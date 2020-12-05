from env.env_def import UnitType, RED_AIRPORT_ID, MapInfo
from common.cmd import Command
from common.grid import MapGrid
from common.interface.base_rule import BaseRulePlayer
from common.interface.task import Task, TaskState
from common.units import Unit, A2G
from common.threat_analysis import ThreatAnalysis
from env.env_util import azimuth_angle

import numpy as np
import math

class PLANE_TASK_STATE:
    PATROLING = 'patroling'
    WAIT_PATROL = 'wait_patrol'
    GATHER = 'wait_gather'
    LOCKED = 'locked'
    ESCAPE = 'escape'
    RETURNING = 'returning'
    ATTACKING = 'attacking'


class Informer:
    """
    将态势信息转换为其它友方单位需要的形式，同时包含一些通用的计算
    """
    def __init__(self):
        # self.team_unit_map = {}         # TMID -> [unit1, unit2 ...] 的映射
        self.a2g_team_unit_map = {}
        self.a2a_team_unit_map = {}
        self.en_ships = []              # 敌方船的位置
        self.en_commands = []           # 敌方指挥所的位置
        self.rocket_target = set()      # 我方被锁定的单位编号

        self.awacs = None 
        self.disturb = None 

        self.START_WAIT_TIME = 600

    def update(self, obs_red):
        self.en_ships.clear()
        self.en_commands.clear()
        for unit in obs_red['qb']:
            if unit['LX'] == UnitType.SHIP and unit not in self.en_ships:
                self.en_ships.append(unit)
            if unit['LX'] == UnitType.COMMAND and unit not in self.en_commands:
                self.en_commands.append(unit)
        
        # 更新导弹信息和我方被锁定的单位信息
        self.rockets = obs_red['rockets']
        self.rocket_target.clear()
        for rocket in self.rockets:
            self.rocket_target.add(rocket['N2'])

        # 更新 self.team_unit_map 的值
        self.a2a_team_unit_map.clear()
        self.a2g_team_unit_map.clear()
        for unit in obs_red['units']:
            if unit['LX'] == UnitType.A2A:
                if unit['TMID'] not in self.a2a_team_unit_map.keys():
                    self.a2a_team_unit_map[unit['TMID']] = [unit]
                else:
                    self.a2a_team_unit_map[unit['TMID']].append(unit)
            
            if unit['LX'] == UnitType.A2G:
                if unit['TMID'] not in self.a2g_team_unit_map.keys():
                    self.a2g_team_unit_map[unit['TMID']] = [unit]
                else:
                    self.a2g_team_unit_map[unit['TMID']].append(unit)
            
        # 更新预警机和干扰机
        self.awacs = next((unit for unit in obs_red['units'] if unit['LX'] == UnitType.AWACS), None)
        self.disturb = next((unit for unit in obs_red['units'] if unit['LX'] == UnitType.DISTURB), None)

    
    # 计算被导弹指定单位的逃脱位点
    def get_escape_point(self, unit): 
        for rocket in self.rockets: 
            if rocket['N2'] == unit['ID']: 
                angel = rocket['HX']/180. * math.pi
                patrol_x = unit['X'] + 60000 * math.sin(angel)
                patrol_y = unit['Y'] + 60000 * math.cos(angel)
                patrol_z = 8000 

                return [patrol_x, patrol_y, patrol_z] 

        return None 

    # 余弦定理计算轰炸机攻击角度，target 是目标，unit 是实施打击的我方轰炸机
    def get_attack_direction(self, target, unit): 
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

    # 返回 uid -> unit 的映射
    def _id2unit(self, obs_red, id_val, is_enermy):
        if is_enermy:
            for unit in obs_red["qb"]:
                if unit["ID"] == id_val:
                    return unit
        else:
            for unit in obs_red["units"]:
                if unit["ID"] == id_val:
                    return unit 
        return None 

    # 返回 单位ID -> 编队ID 的映射
    def unit2team(self, obs_red):
        unit_team_map = {}
        for unit in obs_red['units']:
            unit_team_map[unit['ID']] = unit['TMID']
        return unit_team_map


def cal_unit_dis(unit1, unit2):
    return math.sqrt(math.pow(unit1["X"] - unit2["X"], 2) + math.pow(unit1["Y"] - unit2["Y"], 2))/1000.

