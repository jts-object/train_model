from env.env_def import UnitType, RED_AIRPORT_ID, MapInfo
from common.cmd import Command
from common.grid import MapGrid
from common.interface.base_rule import BaseRulePlayer
from common.interface.task import Task, TaskState
from common.units import Unit, A2G
from common.threat_analysis import ThreatAnalysis
from env.env_util import azimuth_angle
from env.env_cmd import EnvCmd

from player.red.informer import Informer
from player.red.informer import cal_unit_dis

import numpy as np
import math


WAITING_GATHER = 'waiting_gather'
START_PATROL = 'start_patrol'
PATROLING = 'patroling'
SUPPORT_ATTACK = 'support_attack'
REACH_PATROL_POINT = 'reach_patrol_point'


class DisturbControl:
    def __init__(self):
        self.info = Informer()

        self.curr_target = None 
        self.target = None 
        self.is_target_alive = True 
        self.curr_point = {'X': 175000, 'Y': 40000, 'Z': 8000}    # 给定初始的巡逻位点
        self.unit_task = None  


    def update(self, obs_red):
        self.info.update(obs_red)
        self.disturb = self.info.disturb
        if self.disturb is not None and self.unit_task is None:
            self.unit_task = START_PATROL 
        if self.target is None:
            self.target = self.closest_target()
        else:
            alive_ship_id = [unit['ID'] for unit in self.info.en_ships]
            alive_comm_id = [unit['ID'] for unit in self.info.en_commands]

            if self.target['ID'] not in alive_ship_id and self.target['ID'] not in alive_comm_id:
                self.target = None 

    # 逻辑如何设置，到底是船存活就打船还是需要根据态势进行危险预估？
    def set_curr_target(self, obs_red):
        if self.target is None:
            for unit in obs_red['qb']:
                if unit['LX'] == UnitType.SHIP or unit['LX'] == UnitType.COMMAND:
                    pass 
                    # self.unit_task = SUPPORT_ATTACK 
    
    # 得到干扰机的前进路线 
    def get_next_point(self, obs_red): 
        temp = {'X': self.curr_point['X'] - 20000, 'Y': 0, 'Z': 0}
        return temp
    
    # 干扰机是否到达指定位点
    @property 
    def reach_patrol_point(self):
        if self.disturb and self.curr_point:
            if cal_unit_dis(self.disturb, self.curr_point) < 4.5:     # 小于 4.5 km 即认为在区域巡逻的航线上了，区域巡逻长宽定为 5 
                return True 
        
        return False 

    def get_curr_point(self):
        return self.curr_point

    def closest_target(self):
        for ship in self.info.en_ships:
            if self.info.disturb and cal_unit_dis(ship, self.info.disturb) < 150:
                return ship 
        
        for comm in self.info.en_commands:
            if self.info.disturb and cal_unit_dis(comm, self.info.disturb) < 150:
                return comm 

        return None 
    
    # 返回指令
    def gene_cmd(self, obs_red, sim_time, a2a_gather_finish=False, a2g_gather_finish=False):
        cmd = []
        self.update(obs_red)

        if sim_time > self.info.START_WAIT_TIME:
            if self.unit_task == START_PATROL and self.disturb is not None:
                patrol_point = [self.curr_point['X'], self.curr_point['Y'], self.curr_point['Z']]
                patrol_param = [90, 5000, 5000, 200, 9000]
                cmd.append(EnvCmd.make_disturb_areapatrol(self.disturb['ID'], *patrol_point, *patrol_param))
                self.unit_task = PATROLING 
                # cmd.append(Command.area_patrol(self.disturb['ID'], patrol_point, patrol_param))
            
            if self.reach_patrol_point and self.unit_task == PATROLING:
                self.unit_task = WAITING_GATHER
            
            if self.unit_task == WAITING_GATHER and a2a_gather_finish and a2g_gather_finish:
                self.curr_point = self.get_next_point(obs_red)
                self.unit_task = START_PATROL

            if self.target is not None:
                if self.unit_task != SUPPORT_ATTACK:
                    patrol_param = [90, 5000, 5000, 200, 9000]
                    support_point = [self.info.disturb['X'] + 3000, self.info.disturb['Y'], self.info.disturb['Z']]
                    cmd.append(Command.area_patrol(self.disturb['ID'], support_point, patrol_param))
                
                self.unit_task = SUPPORT_ATTACK 

            if self.target is None and self.unit_task == SUPPORT_ATTACK:
                self.unit_task = START_PATROL

            print('sim_time {} and disturb unit task {}'.format(sim_time, self.unit_task))
        
        return cmd 

