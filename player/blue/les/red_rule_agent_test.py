from enum import Enum
import math,json
import time
import numpy as np
# from agent.plane_control.obs_parse import MoveObjectInfoEncoder
# from agent.plane_control.obs_parse import ScalarInfoEncoder


from env.env_cmd_cs import EnvCmd
from env.env_def import UnitType, UnitStatus, BLUE_AIRPORT_ID


from .plane_control_red.red_awacs_control import Awacs
from .plane_control_red.red_bomber_control import Bomber
from .plane_control_red.red_fighter_control import Fighter
from .plane_control_red.red_ship_control import Ship


# 蓝方指挥所
# lx:  41, id:  64, x:-131157, y:-87888, z:   100
# lx:  41, id:  65, x:-129533, y: 87664, z:    90


# 预警机
# 预警机待命阵位
AWACS_PATROL_POINT = [45000, 0, 7500]

# dir, len, wid, speed, time, mode:0:air/1:surface/2:both
AWACS_PATROL_PARAMS = [270, 20000, 20000, 160, 7200, 2]

AREA_PATROL_HEIGHT = 7000

PATROL_POINT1 = [-5000, 65000, AREA_PATROL_HEIGHT]
PATROL_POINT2 = [-5000, -65000, AREA_PATROL_HEIGHT]
PATROL_POINT3 = [-55000, 35000, AREA_PATROL_HEIGHT]
PATROL_POINT4 = [-55000, -35000, AREA_PATROL_HEIGHT]
PATROL_POINT5 = [-65000, 5000, AREA_PATROL_HEIGHT]
PATROL_POINT6 = [-65000, -5000, AREA_PATROL_HEIGHT]

PATROL_POINT11 = [-80000, 75000, AREA_PATROL_HEIGHT]
PATROL_POINT12 = [-80000, 45000, AREA_PATROL_HEIGHT]
PATROL_POINT13 = [-80000, 15000, AREA_PATROL_HEIGHT]
PATROL_POINT14 = [-80000, -15000, AREA_PATROL_HEIGHT]
PATROL_POINT15 = [-80000, -45000, AREA_PATROL_HEIGHT]
PATROL_POINT16 = [-80000, -75000, AREA_PATROL_HEIGHT]

PATROL_AREA_LEN = 30000
PATROL_AREA_WID = 30000
PATROL_DIRECTION = 90
PATROL_SPEED = 250
PATROL_TIME = 7200
PATROL_MODE_0 = 0
PATROL_MODE_1 = 1
PATROL_PARAMS = [PATROL_DIRECTION, PATROL_AREA_LEN, PATROL_AREA_WID, PATROL_SPEED, PATROL_TIME]
PATROL_PARAMS_0 = [PATROL_DIRECTION, PATROL_AREA_LEN, PATROL_AREA_WID, PATROL_SPEED, PATROL_TIME, PATROL_MODE_0]
PATROL_PARAMS_1 = [PATROL_DIRECTION, PATROL_AREA_LEN, PATROL_AREA_WID, PATROL_SPEED, PATROL_TIME, PATROL_MODE_1]

PATROL_TIME1 = 0
PATROL_TIME2 = 60
PATROL_TIME3 = 120
PATROL_TIME4 = 180
PATROL_TIME5 = 240
PATROL_TIME6 = 300

PATROL_TIME11 = 600
PATROL_TIME12 = 900
PATROL_TIME13 = 1200
PATROL_TIME14 = 1500
PATROL_TIME15 = 1800
PATROL_TIME16 = 2100

AIR_ATTACK_PERIOD = 10

global num_fighter
num_fighter = 12


class BlueAgentState(Enum):

    PATROL0 = 0
    PATROL1 = 1
    PATROL2 = 2
    PATROL3 = 3
    PATROL4 = 4
    PATROL5 = 5
    PATROL6 = 6

    PATROL11 = 11
    PATROL12 = 12
    PATROL13 = 13
    PATROL14 = 14
    PATROL15 = 15
    PATROL16 = 16

    END_TAKEOFF = 100


class RedRuleAgent:
    def __init__(self):

        self._init()

    def _init(self):
        self.awacs_agent = Awacs()
        self.bomber_agent = Bomber()
        self.fighter_agent = Fighter()
        self.ship_agent = Ship()

        self.command_list = []
        self.ship_list = []
        self.s2a_list = []
        self.radar_list = []
        self.aircraft_dict = {}

        self.a2a_list = []
        self.a2a_attack_list = []  # 已经收到拦截指令的飞机
        self.target_list = []
        self.target_ship_list = set()
        self.red_dic = {}
        self.attacking_targets = {}

        self.agent_state = BlueAgentState.PATROL0
        self.air_attack_time = 0
        self.airport_flag_time = 9000
        self.airport_flag = False
        self.period = 0           # 战争阶段
        self.civil = set()        # 情报中的中立
        self.unknown = set()      # 初始态势（xx秒内）的未知目标
        self.unknown_new = set()  # 新出现的未知目标
        self.opponent = set()     # 情报中的对方目标


    def reset(self):
        self._init()

    def step(self, sim_time, obs_red, **kwargs):
        t1 = time.time()
        # print('sim_time:', sim_time)

        cmd_list = []

        cmd_awacs = self.awacs_agent.step(sim_time, obs_red)
        cmd_list.extend(cmd_awacs)

        cmd_bomber = self.bomber_agent.step(sim_time, obs_red)
        cmd_list.extend(cmd_bomber)
        #
        cmd_fighter = self.fighter_agent.step(sim_time, obs_red)
        cmd_list.extend(cmd_fighter)

        cmd_ship = self.ship_agent.step(sim_time, obs_red)
        cmd_list.extend(cmd_ship)


        # print('----time----', time.time() - t1)
        return cmd_list

    @staticmethod
    def _takeoff_area_patrol(num, lx, patrol_point, patrol_params):
        global num_fighter
        if num_fighter >= num:
            num_fighter -= num
        else:
            num = num_fighter
            num_fighter = 0

        return [EnvCmd.make_takeoff_areapatrol(BLUE_AIRPORT_ID, num, lx, *patrol_point, *patrol_params)]

    # 区域巡逻
    @staticmethod
    def _area_patrol(unit_id, patrol_point, patrol_params):
        return [EnvCmd.make_areapatrol(unit_id, *patrol_point, *patrol_params)]

    @staticmethod
    def _air_attack(unit_id, target_id):
        return [EnvCmd.make_airattack(unit_id, target_id, 1)]

    # 将情报中的目标分类
    def target_classify(self, qbs, sim_time):
        cur_alive = set()
        for unit in qbs:
            cur_alive.add(unit['ID'])
            if unit['JB'] == 1:
                self.opponent.add(unit['ID'])
            elif unit['JB'] == 3:
                self.civil.add(unit['ID'])
            elif unit['JB'] == 2 and sim_time < 120:
                self.unknown.add(unit['ID'])
            else:
                self.unknown_new.add(unit['ID'])
        tmp = set()
        for id in self.unknown:
            if id in self.opponent or id in self.civil:
                tmp.add(id)

        self.unknown = self.unknown - tmp
        self.unknown_new = self.unknown_new - self.unknown - self.opponent - self.civil

        print('opponent:', self.opponent)
        print('civil:', self.civil)
        print('unkown:', self.unknown)
        print('unkown_new:', self.unknown_new)
        print('cur_alive:', cur_alive)


def print_info(units):
    for unit in units:
        if unit['LX'] != 41:
            print('id: {:3d}, tmid: {:4d}, speed: {:3.0f}, x: {:6.0f}, y: {:6.0f}, z: {:5.0f}, '
                  'type: {:3d}, state: {:3d}, alive: {:2d}, hang: {:3.0f}'.format
                  (unit['ID'], unit['TMID'], unit['SP'], unit['X'], unit['Y'], unit['Z'],
                   unit['LX'], unit['ST'], unit['WH'], unit['Hang']))

def print_info_qbs(qbs):
    for unit in qbs:
        print('id: {:3d}, jb: {:4d}, speed: {:3.0f}, x: {:6.0f}, y: {:6.0f}, z: {:5.0f}, '
                  'XH: {}, DA: {:3d}, alive: {:2d}, time: {}'.format
                  (unit['ID'], unit['JB'], unit['SP'], unit['X'], unit['Y'], unit['Z'],
                   unit['XH'], unit['DA'], unit['WH'], unit['TM'] ))


#南指挥所: -131156.63859  -87887.86736  99.7043
#北指挥所: -129533.05624   87664.0398   89.51567




