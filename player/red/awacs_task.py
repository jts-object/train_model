from env.env_def import UnitType, RED_AIRPORT_ID, MapInfo
from common.cmd import Command
from common.grid import MapGrid
from common.interface.base_rule import BaseRulePlayer
from common.interface.task import Task, TaskState
from common.units import Unit, A2G
from common.threat_analysis import ThreatAnalysis
from env.env_util import azimuth_angle

# from player.red import DisturbControl, ShipControl, Informer, unit_task_state
from player.red.informer import cal_unit_dis

from player.red.informer import Informer
from player.red.a2a_task import A2AControl
from player.red.a2g_task import A2GControl

import numpy as np
import math


class AwacsControl:
    """
    对于预警机的控制，保守思路去安全地带
    """
    def __init__(self):
        """
        歼击机的目的即是为轰炸机护航，围绕干扰机运动
        """
        self.info = Informer() 
        self.curr_patrol_point = {'X': 0, 'Y': 0, 'Z': 8000}  # 记录当前巡逻任务的中心点
        
        # self.task_state = 'patroling'
        # 给定目前的巡逻状态
        # PATROLING = 'patroling' 
        # REACH_PATROL_POINT = 'reach_patrol_point' 

        self.PATROL_PARAMS = [270, 10000, 10000, 160, 7200, 2]

    def update(self, obs_red):
        self.info.update(obs_red)
        self.awacs = self.info.awacs

    def patrol_to_safe(self, obs_red):
        patrol_point = self.find_safe_place(obs_red)
        cmd = []
        if self.awacs and self.curr_patrol_point != patrol_point:
            cmd.append(Command.awacs_areapatrol(self.awacs['ID'], [patrol_point['X'], patrol_point['Y'], patrol_point['Z']], self.PATROL_PARAMS))
            self.curr_patrol_point = patrol_point
        return cmd 

    # 在保证安全(距离最近单位 180 km)的基础上前出
    def find_safe_place(self, obs_red):
        patrol_point = self.curr_patrol_point
        if self.dis_nearest_unit(obs_red) > 200: 
            patrol_point = {'X': self.curr_patrol_point['X'] - 10000, 'Y': 10000, 'Z': 8000}
        elif self.dis_nearest_unit(obs_red) > 160: 
            patrol_point = self.curr_patrol_point 
        else: 
            patrol_point = {'X': self.curr_patrol_point['X'] + 10000, 'Y': 10000, 'Z': 8000}

        print('dis:{} and patrol point: {}'.format(self.dis_nearest_unit(obs_red), patrol_point))
        return patrol_point

    def dis_nearest_unit(self, obs_red):
        min_dis = 1e12
        if self.awacs is not None:
            for unit in obs_red['qb']:
                if unit['LX'] == UnitType.A2A or unit['LX'] == UnitType.SHIP or unit['LX'] == UnitType.S2A:
                    dis = cal_unit_dis(unit, self.curr_patrol_point)
                    if dis < min_dis:
                        min_dis = dis
        
        return min_dis

    # def reach_patrol_point(self, unit):
    #     if self.awacs and cal_unit_dis(self.awacs, self.curr_patrol_point) > 5:
    #         return False 
    #     return True 

    # 返回指令
    def gene_cmd(self, obs_red):
        cmd = []
        self.update(obs_red)
        cmd.extend(self.patrol_to_safe(obs_red))
        return cmd
        

