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
from player.red.a2a_task import A2AControl
from player.red.disturb_task import DisturbControl
from player.red.a2g_task import A2GControl
from player.red.informer import cal_unit_dis

import numpy as np
import math

class unionControl: 
    """
    实现电子战的调度控制，主要在歼击机、轰炸机和干扰机之间传递信息，还需修改：此类决定干扰机去哪，同时需要协调歼击机、轰炸机和干扰机之间的配合
    """
    def __init__(self):
        self.disturb_control = DisturbControl()
        self.a2a_control = A2AControl()
        self.a2g_control = A2GControl()

    def _update(self, obs_red):
        self.disturb_control.update(obs_red)
        self.a2a_control.update(obs_red)
        self.a2g_control.update(obs_red)
        
    def gene_cmd(self, obs_red, sim_time):
        self._update(obs_red)
        cmd = []

        a2a_gather_finish = self.a2a_control.does_gather_finish() 
        a2g_gather_finish = self.a2g_control.does_gather_finish()
        disturb_patrol_point = self.disturb_control.get_curr_point()

        cmd.extend(self.disturb_control.gene_cmd(obs_red, sim_time, a2a_gather_finish, a2g_gather_finish)) 
        cmd.extend(self.a2a_control.gene_cmd(obs_red, sim_time, disturb_patrol_point, self.disturb_control.target)) 
        cmd.extend(self.a2g_control.gene_cmd(obs_red, sim_time, disturb_patrol_point, self.disturb_control.target))
        
        return cmd 

