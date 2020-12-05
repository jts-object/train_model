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


REACH_PATROL_POINT = 'reach_patrol_point'
WAIT_PATROL = 'wait_patrol'
PATROLING = 'patroling'
ATTACKING = 'attacking'
RETURNING = 'returning'


class A2AControl:
    def __init__(self):
        self.info = Informer()
        
        self.target_map = None    # 给定当前单位打击敌方单位的映射
        self.curr_point = None    # 给定初始的巡逻位点

        self.unit_task = {}
        self.gather_finish = False
        self.unit_point_map = {}
        self.disturb_point = None 

    def update(self, obs_red):
        self.info.update(obs_red)
    
    def set_curr_target(self, obs_red):
        pass
    
    def set_patrol_point(self, disturb_point):
        self.disturb_point = disturb_point

    # 判断 unit 是否到达目前干扰机附近的指定位点，如果干扰机不存在则不需要作此判断
    def reach_patrol_point(self, unit):
        if unit['ID'] in self.unit_point_map.keys():
            patrol_point = self.unit_point_map[unit['ID']]
            if cal_unit_dis(unit, patrol_point) > 5:
                return False 
        return True 

    # 判断歼击机是否集结完成，如果完成了则将 self.gather_finish 置为True
    def does_gather_finish(self):
        if len(self.unit_task) == 0:
            return False 

        for task_value in self.unit_task.values():
            if task_value != REACH_PATROL_POINT:
                return False

        self.gather_finish = True
        return self.gather_finish

    def update_state(self, obs_red):
        # 如果self.gather_finish的值为真，则将其置为假。不然 union_task 无法工作，因此每次只有一个 step 的时间内才有 self.gather_finish = True
        if self.gather_finish:
            self.gather_finish = False 
            for unit in obs_red['units']:
                if unit['LX'] == UnitType.A2A:
                    self.unit_task[unit['ID']] = WAIT_PATROL
            self.unit_point_map.clear()

    # 返回指令
    def gene_cmd(self, obs_red, sim_time, disturb_curr_point=None, target=None):
        cmd = []
        self.update(obs_red)
        self.set_patrol_point(disturb_curr_point)

        patrol_param = [90, 5000, 5000, 200, 7200]
        
        # 600 s 是为了保证飞机都飞起来了
        if self.disturb_point is not None and sim_time > self.info.START_WAIT_TIME:
            num_a2a = 0
            for unit in obs_red['units']:
                if unit['LX'] == UnitType.A2A:
                    num_a2a += 1
                    # 对应到初始没记录状态的情况
                    if unit['ID'] not in self.unit_task.keys():
                        self.unit_task[unit['ID']] = WAIT_PATROL

                    elif self.unit_task[unit['ID']] == WAIT_PATROL:
                        patrol_x = self.disturb_point['X'] + 25000 * math.cos(math.pi/2 + 7.5 * num_a2a * math.pi/180)
                        patrol_y = self.disturb_point['Y'] + 25000 * math.sin(math.pi/2 + 7.5 * num_a2a * math.pi/180)
                        patrol_z = 8000 
                        unit_patrol_point = {'X': patrol_x, 'Y': patrol_y, 'Z': patrol_z} 
                        self.unit_point_map[unit['ID']] = unit_patrol_point 
                        cmd.append(Command.area_patrol(unit['ID'], [patrol_x, patrol_y, patrol_z], patrol_param))
                        self.unit_task[unit['ID']] = PATROLING

                    elif self.unit_task[unit['ID']] == PATROLING:
                        if self.reach_patrol_point(unit):
                            self.unit_task[unit['ID']] = REACH_PATROL_POINT
    
            # 更新self.gather_finish
            self.update_state(obs_red)

        # if self.patrol_point is None:

        return cmd 

