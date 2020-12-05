from drill.api.bp.gear.agent import AgentInterface, AgentStat
from collections import deque, defaultdict
import numpy as np
import math 

from env.env_util import get_type_num, get_weapon_num
from env.env_def import UnitType, RED_AIRPORT_ID, MapInfo, SideType, MissileType
from common.cmd import Command
from common.grid import MapGrid
from player.red.rule_player import RulePlayer
from common.threat_analysis import ThreatAnalysis

ATTR_NAME = {getattr(UnitType, attr): attr for attr in dir(UnitType) if not attr.startswith('_')}


class PlayerConfig:
    MY_UNIT_TYPES = [UnitType.A2A, UnitType.A2G, UnitType.JAM, UnitType.AWACS]
    MY_UNIT_MASK_TYPES = [UnitType.A2G]
    MAX_MY_UNIT_LEN = 44

    EN_UNIT_TYPES = [UnitType.A2A, UnitType.A2G, UnitType.AWACS, UnitType.SHIP, 
                     UnitType.S2A, UnitType.RADAR, UnitType.COMMAND]
    MAX_EN_UNIT_LEN = 40
    MINI_MAP_SIZE = 32
    GLOBAL_MOVE_SIZE = 4

# todo: 临时放在这里，后面AgetnStat优化之后，会移到AgentStat里面。
full_name_dict, side_sets = {}, {'red': PlayerConfig.MY_UNIT_TYPES, 'blue': PlayerConfig.EN_UNIT_TYPES}
side_full_name = {k: dict() for k in side_sets}

# 从 'pos_x' 和 'pos_y' 到具体位置的映射，设置加分区域和减分区域
patrol_point_map = {
    (0, 0): [-250830, 184288, 8000],    #  +2分
    (0, 1): [-295519, -100815, 8000],   #  +2分
    (0, 2): [-250830, 294288, 8000],    #  +1分
    (0, 3): [-140830, 294288, 8000],    #  +1分
    (1, 0): [-140830, 184288, 8000],    #  +1分
    (1, 1): [-295519, -210815, 8000],   #  +1分
    (1, 2): [-185519, -210815, 8000],   #  +1分
    (1, 3): [-185519, -100815, 8000],   #  +1分
    (2, 0): [-250830, 74288, 8000],     #  +1分
    (2, 1): [-295519, 9185, 8000],      #  +1分
    (2, 2): [-50830, 41736, 8000],      #  -1分
    (2, 3): [59170, 41736, 8000],       #  -1分
    (3, 0): [-50830, 239288, 8000],     #  -1分
    (3, 1): [-95519, -155815, 8000],    #  -1分
    (3, 2): [128000, 40000, 8000],      #  -1分
    (3, 3): [-140000, 40000, 8000],     #  -1分
}

# 将巡逻位点分为三类，每一类的资质评估不一样
patrol_area_type1 = [(0, 0), (0, 1)]
patrol_area_type2 = [(0, 2), (0, 3), (1, 0), (1, 1), (1, 2), (1, 3), (2, 0), (2, 1)]
patrol_area_type3 = [(2, 2), (2, 3), (3, 0), (3, 1), (3, 2), (3, 3)]

class NJ01Stat(AgentStat):
    def __init__(self):
        super().__init__()
        self.__create_name_dict()

    def __create_name_dict(self):
        for each_side, each_set in side_sets.items():
            for unit_type in each_set:
                type_name = ATTR_NAME[unit_type]
                full_name = '_'.join(['info', each_side, type_name])
                setattr(self, full_name, 0)
                side_full_name[each_side][unit_type] = full_name

    def update_step(self, raw_obs, env_step_info, prev_reward):
        super().update_step(raw_obs, env_step_info, prev_reward)
        if env_step_info.player_done or env_step_info.env_done:
            self.__count(raw_obs)

    def __count(self, raw_obs):
        cnt_dict = {}
        for each_side, each_set in side_sets.items():
            for unit in raw_obs[each_side]['units']:
                unit_type = unit['LX']
                if unit_type in each_set:
                    full_name = side_full_name[each_side][unit_type]
                    cnt_dict[full_name] = cnt_dict.get(full_name, 0) + 1
        for full_name, num in cnt_dict.items():
            setattr(self, full_name, num)

    def summarise(self):
        result = super(NJ01Stat, self).summarise()
        print('result', result)
        return result

class NJ01Player(AgentInterface):

    def __init__(self, side, feature_templates,
                 action_type, network_conf=None):
        super().__init__(feature_templates, action_type, network_conf)
        self.side = side
        self.__init_variables()
        
    @property
    def agent_stat(self) -> AgentStat:
        return self.__agent_stat

    def __init_variables(self):
        self.my_unit_ids = []
        self.en_unit_ids = []
        self.reward_obj = RedReward()
        # map grid for global move
        self.map_grid = MapGrid(
            (MapInfo.X_MIN, MapInfo.Y_MAX), (MapInfo.X_MAX, MapInfo.Y_MIN), 
            PlayerConfig.GLOBAL_MOVE_SIZE, PlayerConfig.GLOBAL_MOVE_SIZE)
        # map grid for minimap
        self.mini_map_grid = MapGrid(
            (MapInfo.X_MIN, MapInfo.Y_MAX), (MapInfo.X_MAX, MapInfo.Y_MIN), 
            PlayerConfig.MINI_MAP_SIZE, PlayerConfig.MINI_MAP_SIZE)
        self.threat_analysis = ThreatAnalysis(self.mini_map_grid, {UnitType.A2A: 80000})

        self.rule_player = RulePlayer(self.side)
        self.__agent_stat = NJ01Stat()
        

        # added by jts
        self.target_ship = None    
        self.rockets = None        # 记录了导弹信息，方便采取反击动作
        self.rocket_target = set()    # 记录被导弹打击的单位编号，存储的为 unit['ID']
        
        self.team_unit_map = {}    # 记录从 unit['TMID'] -> [unit1, unit2 ...] 所包含单位的映射
        self.unit_attack_task = {}   # 记录了当前档位所接受指令的等级，打指挥所或者打船为 1，巡逻为 2 ，有先后关系
        self.target_command = []    
        # 目前躲弹效果不好，暂不考虑
        

    def transform_action2command(self, action, raw_obs):
        """
        :param action:
        :param raw_obs:
        :return: (command, valid_action for MultipleHeadsAction)
        """
        cmds = []
        cmds.extend(self.rule_player.step(raw_obs))
        self.update_info(raw_obs)
        command, valid_actions = self._make_commands(action, raw_obs)
        # cmds.extend(command)

        return cmds, valid_actions

    # 返回 单位ID -> 编队ID 的映射
    def unit2team(self, raw_obs):
        unit_team_map = {}
        for unit in raw_obs[self.side]['units']:
            unit_team_map[unit['ID']] = unit['TMID']
        return unit_team_map
    
    def update_info(self, raw_obs):
        # 敌方舰船和指挥所
        for unit in raw_obs[self.side]['qb']:
            if unit['LX'] == UnitType.SHIP:
                self.is_ship_found = True 
                if self.target_ship is None:
                    self.target_ship = unit 
        
        self.target_command = [unit for unit in raw_obs[self.side]['qb'] if unit['LX'] == UnitType.COMMAND]

        # 编队ID 到 [unit_1, unit_2, ...., unit_n] 的映射
        self.team_unit_map = {}
        for unit in raw_obs[self.side]['units']:
            if unit['TMID'] not in self.team_unit_map.keys():
                self.team_unit_map[unit['TMID']] = [unit]
            else:
                self.team_unit_map[unit['TMID']].append(unit)

        # 更新导弹信息
        self.rockets = raw_obs[self.side]['rockets']
        self.rocket_target = set()
        for rocket in self.rockets:
            self.rocket_target.add(rocket['N2'])

        # 更新敌方舰船信息
        self.ships = [unit for unit in raw_obs[self.side]['qb'] if unit['LX'] == UnitType.SHIP]

        # 更新返航补弹飞机的任务状态
        unit_in_air = [unit['ID'] for unit in raw_obs[self.side]['units']]
        for uid in self.unit_attack_task.keys():
            if self.unit_attack_task[uid] == 3 and uid not in unit_in_air: 
                self.unit_attack_task[uid] = 2
        
        
    def collect_features(self, raw_obs, env_step_info):
        """
        user-defined interface to collect feature values (including historic features), which will be
        transformed to state by o2s_transformer
        :param raw_obs: raw_obs from env
        :param env_step_info:
        :return: feature_template_values according to the feature_template_dict
            e.g., for feature_templates
            {
                "common_template": CommonFeatureTemplate(features={"last_action": OneHotFeature(depth=10)}),
                "entity_template": EntityFeatureTemplate(max_length=10, features={"pos_x": RangedFeature(limited_range=8)}),
                "spatial_template": SpatialFeatureTemplate(height=8, width=8, features={"visibility": PlainFeature()})
            }, it should return something like
            {
                "common_template": {"last_action": 5},
                "entity_template": {"pos_x": 6.6},
                "spatial_template": {"visibility": [[1] * 8] * 8}
            }
        """
        print("current time: ", raw_obs['sim_time'])
        feature_template_values = self._make_feature_values(raw_obs)
        return feature_template_values

    def _make_feature_values(self, raw_obs):
        """根据场上所有可见unit的信息提取state vector"""
        my_units, self.my_unit_ids, my_units_masks = self._get_my_units_feature_values(raw_obs)
        en_units, self.en_unit_ids = self._get_en_units_feature_values(raw_obs)
        common = self._get_common_feature_values(raw_obs)
        mini_map = self._get_spatial_feature_values(raw_obs)

        feature_value = {}
        feature_value['my_units'] = my_units
        feature_value['en_units'] = en_units
        feature_value['mini_map'] = mini_map
        feature_value['common'] = common
        feature_value['selected_units_mask'] = {'mask': my_units_masks}
        
        return feature_value

    def team_get_my_units_feature_values(self, raw_obs):
        my_units = []
        my_unit_ids = []
        masks = []

        unit_team_map = self.unit2team(raw_obs)
        for unit in raw_obs[self.side]['units']:
            # 选择了某编队中第一个被选中的单位的坐标和类型作为该编队的相关信息
            if unit['LX'] in PlayerConfig.MY_UNIT_TYPES and unit['TMID'] not in my_unit_ids:
                my_unit_ids.append(unit_team_map[unit['ID']])
                if unit['LX'] in PlayerConfig.MY_UNIT_MASK_TYPES:
                    masks.append(1)
                else:
                    masks.append(1)
                my_unit_map = {}
                my_unit_map['x'] = unit['X']
                my_unit_map['y'] = unit['Y']
                my_unit_map['z'] = unit['Z']
                my_unit_map['course'] = unit['HX']
                my_unit_map['type'] = PlayerConfig.MY_UNIT_TYPES.index(unit['LX'])
                my_units.append(my_unit_map)

        mask_paddings = [0 for _ in range(PlayerConfig.MAX_MY_UNIT_LEN - len(masks))]
        masks.extend(mask_paddings)
        # TODO(zhoufan): masks长度可能超过60，会出问题吗？
        
        return my_units, my_unit_ids, masks[:PlayerConfig.MAX_MY_UNIT_LEN]

    def _get_my_units_feature_values(self, raw_obs):
        my_units = []
        my_unit_ids = []
        masks = []
        
        rocket_target = set()
        for rocket in raw_obs['red']['rockets']:
            rocket_target.add(rocket['N2'])
        
        for unit in raw_obs[self.side]['units']:
            if unit['LX'] in PlayerConfig.MY_UNIT_TYPES:
                my_unit_ids.append(unit['ID'])
                if unit['LX'] in PlayerConfig.MY_UNIT_MASK_TYPES:
                    masks.append(1)
                else:
                    masks.append(1)
                my_unit_map = {}
                my_unit_map['x'] = unit['X']
                my_unit_map['y'] = unit['Y']
                my_unit_map['z'] = unit['Z']
                my_unit_map['a2a'] = get_weapon_num(unit, MissileType.A2A)
                my_unit_map['a2g'] = get_weapon_num(unit, MissileType.A2G)
                my_unit_map['course'] = unit['HX']
                my_unit_map['speed'] = unit['SP']
                my_unit_map['locked'] = 1 if unit['ID'] in rocket_target else 0 
                # my_unit_map['locked'] = unit['Locked']
                my_unit_map['type'] = PlayerConfig.MY_UNIT_TYPES.index(unit['LX'])
                my_units.append(my_unit_map)
        mask_paddings = [0 for _ in range(PlayerConfig.MAX_MY_UNIT_LEN - len(masks))]
        masks.extend(mask_paddings)
        # TODO(zhoufan): masks长度可能超过60，会出问题吗？
        return my_units, my_unit_ids, masks[:PlayerConfig.MAX_MY_UNIT_LEN]

    def _get_en_units_feature_values(self, raw_obs):
        en_units = []
        en_unit_ids = []
        for unit in raw_obs[self.side]['qb']:
            if unit['LX'] in PlayerConfig.EN_UNIT_TYPES:
                en_unit_map = {}
                en_unit_map['x'] = unit['X']
                en_unit_map['y'] = unit['Y']
                en_unit_map['z'] = unit['Z']
                en_unit_map['course'] = unit['HX']
                en_unit_map['speed'] = unit['SP']
                en_unit_map['type'] = PlayerConfig.EN_UNIT_TYPES.index(unit['LX'])
                en_units.append(en_unit_map)
                en_unit_ids.append(unit['ID'])
        return en_units, en_unit_ids
    
    def _get_spatial_feature_values(self, raw_obs):
        mini_map = {}
        mini_map['my_a2a'] = self._get_binary_matrix(raw_obs, UnitType.A2A)
        mini_map['my_a2g'] = self._get_binary_matrix(raw_obs, UnitType.A2G)
        mini_map['en_a2a'] = self._get_binary_matrix(raw_obs, UnitType.A2A, True)
        mini_map['en_a2g'] = self._get_binary_matrix(raw_obs, UnitType.A2G, True)
        mini_map['threat'] = self.threat_analysis.get_threat_matrix(raw_obs['red'])
        return mini_map

    def _get_binary_matrix(self, raw_obs, type_, qb=False):
        binary_matrix = np.zeros((PlayerConfig.MINI_MAP_SIZE, PlayerConfig.MINI_MAP_SIZE))
        category = 'qb' if qb else 'units'
        for unit in raw_obs[self.side][category]:
            if unit['LX'] == type_:
                x_idx, y_idx = self.map_grid.get_idx(unit['X'], unit['Y'])
                binary_matrix[y_idx][x_idx] = 1 
        return binary_matrix

    def _get_common_feature_values(self, raw_obs):
        common_map = {}
        common_map['sim_time'] = raw_obs['sim_time']
        return common_map

    def select_team_from_unit(self, unit_team_map, selected_units):
        teams = set()
        for id_ in selected_units:
            if id_ in unit_team_map.keys():
                teams.add(unit_team_map[id_])
        return teams 

    def get_attack_direction(self, target, unit):
        # 余弦定理
        a = 1
        b = math.sqrt(math.pow(target['X'] - unit['X'], 2) + math.pow(target['Y'] - unit['Y'], 2))
        c = math.sqrt(math.pow(unit['X'] - target['X'], 2) + math.pow(unit['Y'] - (target['Y'] + 1), 2))
        cos_theta = (a * a + b * b - c * c)/(2 * a * b)

        if unit['X'] >= target['X']:
            direction = math.acos(cos_theta) * 180./math.pi
            direction = 180 + direction
        else:
            direction = 180 - math.acos(cos_theta) * 180./math.pi

        return direction

    # 返回当前的unit[目前只支持A2A和A2G]是否可以接受打击 target 的动作
    def is_attack_valid(self, unit, target):
        dis_constrain = self.cal_unit_dis(unit, target) < 110. 
        # self.unit_attack_task 目前只有三种状态，空 或 0 或 1
        task_constrain = unit['ID'] not in self.unit_attack_task.keys() or self.unit_attack_task[unit['ID']] == 2
        curr_missle_num = unit['WP']['360'] if unit['LX'] == UnitType.A2G else unit['WP']['170']
        total_missle_num = 2 if unit['LX'] == UnitType.A2G else 6 
        if dis_constrain:
            if task_constrain and curr_missle_num > 0:
                return True 
            if not task_constrain and 0 < curr_missle_num < total_missle_num:
                return True 
            if curr_missle_num == 0:
                return False
        else:
            return False

    # 打船，对轰炸机编队中每一个单位下指令
    def attack_ship(self, raw_obs, unit_team_map, teams):
        cmd = [] 
        if len(self.en_unit_ids) > 0:
            for team in teams:
                # unit = self._id2unit(raw_obs, id_, is_enermy=False)
                for unit in self.team_unit_map[team]:
                    if unit and unit['LX'] == UnitType.A2G:
                        for ship in self.ships:
                            # 在 110 km 处开始发弹；只有没任务或者任务状态为巡逻(=2)的才可以接受打击船的指令，
                            if self.is_attack_valid(unit, ship):
                                direction = self.get_attack_direction(ship, unit)
                                cmd.append(Command.target_hunt(unit['ID'], ship['ID'], 90, direction))
                                self.unit_attack_task[unit['ID']] = 1   # 此时状态码置为 1
                                print('unit:{} attack ship:{}'.format(unit['ID'], ship['ID']))
                                break
        
        return cmd 
    
    # 打指挥所，对编队中每一个单位下指令 
    def attack_command(self, raw_obs, unit_team_map, teams):
        cmd = []
        if len(self.en_unit_ids) > 0:
            for team in teams:
                for unit in self.team_unit_map[team]:
                    if unit and unit['LX'] == UnitType.A2G:
                        for commander in self.target_command:
                            # 距离指挥所 110 km 开启目标突击
                            if self.is_attack_valid(unit, commander):
                                direction = self.get_attack_direction(commander, unit)
                                cmd.append(Command.target_hunt(unit['ID'], commander['ID'], 90, direction))
                                self.unit_attack_task[unit['ID']] = 1
                                print("attack command start !uid={}, missile={}, direction={}".format(unit['ID'], unit['WP']['360'], direction))
                                break

        return cmd 
    
    # 反击，对于被导弹锁定的单位，如果此时不处于打击任务，就立即朝最近的单位进行反击
    def fight_back(self, raw_obs):
        cmd = []
        for uid in self.rocket_target:
            if uid not in self.unit_attack_task.keys() or self.unit_attack_task[uid] == 2:
                unit = self._id2unit(raw_obs, uid, is_enermy=False)
                if unit:
                    for en_unit in raw_obs[self.side]['qb']:
                        dis = self.cal_unit_dis(unit, en_unit)
                        if dis < 125:
                            # 对于 A2A 来说反击只需要一架
                            if unit['LX'] == UnitType.A2A and en_unit['LX'] == UnitType.A2A:
                                direction = self.get_attack_direction(en_unit, unit)
                                cmd.append(Command.a2a_attack(unit['ID'], en_unit['ID']))
                                self.unit_attack_task[unit['ID']] = 1
                            # 对于 A2G 来说反击需要一个编队
                            if unit['LX'] == UnitType.A2G and (en_unit['LX'] == UnitType.SHIP or en_unit['LX'] == UnitType.COMMAND or en_unit['LX'] == UnitType.S2A):
                                team = unit['TMID']
                                for team_unit in self.team_unit_map[team]:
                                    direction = self.get_attack_direction(en_unit, team_unit)
                                    cmd.append(Command.target_hunt(team_unit['ID'], en_unit['ID'], 98, direction))
                                    self.unit_attack_task[unit['ID']] = 1 
        
        return cmd 
    
    def a2g_return(self, raw_obs):
        cmd = []
        for unit in raw_obs['red']['units']:
            if unit['LX'] == UnitType.A2G and unit['WP']['360'] == 0:
                cmd.append(Command.return2base(unit['ID'], RED_AIRPORT_ID))
                self.unit_attack_task[unit['ID']] = 3   # 表示正在返航 

        return cmd


    # 只安排巡逻，打击全部由规则操作(代号：version4)
    def _make_commands(self, actions, raw_obs):
        # 初始化 valid_action 
        selected_units = []
        for idx in actions['selected_units']:
            if idx > 0:
                selected_units.append(self.my_unit_ids[idx - 1])
        valid_actions = {}
        for key, value in actions.items():
            valid_actions[key] = 0.0 
        if len(selected_units) != 0:
            valid_actions['selected_units'] = 1.0
        else:
            valid_actions['selected_units'] = 0
        valid_actions['meta_action'] = 1.0
        action_cmds = []
        meta_action = actions['meta_action']
    
        commands_pos = []
        for cmd in self.target_command:
            commands_pos.append([cmd['X'], cmd['Y'], cmd['Z']])

        unit_team_map = self.unit2team(raw_obs)
        # 将所选单位列表 (selected_units) 映射到其所在编队
        teams = self.select_team_from_unit(unit_team_map, selected_units)
        
        action_cmds.extend(self.fight_back(raw_obs))
        action_cmds.extend(self.a2g_return(raw_obs))

        for en_unit in raw_obs['red']['qb']:
            if en_unit['LX'] == UnitType.SHIP or en_unit['LX'] == UnitType.COMMAND or en_unit['LX'] == UnitType.S2A:
                for unit in raw_obs['red']['units']:
                    if unit['LX'] == UnitType.A2G and self.cal_unit_dis(en_unit, unit) < 120:
                        team = unit['TMID']
                        for team_unit in self.team_unit_map[team]:
                            if (team_unit['ID'] not in self.unit_attack_task.keys() or self.unit_attack_task[team_unit['ID']] == 2):
                                direction = self.get_attack_direction(en_unit, team_unit)
                                action_cmds.append(Command.target_hunt(team_unit['ID'], en_unit['ID'], 100, direction))
                                self.unit_attack_task[team_unit['ID']] = 1 
                            if team_unit['WP']['360'] == 1 and self.unit_attack_task[unit['ID']] == 1:
                                direction = self.get_attack_direction(en_unit, team_unit)
                                action_cmds.append(Command.target_hunt(team_unit['ID'], en_unit['ID'], 100, direction))
                                self.unit_attack_task[unit['ID']] = 0 


        # 新的打船策略
        # for team, units in self.team_unit_map.items():
        #     for unit in units:
        #         if self.cal_unit_dis(unit, self.target_ship) < 50 and unit['ID'] not in self.rocket_target:
        #             if unit['ID'] in self.unit_task_state.keys() and self.unit_task_state[unit['ID']] == 2:
        #                 print('unit accept attack task: ', unit['ID'])
        #                 self.unit_task_state[unit['ID']] = 1
        #                 direction = self.get_attack_direction(self.target_ship, unit)
        #                 cmd.append(Command.target_hunt(unit['ID'], self.target_ship['ID'], 90, direction))
        #             if self.cal_unit_dis(unit, self.target_ship) > 50 and unit['ID'] not in self.rocket_target:
        #                 if unit['ID'] in self.unit_task_state.keys() and self.unit_task_state[unit['ID']] == 2:
        #                     print('unit accept patrol task: ', unit['ID'])
        #                     self.unit_task_state[unit['ID']] = 2    # 表示目前接受巡逻任务
        #                     center_point = [self.target_ship['X'], self.target_ship['Y'], self.target_ship['Z']]
        #                     cmd.append(Command.area_patrol(unit['ID'], center_point))
        #             if unit['ID'] in self.rocket_target:
        #                 print('unit accept escape task: ', unit['ID'])
        #                 escape_point = self.get_escape_point(self.rockets, unit)
        #                 self.unit_task_state[unit['ID']] = 3
        #                 for rocket in self.rockets:
        #                     print('rocket info', rocket)
        #                 if escape_point is not None:
        #                     cmd.append(Command.area_patrol(unit['ID'], escape_point))
        #                     self.unit_task_state[unit['ID']] = 3
        #             if unit['WP']['360'] == 1 and self.unit_task_state[unit['ID']] == 1:
        #                 direction = self.get_attack_direction(self.target_ship, unit)
        #                 cmd.append(Command.target_hunt(unit['ID'], self.target_ship['ID'], 90, direction))
        #                 self.unit_task_state[unit['ID']] = 0
        #             if self.unit_task_state[unit['ID']] == 3 and self.cal_unit_dis(unit, self.target_ship) > 155:
        #                 print('unit accept approach task: ', unit['ID'])
        #                 self.rocket_target.remove(unit['ID'])
        #                 self.unit_task_state[unit['ID']] = 2
                
                
        
        if meta_action == 0:    # 区域巡逻
            valid_actions['pos_x'] = 1.0
            valid_actions['pos_y'] = 1.0
            patrol_zone_x_idx = float(actions['pos_x'])
            patrol_zone_y_idx = float(actions['pos_y'])
            center_points = patrol_point_map[(patrol_zone_x_idx, patrol_zone_y_idx)]

            for team in teams:
                for unit in self.team_unit_map[team]:
                    if unit['ID'] not in self.unit_attack_task.keys() or self.unit_attack_task[unit['ID']] == 2:
                        action_cmds.append(Command.area_patrol(unit['ID'], center_points))
                        self.unit_attack_task[unit['ID']] = 2 

        
        # elif meta_action == 1:      # 空中拦截，目前认为 'target_unit' 只作为歼击机的拦截目标 
        #     valid_actions['target_unit'] = 1.0  # target unit valid 
        #     target_idx = actions['target_unit'] 
        #     # 给出了在 self.en_unit_ids 中的索引，从 self.en_unit_ids 中取出平台编号
        #     if len(self.en_unit_ids) > 0:
        #         for id_ in selected_units:
        #             our_unit = self._id2unit(raw_obs, id_, is_enermy=False)
        #             en_unit = self._id2unit(raw_obs, self.en_unit_ids[target_idx], is_enermy=True)
        #             if our_unit and en_unit:
        #                 if self.cal_unit_dis(our_unit, en_unit) < 150.:       # 200 km 之内开始目标打击
        #                     action_cmds.append(Command.a2a_attack(id_, self.en_unit_ids[target_idx]))
        #                 else:
        #                     patrol_point = [en_unit["X"], en_unit["Y"], en_unit["Z"]]
        #                     for id_ in selected_units:
        #                         action_cmds.append(Command.area_patrol(id_, patrol_point))

        
        return action_cmds, valid_actions
    
    
    # 3 个动作输出的宏动作，(代号：version1)
    def ver3_make_commands(self, actions, raw_obs):
        # 初始化 valid_action 
        selected_units = []
        for idx in actions['selected_units']:
            if idx > 0:
                selected_units.append(self.my_unit_ids[idx - 1])
        valid_actions = {}
        for key, value in actions.items():
            valid_actions[key] = 0.0 
        if len(selected_units) != 0:
            valid_actions['selected_units'] = 1.0
        else:
            valid_actions['selected_units'] = 0
        valid_actions['meta_action'] = 1.0
        action_cmds = []
        meta_action = actions['meta_action']
    
        commands_pos = []
        for cmd in self.target_command:
            commands_pos.append([cmd['X'], cmd['Y'], cmd['Z']])

        # 从obs中得到其单位ID到编队ID的映射
        unit_team_map = self.unit2team(raw_obs)
        print('unit_team_map', unit_team_map)
        # 将所选单位列表 (selected_units) 映射到其所在编队
        teams = self.select_team_from_unit(unit_team_map, selected_units)
        
        if meta_action == 0:    # 区域巡逻
            valid_actions['pos_x'] = 1.0
            valid_actions['pos_y'] = 1.0
            patrol_zone_x_idx = float(actions['pos_x'])
            patrol_zone_y_idx = float(actions['pos_y'])
            center_points = patrol_point_map[(patrol_zone_x_idx, patrol_zone_y_idx)]

            for team in teams:
                for unit in self.team_unit_map[team]:
                    if unit['ID'] not in self.unit_attack_task.keys() or self.unit_attack_task[unit['ID']] == 2:
                        action_cmds.append(Command.area_patrol(unit['ID'], center_points))
                        self.unit_attack_task[unit['ID']] = 2 
                

        # elif meta_action == 1:      # 空中拦截，目前认为 'target_unit' 只作为歼击机的拦截目标 
        #     valid_actions['target_unit'] = 1.0  # target unit valid 
        #     target_idx = actions['target_unit'] 
        #     # 给出了在 self.en_unit_ids 中的索引，从 self.en_unit_ids 中取出平台编号
        #     if len(self.en_unit_ids) > 0:
        #         for id_ in selected_units:
        #             our_unit = self._id2unit(raw_obs, id_, is_enermy=False)
        #             en_unit = self._id2unit(raw_obs, self.en_unit_ids[target_idx], is_enermy=True)
        #             if our_unit and en_unit:
        #                 if self.cal_unit_dis(our_unit, en_unit) < 150.:       # 200 km 之内开始目标打击
        #                     action_cmds.append(Command.a2a_attack(id_, self.en_unit_ids[target_idx]))
        #                 else:
        #                     patrol_point = [en_unit["X"], en_unit["Y"], en_unit["Z"]]
        #                     for id_ in selected_units:
        #                         action_cmds.append(Command.area_patrol(id_, patrol_point))

        elif meta_action == 1:      # 让某一编队朝着最近的指挥所移动
            for team in teams:
                if len(self.target_command) == 1:
                    patrol_point = [self.target_command[0]['X'], self.target_command[0]['Y'], self.target_command[0]['Z']]
                if len(self.target_command) == 2:
                    if self.cal_unit_dis(self.team_unit_map[team][0], self.target_command[0]) < self.cal_unit_dis(self.team_unit_map[team][0], self.target_command[1]):
                        patrol_point = [self.target_command[0]['X'], self.target_command[0]['Y'], self.target_command[0]['Z']]
                    else:
                        patrol_point = [self.target_command[1]['X'], self.target_command[1]['Y'], self.target_command[1]['Z']] 

                action_cmds.append(Command.area_patrol(team, patrol_point))
            
        elif meta_action == 2:
            action_cmds.extend(self.fight_back(raw_obs))
        
        return action_cmds, valid_actions


    # 第一个版本的编队控制，实现了简单思路，直接将单位映射到所在编队，然后控制该编队(代号：version2)
    def ver1_make_commands(self, actions, raw_obs):
        # 初始化 valid_action 
        selected_units = []
        for idx in actions['selected_units']:
            if idx > 0:
                selected_units.append(self.my_unit_ids[idx - 1])
        valid_actions = {}
        for key, value in actions.items():
            valid_actions[key] = 0.0 
        if len(selected_units) != 0:
            valid_actions['selected_units'] = 1.0
        else:
            valid_actions['selected_units'] = 0
        valid_actions['meta_action'] = 1.0
        action_cmds = []
        meta_action = actions['meta_action']
    
        commands_pos = []
        for cmd in self.target_command:
            commands_pos.append([cmd['X'], cmd['Y'], cmd['Z']])

        # 从obs中得到其单位ID到编队ID的映射
        unit_team_map = self.unit2team(raw_obs)
        # 将所选单位列表 (selected_units) 映射到其所在编队
        teams = self.select_team_from_unit(unit_team_map, selected_units)

        if meta_action == 0:    # 区域巡逻
            valid_actions['pos_x'] = 1.0
            valid_actions['pos_y'] = 1.0
            patrol_zone_x_idx = float(actions['pos_x'])
            patrol_zone_y_idx = float(actions['pos_y'])
            center_points = patrol_point_map[(patrol_zone_x_idx, patrol_zone_y_idx)]

            for team in teams:
                for unit in self.team_unit_map[team]:
                    if unit['ID'] not in self.unit_attack_task.keys() or self.unit_attack_task[unit['ID']] == 2:
                        action_cmds.append(Command.area_patrol(team, center_points))
                        self.unit_attack_task[unit['ID']] = 2
                

        elif meta_action == 1:      # 空中拦截，目前认为 'target_unit' 只作为歼击机的拦截目标 
            valid_actions['target_unit'] = 1.0  # target unit valid 
            target_idx = actions['target_unit'] 
            # 给出了在 self.en_unit_ids 中的索引，从 self.en_unit_ids 中取出平台编号
            if len(self.en_unit_ids) > 0:
                for id_ in selected_units:
                    our_unit = self._id2unit(raw_obs, id_, is_enermy=False)
                    en_unit = self._id2unit(raw_obs, self.en_unit_ids[target_idx], is_enermy=True)
                    if our_unit and en_unit:
                        if self.cal_unit_dis(our_unit, en_unit) < 150.:       # 200 km 之内开始目标打击
                            action_cmds.append(Command.a2a_attack(id_, self.en_unit_ids[target_idx]))
                        else:
                            patrol_point = [en_unit["X"], en_unit["Y"], en_unit["Z"]]
                            for id_ in selected_units:
                                action_cmds.append(Command.area_patrol(id_, patrol_point))

        elif meta_action == 2:      # 让编队朝着最近的指挥所移动
            for team in teams:
                if len(self.target_command) == 1:
                    patrol_point = [self.target_command[0]['X'], self.target_command[0]['Y'], self.target_command[0]['Z']]
                if len(self.target_command) == 2:
                    if self.cal_unit_dis(self.team_unit_map[team][0], self.target_command[0]) < self.cal_unit_dis(self.team_unit_map[team][0], self.target_command[1]):
                        patrol_point = [self.target_command[0]['X'], self.target_command[0]['Y'], self.target_command[0]['Z']]
                    else:
                        patrol_point = [self.target_command[1]['X'], self.target_command[1]['Y'], self.target_command[1]['Z']] 
            
        elif meta_action == 3:      # 对指挥所突击，需要对轰炸机编队进行控制 
            # valid_actions['target_unit'] = 1.0
            # target_idx = actions['target_unit']
            action_cmds.extend(self.attack_command(raw_obs, unit_team_map, teams))

        elif meta_action == 4:       # 对船突击，需要对轰炸机编队进行控制
            # valid_actions['target_unit'] = 1.0
            # target_idx = actions['target_unit']
            action_cmds.extend(self.attack_ship(raw_obs, unit_team_map, teams))
            
        elif meta_action == 5:
            action_cmds.extend(self.fight_back(raw_obs))
        
        return action_cmds, valid_actions


    # 第二个版本的编队控制，实现的是态势由编队态势构成，然后由指针网络挑选出来编队(代号：version3)
    def ver2_make_commands(self, actions, raw_obs):
        # 初始化 valid_action 
        selected_units = []
        for idx in actions['selected_units']:
            if idx > 0:
                selected_units.append(self.my_unit_ids[idx - 1])

        valid_actions = {}
        for key, value in actions.items():
            valid_actions[key] = 0.0 

        if len(selected_units) != 0:
            valid_actions['selected_units'] = 1.0
        else:
            valid_actions['selected_units'] = 0
        valid_actions['meta_action'] = 1.0

        commands = [unit for unit in raw_obs['red']['qb'] if unit['LX'] == UnitType.COMMAND]
        commands_pos = []
        for cmd in commands:
            commands_pos.append([cmd['X'], cmd['Y'], cmd['Z']])

        ships = [unit for unit in raw_obs['red']['qb'] if unit['LX'] == UnitType.SHIP]

        action_cmds = []
        meta_action = actions['meta_action']

        unit_team_map = self.unit2team(raw_obs)

        if meta_action == 0:    # 区域巡逻，如果当前处于打击任务中就不进行巡逻
            valid_actions['pos_x'] = 1.0
            valid_actions['pos_y'] = 1.0
            patrol_zone_x_idx = float(actions['pos_x'])
            patrol_zone_y_idx = float(actions['pos_y'])
            center_points = patrol_point_map[(patrol_zone_x_idx, patrol_zone_y_idx)]

            for tid in selected_units:
                if tid not in self.team_attack_task.keys():
                    action_cmds.append(Command.area_patrol(tid, center_points))

            # center_point_x, center_point_y = self.map_grid.get_center(
            #     patrol_zone_x_idx, patrol_zone_y_idx)
            # center_points.append(center_point_x)
            # center_points.append(center_point_y)
            # center_points.append(8000)

        elif meta_action == 1:      # 空中拦截，依然选择编队去做空中拦截，可能有点浪费
            valid_actions['target_unit'] = 1.0  # target unit valid 
            target_idx = actions['target_unit'] 
            # 给出了在 self.en_unit_ids 中的索引，从 self.en_unit_ids 中取出平台编号
            if len(self.en_unit_ids) > 0:
                for id_ in selected_units:
                    our_unit = self._id2unit(raw_obs, id_, is_enermy=False)
                    en_unit = self._id2unit(raw_obs, self.en_unit_ids[target_idx], is_enermy=True)
                    if our_unit and en_unit:
                        if self.cal_unit_dis(our_unit, en_unit) < 180.:       # 200 km 之内开始空中拦截
                            action_cmds.append(Command.a2a_attack(id_, self.en_unit_ids[target_idx]))
                        else:
                            patrol_point = [en_unit["X"], en_unit["Y"], en_unit["Z"]]
                            for tid in selected_units:
                                action_cmds.append(Command.area_patrol(tid, patrol_point))

        elif meta_action == 2:      # 随机朝着两个指挥所之一移动
            for id_ in selected_units:  # selected_units 选的都是我方编队
                random_ind = np.random.randint(0, len(commands_pos))
                target_point = commands_pos[random_ind]
                action_cmds.append(Command.area_patrol(id_, target_point))
                
            
        elif meta_action == 3:      # 对指挥所突击，需要对轰炸机编队进行控制 
            # valid_actions['target_unit'] = 1.0
            # target_idx = actions['target_unit']
            fire_range = 100
            direction = 270

            if len(self.en_unit_ids) > 0:
                for tid in selected_units:
                    # 从 TMID 对应的编队中找到其中一个单位，以这个单位作为该编队的代表单元
                    unitid = None 
                    for uid, teamid in unit_team_map.items():
                        if tid == teamid:
                            unitid = uid 
                            break 
                    unit = self._id2unit(raw_obs, unitid, is_enermy=False)

                    # 不在执行打击任务列表中
                    if tid not in self.team_attack_task.keys():
                        for comm in commands:
                            # 在指挥所 150 km 处发动目标突击
                            if unit and self.cal_unit_dis(unit, comm) < 150.:
                                print("attack command start !")
                                self.team_attack_task[tid] = (raw_obs['sim_time'], comm['ID'])  
                                action_cmds.append(Command.target_hunt(tid, comm['ID'], fire_range, direction))
                                break

        else:       # 对船突击，需要对轰炸机编队进行控制
            # valid_actions['target_unit'] = 1.0
            # target_idx = actions['target_unit']
            fire_range = 100 
            direction = 270 
            if len(self.en_unit_ids) > 0:
                for tid in selected_units:
                    # 从 TMID 对应的编队中找到其中一个单位，以这个单位作为该编队的代表单元
                    for uid, teamid in unit_team_map.items():
                        if tid == teamid:
                            unitid = uid 
                            break 
                    unit = self._id2unit(raw_obs, unitid, is_enermy=False)

                    if tid not in self.team_attack_task.keys():
                        for ship in ships:
                            if self.cal_unit_dis(ship, unit) < 150.:
                                print("attack ship start !")
                                self.team_attack_task[tid] = (raw_obs['sim_time'], ship['ID'])
                                action_cmds.append(Command.target_hunt(tid, ship['ID'], fire_range, direction))
                                break 
        
        action_cmds.extend(self._update_team_task(raw_obs))
                        
        return action_cmds, valid_actions


    # 单元（平台）控制，启元的版本
    def inspir_make_commands(self, actions, raw_obs):
        selected_units = []
        for idx in actions['selected_units']:
            if idx > 0:
                selected_units.append(self.my_unit_ids[idx - 1])

        valid_actions = {}
        for key, _ in actions.items():
            valid_actions[key] = 0.0

        if len(selected_units) != 0:
            valid_actions['selected_units'] = 1.0
        else:
            valid_actions['selected_units'] = 0
        valid_actions['meta_action'] = 1.0

        action_cmds = []
        meta_action = actions['meta_action']
        if meta_action == 0:    # 0 是去巡逻
            valid_actions['pos_x'] = 1.0  # x,y valid
            valid_actions['pos_y'] = 1.0  # x,y valid
            # valid_actions['pos_z'] = 1.0   
            patrol_zone_x_idx = actions['pos_x']
            patrol_zone_y_idx = actions['pos_y']
            # patrol_zone_z_idx = actions['pos_z']
            center_points = []
            center_point_x, center_point_y = self.map_grid.get_center(patrol_zone_x_idx, patrol_zone_y_idx)
            center_points.append(center_point_x)
            center_points.append(center_point_y)
            # center_points.append(patrol_zone_z_idx * 1000)
            center_points.append(8000)
            for id_ in selected_units:
                action_cmds.append(Command.area_patrol(id_, center_points))
        elif meta_action == 1: # 1 为歼击机空中拦截，敌方单位好像只有一个，我方单位所有飞机去打击敌方轰炸机或者预警机
            valid_actions['target_unit'] = 1.0  # target unit valid
            target_idx = actions['target_unit']
            for id_ in selected_units:
                action_cmds.append(Command.a2a_attack(id_, self.en_unit_ids[target_idx]))
        elif meta_action == 2: # 2 为轰炸机目标突击，和以上逻辑一致
            valid_actions['target_unit'] = 1.0
            target_idx = actions['target_unit']
            fire_range = 100
            direction = 270
            for id_ in selected_units:
                action_cmds.append(Command.target_hunt(id_, self.en_unit_ids[target_idx], fire_range, direction))
        else:   # 3 为
            print("meta_action > 2")

        return action_cmds, valid_actions


    def _update_team_task(self, raw_obs):
        temp_record = []
        cmd = []
        
        # 为何是 100s 和 8s ？超过 100s 的就删除，超过 8s 的就继续发突击指令
        for team_id in self.team_attack_task.keys():
            if raw_obs['sim_time'] - self.team_attack_task[team_id][0] > 100.:
                temp_record.append(team_id)
            elif raw_obs['sim_time'] - self.team_attack_task[team_id][0] > 8.:
                cmd.append(Command.target_hunt(team_id, self.team_attack_task[team_id][1], 100, 270))

        for tid in temp_record:
            self.team_attack_task.pop(tid)

        return cmd
        
    # 计算两个单位之间的距离
    def cal_unit_dis(self, unit1, unit2):
        return math.sqrt(math.pow(unit1["X"] - unit2["X"], 2) + math.pow(unit1["Y"] - unit2["Y"], 2))/1000.

    def _id2unit(self, raw_obs, id_val, is_enermy):
        if is_enermy:
            for unit in raw_obs[self.side]["qb"]:
                if unit["ID"] == id_val:
                    return unit
        else:
            for unit in raw_obs[self.side]["units"]:
                if unit["ID"] == id_val:
                    return unit 
        return None 
    
    def calculate_reward(self, raw_obs, env_step_info):
        """
        user-defined class to calculate reward for agent player
        :param raw_obs: raw_obs from env
        :param env_step_info:
        :return: reward
        """
        reward = self.reward_obj.get(raw_obs)
        print(reward)
        return reward

    def reset(self, raw_obs, env_step_info):
        super().reset(raw_obs, env_step_info)
        self.__init_variables()


# 给一个新版本，如果靠近指挥所能得到奖励，考虑飞机群相对于指挥所的大格子的位置，处于划分的16个格子的哪个位置，找到飞机相对于哪一个格子更近
# 以格子中心为圆心，50 km 为半径，就被划分到这一个里面，引导其往指挥所飞，但需要做好单位损失和之间的权重分配，又是一个调参的东西，需要测试。

class RedReward(object):

    def __init__(self):
        self.last_a2a_num = -1
        self.last_a2g_num = -1
        self.last_awacs_num = -1
        self.last_en_a2a_num = -1
        self.last_en_a2g_num = -1
        self.last_en_ship_num = -1
        self.last_en_command_num = -1

        self.comm_rew_flag = False
        self._mini_count = {}

    def _get_type_num_diff(self, raw_obs, side, type_, last_num):
        curr_num = get_type_num(raw_obs[side], [type_], consider_airport=True)
        diff = curr_num - last_num if last_num != -1 else 0
        return diff, curr_num

    # 找到 unit 距离哪个小格子比较近，返回的是格子编号，也就是 patrol_point_map 中的某一 key 值
    def find_grid_belong(self, unit):
        min_dis = 1e12
        ans = None
        for xypair, point in patrol_point_map.items():
            dis = self.cal_dis(point, (unit['X'], unit['Y'], unit['Z']))
            if dis < min_dis:
                ans = xypair
                min_dis = dis
        return ans 

    # 统计每一个格子里面的A2A和A2G的数量
    def get_mini_count(self, raw_obs):
        # 给每个格子里的飞机计数，返回一个 xypair -> num 的映射。即便空中单位全没有了，mini_count 也不会为空。
        mini_count = {xypair : 0 for xypair in patrol_point_map.keys()}
        for unit in raw_obs['red']['units']:
            if unit['LX'] == UnitType.A2A or UnitType.A2G:
                pos = self.find_grid_belong(unit)
                mini_count[pos] += 1
        return mini_count 
    
    def compare_mini_count(self, mini_count1, mini_count2):
        # mini_count2 为现在的小区域飞机分布，mini_count1 为上一步的小区域飞机分布
        area_name = ['area1', 'area2', 'area3']
        area_type_count1 = {num : 0 for num in area_name}
        area_type_count2 = {num : 0 for num in area_name}

        for pos, num in mini_count1.items():
            if pos in patrol_area_type1:
                area_type_count1['area1'] += num
            if pos in patrol_area_type2:
                area_type_count1['area2'] += num
            if pos in patrol_area_type3:
                area_type_count1['area3'] += num

        for pos, num in mini_count2.items():
            if pos in patrol_area_type1:
                area_type_count2['area1'] += num
            if pos in patrol_area_type2:
                area_type_count2['area2'] += num
            if pos in patrol_area_type3:
                area_type_count2['area3'] += num

        print("area_type_count1", area_type_count1)
        print("area_type_count2", area_type_count2)

        sum_rew = 0
        sum_rew += 1.0 * (area_type_count2['area1'] - area_type_count1['area1'])    # 鼓励进入区域 1 和区域 2
        sum_rew += area_type_count2['area2'] - area_type_count1['area2']
        sum_rew += -(area_type_count2['area3'] - area_type_count1['area3']) # 鼓励逃离区域 3

        if sum_rew > 0:
            return 2
        if sum_rew == 0:
            return 0
        if sum_rew < 0:
            return -2
        
                
    # 得到接近指挥所的回报
    def appro_comm_rew(self, raw_obs):
        rew = 0
        if self.comm_rew_flag:
            if raw_obs['sim_time'] > 600:
                curr_mini_count = self.get_mini_count(raw_obs)
                rew += self.compare_mini_count(self._mini_count, curr_mini_count)
                self._mini_count = curr_mini_count
        else:
            self.comm_rew_flag = True
            self._mini_count = self.get_mini_count(raw_obs)
        
        return rew
        

    # unit1 和 unit2 为列表或是元组
    def cal_dis(self, unit1, unit2):
        return math.sqrt(math.pow(unit1[0] - unit2[0], 2) + math.pow(unit1[1] - unit2[1], 2))/1000.


    def get(self, raw_obs):
        my_a2a_num_diff, my_a2a_num = self._get_type_num_diff(
                        raw_obs, 'red', UnitType.A2A, self.last_a2a_num)
        self.last_a2a_num = my_a2a_num
        # print('a2a ', my_a2a_num, self.last_a2a_num, my_a2a_num_diff)

        my_a2g_num_diff, my_a2g_num = self._get_type_num_diff(
            raw_obs, 'red', UnitType.A2G, self.last_a2g_num)
        self.last_a2g_num = my_a2g_num
        
        my_awacs_num_diff, my_awacs_num = self._get_type_num_diff(
            raw_obs, 'red', UnitType.AWACS, self.last_awacs_num)
        self.last_awacs_num = my_awacs_num

        en_a2a_num_diff, en_a2a_num = self._get_type_num_diff(
            raw_obs, 'blue', UnitType.A2A, self.last_en_a2a_num)
        self.last_en_a2a_num = en_a2a_num
        

        en_a2g_num_diff, en_a2g_num = self._get_type_num_diff(
            raw_obs, 'blue', UnitType.A2G, self.last_en_a2g_num)
        self.last_en_a2g_num = en_a2g_num

        en_ship_num_diff, en_ship_num = self._get_type_num_diff(
            raw_obs, 'blue', UnitType.SHIP, self.last_en_ship_num)
        self.last_en_ship_num = en_ship_num

        en_command_num_diff, en_command_num = self._get_type_num_diff(
            raw_obs, 'blue', UnitType.COMMAND, self.last_en_command_num)
        self.last_en_command_num = en_command_num


        if raw_obs['sim_time'] > 7992. and en_command_num == 2:
            win_lose_penalize = -10
        else:
            win_lose_penalize = 0

        # control_comm_rew = self.appro_comm_rew(raw_obs)
        control_comm_rew = 0
        
        rew = my_a2a_num_diff * 0.1 + my_a2g_num_diff * 0.2 + en_a2a_num_diff * (-1) + en_a2g_num_diff * (-1) + \
            en_ship_num_diff * (-5) + en_command_num_diff * (-8) + my_awacs_num_diff * 5 + win_lose_penalize + control_comm_rew 
        
        # rew = en_a2a_num_diff * (-1) + en_a2g_num_diff * (-1) + en_ship_num_diff * (-5) + en_command_num_diff * (-8) + win_lose_penalize + control_comm_rew 

        return rew