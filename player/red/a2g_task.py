from env.env_def import UnitType, RED_AIRPORT_ID, MapInfo
from common.cmd import Command
from common.grid import MapGrid
from common.interface.base_rule import BaseRulePlayer
from common.interface.task import Task, TaskState
from common.units import Unit, A2G
from common.threat_analysis import ThreatAnalysis
from env.env_util import azimuth_angle

from player.red.informer import Informer
from player.red.informer import cal_unit_dis

import numpy as np
import math


WAIT_PATROL = 'wait_patrol'
PATROLING = 'patroling'
REACH_PATROL_POINT = 'reach_patrol_point'
ATTACKING = 'attacking'
RETURNING = 'returning'


class A2GControl:
    def __init__(self):
        self.info = Informer()
        
        self.target_map = None    # 给定当前单位打击敌方单位的映射
        self.curr_point = None    # 给定初始的巡逻位点
        self.disturb_point = None

        self.unit_task_state = {}   # 单位所处状态
        self.team_task = {}         # 编队所处状态
        self.unit_point_map = {}    # 为每一个编队分配一个巡逻位点
        self.gather_finish = False  # 编队中所有单位是否集结完成

    def update(self, obs_red):
        self.info.update(obs_red)
        self.update_state(obs_red)
    
    def set_curr_target(self, obs_red):
        pass
    
    def set_patrol_point(self, disturb_point):
        self.disturb_point = disturb_point

    # 判断 unit 是否到达目前干扰机附近的指定位点，如果干扰机不存在则不需要作此判断
    def reach_patrol_point(self, unit):
        if unit['TMID'] in self.unit_point_map.keys():
            patrol_point = self.unit_point_map[unit['TMID']]
            if cal_unit_dis(unit, patrol_point) > 5:
                return False 
        return True 

    # 判断歼击机是否集结完成，如果完成了则将 self.gather_finish 置为True
    def does_gather_finish(self):
        if len(self.team_task) == 0:
            return False 

        # for task_value in self.unit_task.values():
        for task_value in self.team_task.values():
            if task_value != REACH_PATROL_POINT:
                return False 

        self.gather_finish = True
        return self.gather_finish

    def update_state(self, obs_red):
        # unit_in_air = [unit['ID'] for unit in obs_red['units']]
        # 更新单位状态和编队状态
        # 移除当前不存在的编队和单位
        # delete_unit = []
        delete_team = []
        for team_id in self.team_task.keys():
            if team_id not in self.info.a2g_team_unit_map.keys():
                delete_team.append(team_id)

        for tid in delete_team:
            del self.team_task[tid]
        
        delete_team = []
        for team_id in self.unit_point_map.keys():
            if team_id not in self.info.a2g_team_unit_map.keys():
                delete_team.append(team_id)
        for tid in delete_team:
            del self.unit_point_map[tid]

        # for unit_id in self.unit_task_state.keys():
        #     # 不在空中单位即将其从中删除
        #     if unit_id not in unit_in_air:
        #         delete_unit.append(unit_id) 

        # for uid in delete_unit:
        #     del self.unit_task_state[uid]


        # 如果 self.gather_finish 的值为真，则将其置为假。不然 union_task 无法工作，因此每次只有一个 step 的时间内才有 self.gather_finish = True
        if self.gather_finish:
            self.gather_finish = False 
            for unit in obs_red['units']:
                if unit['LX'] == UnitType.A2G:
                    self.team_task[unit['TMID']] = WAIT_PATROL
            self.unit_point_map.clear()

        # 更新返航补弹飞机的任务状态，在满弹的时候置为 2 
        for uid in self.unit_task_state.keys():
            bomb = self.info._id2unit(obs_red, uid, is_enermy=False)
            if bomb and self.unit_task_state[uid] == 4 and bomb['WP']['360'] == 2:
                self.unit_task_state[uid] = 2 

    # 从当前轰炸机编队中找到离目标平均距离最近的编队
    def closest_team(self, obs_red, target):
        team_distance_map = {}
        for team, units in self.info.a2g_team_unit_map.items():
            ave_dis, num_a2g = 0, len(units)
            for unit in units:
                ave_dis += cal_unit_dis(unit, target)
            team_distance_map[team] = ave_dis/num_a2g
        # 按照距离排序
        team_distance_map = dict(sorted(team_distance_map.items(), key=lambda item: item[1]))
        return list(team_distance_map.keys())[0]

    # 1:处于打击状态，且剩一枚弹；0: 两枚弹都发出去了，2: 巡逻；3: 处于逃逸状态，4: 接受返航指令的状态
    def attack_ship(self, obs, target):
        cmd  = []

        def condition_satisfied_attack(unit):
            if cal_unit_dis(unit, target) < 110 and unit['ID'] not in self.info.rocket_target:
                if unit['ID'] in self.unit_task_state.keys() and self.unit_task_state[unit['ID']] == 2:
                    self.unit_task_state[unit['ID']] = 1 
                    direction = self.info.get_attack_direction(target, unit)
                    cmd.append(Command.target_hunt(unit['ID'], target['ID'], 90, direction))
        
        def not_condition_satisfied_approach(unit):
            if cal_unit_dis(unit, target) > 110 and unit['ID'] not in self.info.rocket_target:
                if unit['ID'] not in self.unit_task_state.keys() or self.unit_task_state[unit['ID']] == 2:
                    self.unit_task_state[unit['ID']] = 2    # 表示目前接受巡逻任务
                    center_point = [target['X'], target['Y'], target['Z']]
                    cmd.append(Command.area_patrol(unit['ID'], center_point))

        def escape_rocket(unit):
            if unit['ID'] in self.info.rocket_target:
                escape_point = self.info.get_escape_point(unit)
                self.unit_task_state[unit['ID']] = 3
                if escape_point is not None:
                    cmd.append(Command.area_patrol(unit['ID'], escape_point))
                    self.unit_task_state[unit['ID']] = 3 

        def second_attack(unit):
            if unit['WP']['360'] == 1 and self.unit_task_state[unit['ID']] == 1:
                direction = self.info.get_attack_direction(target, unit)
                cmd.append(Command.target_hunt(unit['ID'], target['ID'], 90, direction))
                self.unit_task_state[unit['ID']] = 0 


        attack_team = self.closest_team(obs, target)
        self.team_task[attack_team] = ATTACKING 
        for unit in self.info.a2g_team_unit_map[attack_team]:
            if unit['WP']['360'] == 0:
                self.unit_task_state[unit['ID']] = 4
                cmd.append(Command.return2base(unit['ID'], RED_AIRPORT_ID))
            else:
                condition_satisfied_attack(unit)
                not_condition_satisfied_approach(unit)
                # escape_rocket(unit)
                second_attack(unit)

                # if self.unit_task_state[unit['ID']] == 3 and cal_unit_dis(unit, target) > 155:
                #     print('unit accept approach task: ', unit['ID'])
                #     self.rocket_target.remove(unit['ID'])
                #     self.unit_task_state[unit['ID']] = 2

        return cmd 

    def attack_command(self, obs, target):
        cmd = []

        for team, units in self.info.a2g_team_unit_map.items():
            for unit in units:
                if cal_unit_dis(unit, target) > 110:
                    if (unit['ID'] in self.unit_task_state.keys() and self.unit_task_state[unit['ID']] == 2) or (unit['ID'] not in self.unit_task_state.keys()):
                        center_point = [target['X'], target['Y'], target['Z']]
                        cmd.append(Command.area_patrol(unit['ID'], center_point))
                        self.unit_task_state[unit['ID']] = 2
                else:
                    # 接受第一次打击任务
                    if unit['ID'] not in self.unit_task_state.keys() or self.unit_task_state[unit['ID']] == 2:
                        self.unit_task_state[unit['ID']] = 1
                        direction = self.info.get_attack_direction(target, unit)
                        cmd.append(Command.target_hunt(unit['ID'], target['ID'], 90, direction))

                    # 接受第二次打击任务，此时表明该单位的导弹发出去一枚，继续对同一个指挥所进行打击 
                    if unit['WP']['360'] == 1 and self.unit_task_state[unit['ID']] == 1:
                        self.unit_task_state[unit['ID']] = 0 
                        direction = self.info.get_attack_direction(target, unit) 
                        cmd.append(Command.target_hunt(unit['ID'], target['ID'], 90, direction)) 

        return cmd 

    def a2g_return(self, obs_red):
        cmd = []
        for unit in obs_red['units']:
            if unit['LX'] == UnitType.A2G and unit['WP']['360'] == 0:
                if unit['ID'] in self.unit_task_state and self.unit_task_state[unit['ID']] != 4:
                    cmd.append(Command.return2base(unit['ID'], RED_AIRPORT_ID))
                    self.unit_task_state[unit['ID']] = 4 
        return cmd

    def set_team_patrol_point(self, team_id, num_a2g):
        patrol_x = self.disturb_point['X'] + 15000 * math.cos(math.pi/2 + 40 * num_a2g * math.pi/180)
        patrol_y = self.disturb_point['Y'] + 15000 * math.sin(math.pi/2 + 40 * num_a2g * math.pi/180)
        patrol_z = 8000 
        unit_patrol_point = {'X': patrol_x, 'Y': patrol_y, 'Z': patrol_z}
        self.unit_point_map[team_id] = unit_patrol_point
        return [patrol_x, patrol_y, patrol_z]

    # 返回指令
    def gene_cmd(self, obs_red, sim_time, disturb_curr_point=None, target=None):
        cmd = []
        self.update(obs_red)
        self.set_patrol_point(disturb_curr_point)
        patrol_param = [90, 5000, 5000, 200, 7200]
        
        # 轰炸机需要按照编队控制去打击指挥所和船，改成编队控制
        if self.disturb_point is not None and sim_time > self.info.START_WAIT_TIME:
            num_a2g = 0 
            if target is not None:
                if target['LX'] == UnitType.SHIP:
                    cmd.extend(self.attack_ship(obs_red, target))

            for team_id in self.info.a2g_team_unit_map:
                num_a2g += 1 
                # 对应到初始没记录状态的情况
                # if unit['ID'] not in self.unit_task.keys():
                #     self.unit_task[unit['ID']] = WAIT_PATROL
                if team_id not in self.team_task.keys():
                    if self.info.a2g_team_unit_map[team_id][0]['X'] < 160000:
                        self.team_task[team_id] = WAIT_PATROL

                elif self.team_task[team_id] == WAIT_PATROL:
                    patrol_point = self.set_team_patrol_point(team_id, num_a2g)
                    for unit in self.info.a2g_team_unit_map[team_id]:
                        # print('unit id {} and team id {}'.format(unit['ID'], unit['TMID']))
                        # if unit['ID'] in self.unit_task_state.keys():
                        #     print('unit_task_state:', self.unit_task_state[unit['ID']])
                        if unit['ID'] not in self.unit_task_state.keys() or self.unit_task_state[unit['ID']] != 4:
                            # print(Command.area_patrol(unit['ID'], patrol_point, patrol_param))
                            cmd.append(Command.area_patrol(unit['ID'], patrol_point, patrol_param))
                    self.team_task[team_id] = PATROLING 
                    
                elif self.team_task[team_id] == PATROLING:
                    # 判断编队是否到达指定位置 
                    team_reach_point = True 
                    for unit in self.info.a2g_team_unit_map[team_id]:
                        # 只考虑不在返航的飞机是否到达指定位置
                        if unit['ID'] in self.unit_task_state.keys() and self.unit_task_state[unit['ID']] != 4:
                            team_reach_point = team_reach_point and self.reach_patrol_point(unit)
                    if team_reach_point: 
                        self.team_task[team_id] = REACH_PATROL_POINT 
                    
                if target is None and team_id in self.team_task.keys() and self.team_task[team_id] == ATTACKING:
                    self.team_task[team_id] = WAIT_PATROL

            # 更新self.gather_finish
            # self.update_state(obs_red)

        # for item in self.team_task.items():
        #     print('team task: ', item)

        # for team, units in self.info.a2g_team_unit_map.items():
        #     print('team id:{} and num of units:{}'.format(team, len(units)))
        

        cmd.extend(self.a2g_return(obs_red))

        # if target['LX'] == UnitType.COMMAND:
            # cmd.extend(self.attack_command(obs_red, target))
        # if self.disturb_point is None:

        return cmd 
