
from env.env_def import UnitType, RED_AIRPORT_ID, MapInfo
from common.cmd import Command
from common.grid import MapGrid
from common.interface.base_rule import BaseRulePlayer
from common.interface.task import Task, TaskState
from common.units import Unit, A2G
from common.threat_analysis import ThreatAnalysis
from env.env_util import azimuth_angle

from player.red.disturb_task import DisturbControl
from player.red.union_task import unionControl
from player.red.awacs_task import AwacsControl

import numpy as np
import math

A2A_PATROL_PARAMS = [270, 10000, 10000, 250, 7200]


class unit_task_state:
    ESCAPE = 0
    ATTACK = 1
    PATROL = 2


class A2GTask(Task):
    def __init__(self, max_unit_num, fire_range, start_time, map_grid, task_state=TaskState.PREPARE):
        super().__init__(task_state)
        self.max_unit_num = max_unit_num
        self.fire_range = fire_range
        self.target_unit = None
        self.start_time = start_time
        self.map_grid = map_grid

        self.is_ship_found = False
        self.target_ship = None
        self.rockets = None 
        self.rocket_target = set()
        self.team_unit_map = {}
        self.unit_task_state = {}   # 还需要记录每个单位是否在逃跑之中了，迪士尼在逃单位; 0-逃跑中，1-打击中，2-巡逻中
        self.target_command = None 
        # self._init_state()
        self.potrol_point = [0, 0, 0]
    
    def _init_state(self, obs):
        pass 

    def get_all_missiles(self):
        missile_num = 0
        for _, unit in self.units_map.items():
            missile_num += unit.get_missile_num() 
        return missile_num

    def update(self, alive_unit_map, obs):
        self.update_units_map(alive_unit_map)
        # self.update_task_state(obs)

    def run(self, idle_unit_map, threat_matrix):
        cmds = []
        if self.task_state == TaskState.START: 
            while len(self.units_map) < self.max_unit_num or self.get_all_missiles() < self.max_unit_num * 2: 
                if len(idle_unit_map) == 0:
                    break
                unit = idle_unit_map.popitem()[1]
                self.add_unit(unit)
            for _, unit in self.units_map.items():
                if unit.get_missile_num() != 0:
                    cmd_list = self.astar_task_run(unit, threat_matrix)
                    cmds.extend(cmd_list)
                else:
                    cmds.append(Command.return2base(unit.id, RED_AIRPORT_ID))
        elif self.task_state == TaskState.FINISH:
            for unit_id, unit in self.units_map.items():
                if unit.get_missile_num() != 0: 
                    cmds.append(Command.return2base(unit_id, RED_AIRPORT_ID))
            self.finish()
        return cmds
 
    def astar_task_run(self, unit, threat_matrix):
        cmds = []

        end_point_x, end_point_y = self.map_grid.get_idx(self.target_unit.x, self.target_unit.y)
        end_point = [end_point_x, end_point_y]
        path = unit.astar_path_finding(threat_matrix, end_point, self.map_grid)
        # 找到路径
        if len(path) > 1:
            x, y = self.map_grid.get_center(path[1][0], path[1][1])
            cmds.append(Command.area_patrol(unit.id, [x, y, 8000], A2A_PATROL_PARAMS))
    
        if unit.compute_2d_distance_unit(self.target_unit) < 100000:
            direction = azimuth_angle(unit.x, unit.y, self.target_unit.x, self.target_unit.y)
            cmds.append(Command.target_hunt(unit.id, self.target_unit.id, fire_range=100, direction=direction))

        return cmds

    def update_info(self, obs):
        for unit in obs['qb']:
            if unit['LX'] == UnitType.SHIP:
                self.is_ship_found = True 
                if self.target_ship is None:
                    self.target_ship = unit 
            if unit['LX'] == UnitType.COMMAND and self.target_command is None:
                self.target_command = unit 
            
        self.team_unit_map = {}
        for unit in obs['units']:
            if unit['LX'] == UnitType.A2G:
                self.patrol_point = [unit['X'] - 10000, unit['Y'], unit['Z']]
                if unit['TMID'] not in self.team_unit_map.keys():
                    self.team_unit_map[unit['TMID']] = [unit]
                else:
                    self.team_unit_map[unit['TMID']].append(unit)

        self.rockets = obs['rockets']

        # 只安排两架飞机逃离
        # if len(self.rocket_target) < 2:
        #     for rocket in self.rockets:
        #         self.rocket_target.add(rocket['N2'])

    
    # 返回满足条件的编队，目前只是返回距离在 150 km的编队
    def select_team(self, obs):
        team_id = None
        for team, units in self.team_unit_map.items():
            if self.cal_unit_dis(units[0], self.target_ship) < 150:
                team_id = team 
                return team_id, True
        
        return team_id, False

    # 计算每一个被指定单位的逃脱位点
    def get_escape_point(self, rockets, unit):
        for rocket in rockets:
            if rocket['N2'] == unit['ID']:
                angel = rocket['HX']/180. * math.pi + 90 # 看看偏折 45 度是否可以躲开
                patrol_x = unit['X'] + 100000 * math.sin(angel)
                patrol_y = unit['Y'] + 100000 * math.cos(angel)
                patrol_z = 8000

                return [patrol_x, patrol_y, patrol_z]

        return None 

    def get_attack_direction(self, target, unit):
        # 余弦定理
        a = 1
        b = math.sqrt(math.pow(target['X'] - unit['X'], 2) + math.pow(target['Y'] - unit['Y'], 2))
        c = math.sqrt(math.pow(unit['X'] - target['X'], 2) + math.pow(unit['Y'] - (target['Y'] + 1), 2))
        cos_theta = (a * a + b * b - c * c)/(2 *a * b)
        if unit['X'] >= target['X']:
            direction = math.acos(cos_theta) * 180./math.pi
            direction = 180 + direction
        else:
            direction = 180 - math.acos(cos_theta) * 180./math.pi

        return direction


    def attack_ship(self, obs):
        cmd  = []
        self.update_info(obs)

        # 1:处于打击状态，且剩一枚弹；0:两枚弹都发出去了，2:巡逻；3:处于逃逸状态
        if self.is_ship_found:
            for team, units in self.team_unit_map.items():
                for unit in units:
                    if self.cal_unit_dis(unit, self.target_ship) < 50 and unit['ID'] not in self.rocket_target:
                        if unit['ID'] in self.unit_task_state.keys() and self.unit_task_state[unit['ID']] == 2:
                            print('unit accept attack task: ', unit['ID'])
                            self.unit_task_state[unit['ID']] = 1
                            direction = self.get_attack_direction(self.target_ship, unit)
                            cmd.append(Command.target_hunt(unit['ID'], self.target_ship['ID'], 90, direction))
                    if self.cal_unit_dis(unit, self.target_ship) > 50 and unit['ID'] not in self.rocket_target:
                        if unit['ID'] in self.unit_task_state.keys() and self.unit_task_state[unit['ID']] == 2:
                            print('unit accept patrol task: ', unit['ID'])
                            self.unit_task_state[unit['ID']] = 2    # 表示目前接受巡逻任务
                            center_point = [self.target_ship['X'], self.target_ship['Y'], self.target_ship['Z']]
                            cmd.append(Command.area_patrol(unit['ID'], center_point))
                    if unit['ID'] in self.rocket_target:
                        print('unit accept escape task: ', unit['ID'])
                        escape_point = self.get_escape_point(self.rockets, unit)
                        self.unit_task_state[unit['ID']] = 3
                        for rocket in self.rockets:
                            print('rocket info', rocket)
                        if escape_point is not None:
                            cmd.append(Command.area_patrol(unit['ID'], escape_point))
                            self.unit_task_state[unit['ID']] = 3
                    if unit['WP']['360'] == 1 and self.unit_task_state[unit['ID']] == 1:
                        direction = self.get_attack_direction(self.target_ship, unit)
                        cmd.append(Command.target_hunt(unit['ID'], self.target_ship['ID'], 90, direction))
                        self.unit_task_state[unit['ID']] = 0
                    if self.unit_task_state[unit['ID']] == 3 and self.cal_unit_dis(unit, self.target_ship) > 155:
                        print('unit accept approach task: ', unit['ID'])
                        self.rocket_target.remove(unit['ID'])
                        self.unit_task_state[unit['ID']] = 2
      
        else:
            # TODO: 修改确定巡逻位点的逻辑
            for team in self.team_unit_map.keys():
                center_point = self.patrol_point
                cmd.append(Command.area_patrol(team, center_point))
                for unit in self.team_unit_map[team]:
                    self.unit_task_state[unit['ID']] = 2

        return cmd

    def attack_command(self, obs):
        cmd = []
        self.update_info(obs)

        if self.target_command is not None:
            for team, units in self.team_unit_map.items():
                for unit in units:
                    if self.cal_unit_dis(unit, self.target_command) > 110:
                        if (unit['ID'] in self.unit_task_state.keys() and self.unit_task_state[unit['ID']] == 2) or (unit['ID'] not in self.unit_task_state.keys()):
                            center_point = [self.target_command['X'], self.target_command['Y'], self.target_command['Z']]
                            cmd.append(Command.area_patrol(unit['ID'], center_point))
                            self.unit_task_state[unit['ID']] = 2
                    else:
                        # 接受第一次打击任务
                        if unit['ID'] not in self.unit_task_state.keys() or self.unit_task_state[unit['ID']] == 2:
                            self.unit_task_state[unit['ID']] = 1
                            direction = self.get_attack_direction(self.target_command, unit)
                            cmd.append(Command.target_hunt(unit['ID'], self.target_command['ID'], 90, direction))

                        # 接受第二次打击任务，此时表明该单位的导弹发出去一枚，继续对同一个指挥所进行打击
                        if unit['WP']['360'] == 1 and self.unit_task_state[unit['ID']] == 1:
                            self.unit_task_state[unit['ID']] = 0
                            direction = self.get_attack_direction(self.target_command, unit)
                            cmd.append(Command.target_hunt(unit['ID'], self.target_command['ID'], 90, direction))

        return cmd 

    def cal_unit_dis(self, unit1, unit2):
        return math.sqrt(math.pow(unit1["X"] - unit2["X"], 2) + math.pow(unit1["Y"] - unit2["Y"], 2))/1000.
    

class OneForAllA2gTask(A2GTask):
    def __init__(self, max_unit_num, fire_range, start_time, map_grid):
        super().__init__(max_unit_num, fire_range, start_time, map_grid)
    
    def update_task_state(self, raw_obs):
        self.target_unit = None
        for unit in raw_obs['red']['qb']:
            if unit['LX'] == UnitType.SHIP:
                self.target_unit = Unit(unit)
                break
            if unit['LX'] == UnitType.COMMAND:
                if unit['Y'] > 0:
                    self.target_unit = Unit(unit)
                    break
                else:
                    self.target_unit = Unit(unit)
    
        if self.target_unit is None:
            self.task_state = TaskState.FINISH
        else:
            if raw_obs['sim_time'] > self.start_time:
                self.task_state = TaskState.START


class RulePlayer(BaseRulePlayer):

    def __init__(self, side):
        super().__init__(side)
        self.map_grid = MapGrid(
            (MapInfo.X_MIN, MapInfo.Y_MAX), (MapInfo.X_MAX, MapInfo.Y_MIN), 20, 20)
        self.a2g_task = OneForAllA2gTask(6, 100, 500, self.map_grid)
        # A*算法时，只考虑了歼击机的威胁，没有考虑舰船和地防的威胁（有可能无法避免）
        self.threat_analysis = ThreatAnalysis(self.map_grid, {UnitType.A2A: 100000})
        
        # added by jts
        self.flag = True
        self.disturb_control = DisturbControl()
        self.union_control = unionControl()
        self.awacs_control = AwacsControl()


    def _take_off(self, raw_obs):
        cmds = []

        # 用于起飞多类型飞机
        # fly_types = [UnitType.A2A, UnitType.A2G, UnitType.JAM]
        for type_ in [UnitType.A2A, UnitType.A2G]:
            num = min(self._get_waiting_aircraft_num(raw_obs, type_), 4)
            # if self._get_waiting_aircraft_num(raw_obs, type_):
            if num:
                cmds.append(Command.takeoff_areapatrol(RED_AIRPORT_ID, num, type_))

        # 用于单次起飞几架飞机
        if self.flag:
            cmds.append(Command.takeoff_areapatrol(RED_AIRPORT_ID, 1, UnitType.A2G))
            cmds.append(Command.takeoff_areapatrol(RED_AIRPORT_ID, 1, UnitType.DISTURB))
            self.flag = False 

        return cmds

    def _awacs_task(self, raw_obs):
        cmds = []
        patrol_points = [0, 0, 8000]
        # TODO(zhoufan): 是否应该将awacs的id缓存起来
        for unit in raw_obs[self.side]['units']:
            if unit['LX'] == UnitType.AWACS:
                cmds.append(
                    Command.awacs_areapatrol(
                        unit['ID'], patrol_points))
                break
        return cmds
    
    def _get_units_map(self, raw_obs, type_):
        units_map = {}
        for info_map in raw_obs[self.side]['units']:
            if info_map['LX'] == type_:
                units_map[info_map['ID']] = A2G(info_map)
        return units_map

    def step(self, raw_obs):
        cmds = []
        cmds.extend(self._take_off(raw_obs))
        # cmds.extend(self._awacs_task(raw_obs))

        # 基于规则的电子战 

        cmds.extend(self.union_control.gene_cmd(raw_obs['red'], raw_obs['sim_time']))
        cmds.extend(self.awacs_control.gene_cmd(raw_obs['red']))

        # if raw_obs['sim_time'] > 3000:
        #     for cmd in cmds:
        #         print(cmd) 

        # a2g_map = self._get_units_map(raw_obs, UnitType.A2G)
        # self.a2g_task.update(a2g_map, raw_obs)
        # for unit_id, _ in self.a2g_task.get_units_map().items():
        #     a2g_map.pop(unit_id)
        # threat_matrix = self.threat_analysis.get_threat_matrix(raw_obs[self.side])

        # print(raw_obs['red']['rockets'])
        # print(raw_obs['blue']['rockets'])

        # print(threat_matrix)
        # threat_matrix = np.ones((self.map_grid.x_n, self.map_grid.y_n))
        # cmds.extend(self.a2g_task.run(a2g_map, threat_matrix))
        # patrol_cmds = [cmd for cmd in cmds if 'patrol'in cmd['maintype']]
        # print('total, patrol, else', len(cmds), len(patrol_cmds), len(cmds)-len(patrol_cmds))

        return cmds
