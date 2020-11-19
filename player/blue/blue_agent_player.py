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


class bluePlayerConfig:
    MY_UNIT_TYPES = [UnitType.A2A, UnitType.A2G, UnitType.JAM, UnitType.AWACS, UnitType.S2A, UnitType.RADAR, UnitType.COMMAND]
    MY_UNIT_MASK_TYPES = [UnitType.A2G]
    MAX_MY_UNIT_LEN = 50

    EN_UNIT_TYPES = [UnitType.A2A, UnitType.A2G, UnitType.AWACS, UnitType.SHIP]
    MAX_EN_UNIT_LEN = 50
    MINI_MAP_SIZE = 16
    GLOBAL_MOVE_SIZE = 8


# todo: 临时放在这里，后面AgetnStat优化之后，会移到AgentStat里面
full_name_dict, side_sets = {}, {'blue': bluePlayerConfig.MY_UNIT_TYPES, 'red': bluePlayerConfig.EN_UNIT_TYPES}
side_full_name = {k: dict() for k in side_sets}


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
        
        return result

class bluePlayer(AgentInterface):

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
        self.reward_obj = BlueReward()
        # map grid for global move
        self.map_grid = MapGrid(
            (MapInfo.X_MIN, MapInfo.Y_MAX), (MapInfo.X_MAX, MapInfo.Y_MIN), 
            bluePlayerConfig.GLOBAL_MOVE_SIZE, bluePlayerConfig.GLOBAL_MOVE_SIZE)
        # map grid for minimap
        self.mini_map_grid = MapGrid(
            (MapInfo.X_MIN, MapInfo.Y_MAX), (MapInfo.X_MAX, MapInfo.Y_MIN), 
            bluePlayerConfig.MINI_MAP_SIZE, bluePlayerConfig.MINI_MAP_SIZE)
        self.threat_analysis = ThreatAnalysis(self.mini_map_grid, {UnitType.A2A: 80000})

        self.rule_player = RulePlayer(self.side)
        self.__agent_stat = NJ01Stat()

    def transform_action2command(self, action, raw_obs):
        """
        :param action:
        :param raw_obs:
        :return: (command, valid_action for MultipleHeadsAction)
        """
        cmds = []
        cmds.extend(self.rule_player.step(raw_obs))
        command, valid_actions = self._make_commands(action, raw_obs)
        cmds.extend(command)
        
        return cmds, valid_actions

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
        print("\rcurr_time_test: {}".format(raw_obs['sim_time']), end='  ')
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

    def _get_my_units_feature_values(self, raw_obs):
        my_units = []
        my_unit_ids = []
        masks = []
        for unit in raw_obs[self.side]['units']:
            if unit['LX'] in bluePlayerConfig.MY_UNIT_TYPES:
                my_unit_ids.append(unit['ID'])
                if unit['LX'] in bluePlayerConfig.MY_UNIT_MASK_TYPES:
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
                my_unit_map['locked'] = unit['Locked']
                my_unit_map['type'] = bluePlayerConfig.MY_UNIT_TYPES.index(unit['LX'])
                my_units.append(my_unit_map)
        mask_paddings = [0 for _ in range(bluePlayerConfig.MAX_MY_UNIT_LEN - len(masks))]
        masks.extend(mask_paddings)
        # TODO(zhoufan): masks长度可能超过60，会出问题吗？
        return my_units, my_unit_ids, masks[:bluePlayerConfig.MAX_MY_UNIT_LEN]

    def _get_en_units_feature_values(self, raw_obs):
        en_units = []
        en_unit_ids = []
        for unit in raw_obs[self.side]['qb']:
            if unit['LX'] in bluePlayerConfig.EN_UNIT_TYPES:
                en_unit_map = {}
                en_unit_map['x'] = unit['X']
                en_unit_map['y'] = unit['Y']
                en_unit_map['z'] = unit['Z']
                en_unit_map['course'] = unit['HX']
                en_unit_map['speed'] = unit['SP']
                en_unit_map['type'] = bluePlayerConfig.EN_UNIT_TYPES.index(unit['LX'])
                en_units.append(en_unit_map)
                en_unit_ids.append(unit['ID'])
        return en_units, en_unit_ids
    
    def _get_spatial_feature_values(self, raw_obs):
        mini_map = {}
        mini_map['my_a2a'] = self._get_binary_matrix(raw_obs, UnitType.A2A)
        mini_map['my_a2g'] = self._get_binary_matrix(raw_obs, UnitType.A2G)
        mini_map['en_a2a'] = self._get_binary_matrix(raw_obs, UnitType.A2A, True)
        mini_map['en_a2g'] = self._get_binary_matrix(raw_obs, UnitType.A2G, True)
        mini_map['threat'] = self.threat_analysis.get_threat_matrix(raw_obs['blue'])
        return mini_map

    def _get_binary_matrix(self, raw_obs, type_, qb=False):
        binary_matrix = np.zeros((bluePlayerConfig.MINI_MAP_SIZE, bluePlayerConfig.MINI_MAP_SIZE))
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
        if meta_action == 0:  # 区域巡逻
            valid_actions['pos_x'] = 1.0  # x,y valid
            valid_actions['pos_y'] = 1.0  # x,y valid
            patrol_zone_x_idx = actions['pos_x']
            patrol_zone_y_idx = actions['pos_y']
            center_points = []
            center_point_x, center_point_y = self.map_grid.get_center(
                patrol_zone_x_idx, patrol_zone_y_idx)
            center_points.append(center_point_x)
            center_points.append(center_point_y)
            center_points.append(8000)
            for id_ in selected_units:
                action_cmds.append(Command.area_patrol(id_, center_points))
        elif meta_action == 1:  # 空中拦截
            valid_actions['target_unit'] = 1.0  # target unit valid
            target_idx = actions['target_unit']
            if len(self.en_unit_ids) > 0:  # 因为没有mask，做一个保护
                for id_ in selected_units:
                    action_cmds.append(
                        Command.a2a_attack(
                            id_, self.en_unit_ids[target_idx]))
        else:  # 目标突击
            valid_actions['target_unit'] = 1.0
            target_idx = actions['target_unit']
            fire_range = 100
            direction = 270  # TODO(zhoufan): direction有更好的解决方案
            if len(self.en_unit_ids) > 0:  # 因为没有mask，做一个保护
                for id_ in selected_units:
                    action_cmds.append(
                        Command.target_hunt(
                            id_,
                            self.en_unit_ids[target_idx],
                            fire_range,
                            direction))
                    
        return action_cmds, valid_actions

    # 计算两个单位之间的距离
    def cal_unit_dis(self, unit1, unit2):
        return math.sqrt(math.pow(unit1["X"] - unit2["X"], 2) + math.pow(unit1["Y"] - unit2["Y"], 2))/1000.

    def _id2unit(self, raw_obs, id_val):
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


class BlueReward(object):

    def __init__(self):
        self.last_a2a_num = -1
        self.last_a2g_num = -1
        self.last_awacs_num = -1
        self.last_en_a2a_num = -1
        self.last_en_a2g_num = -1
        self.last_en_ship_num = -1
        self.last_en_command_num = -1

    def _get_type_num_diff(self, raw_obs, side, type_, last_num):
        curr_num = get_type_num(raw_obs[side], [type_], consider_airport=True)
        diff = curr_num - last_num if last_num != -1 else 0
        return diff, curr_num

    def get(self, raw_obs):
        my_a2a_num_diff, my_a2a_num = self._get_type_num_diff(
                        raw_obs, 'blue', UnitType.A2A, self.last_a2a_num)
        self.last_a2a_num = my_a2a_num
        # print('a2a ', my_a2a_num, self.last_a2a_num, my_a2a_num_diff)

        my_a2g_num_diff, my_a2g_num = self._get_type_num_diff(
            raw_obs, 'blue', UnitType.A2G, self.last_a2g_num)
        self.last_a2g_num = my_a2g_num
        
        my_awacs_num_diff, my_awacs_num = self._get_type_num_diff(
            raw_obs, 'blue', UnitType.AWACS, self.last_awacs_num)
        self.last_awacs_num = my_awacs_num

        en_a2a_num_diff, en_a2a_num = self._get_type_num_diff(
            raw_obs, 'red', UnitType.A2A, self.last_en_a2a_num)
        self.last_en_a2a_num = en_a2a_num
        
        en_a2g_num_diff, en_a2g_num = self._get_type_num_diff(
            raw_obs, 'red', UnitType.A2G, self.last_en_a2g_num)
        self.last_en_a2g_num = en_a2g_num

        en_ship_num_diff, en_ship_num = self._get_type_num_diff(
            raw_obs, 'red', UnitType.SHIP, self.last_en_ship_num)
        self.last_en_ship_num = en_ship_num

        en_command_num_diff, en_command_num = self._get_type_num_diff(
            raw_obs, 'red', UnitType.COMMAND, self.last_en_command_num)
        self.last_en_command_num = en_command_num

        if raw_obs['sim_time'] > 5992. and en_command_num == 2:
            win_lose_penalize = 10
        else:
            win_lose_penalize = 0

        rew = my_a2a_num_diff * 0.5 + my_a2g_num_diff * 1 + en_a2a_num_diff * (-1) + en_a2g_num_diff * (-1) + \
            en_ship_num_diff * (-5) + en_command_num_diff * (-8) + my_awacs_num_diff * 5 + win_lose_penalize

        return rew