from enum import Enum
import math,json
import time
import numpy as np
# from agent.plane_control.obs_parse import MoveObjectInfoEncoder
# from agent.plane_control.obs_parse import ScalarInfoEncoder
from .plane_control_blue.obs_parse import ObsParse

from env.env_cmd_cs import EnvCmd
from env.env_def import UnitType, UnitStatus, BLUE_AIRPORT_ID


from .plane_control_blue.awacs_control import Awacs
from .plane_control_blue.bomber_control import Bomber
from .plane_control_blue.fighter_control import Fighter
from .plane_control_blue.ship_control import Ship
from .plane_control_blue.sam_control import Sam

# 蓝方指挥所
# lx:  41, id:  64, x:-131157, y:-87888, z:   100
# lx:  41, id:  65, x:-129533, y: 87664, z:    90

# X_Max = 174500
# X_Min = -170000
# Y_Max = 174500
# Y_Min = -171000


class BlueRuleAgent:
    def __init__(self,):
        self._init()

    def _init(self):
        self.awacs_agent = Awacs()
        self.bomber_agent = Bomber()
        self.fighter_agent = Fighter()
        self.ship_agent = Ship()
        self.sam_agent = Sam()

        # self.period = 0           # 战争阶段
        # self.civil = set()        # 情报中的中立
        # self.unknown = set()      # 初始态势（xx秒内）的未知目标
        # self.unknown_new = set()  # 新出现的未知目标
        # self.opponent = set()     # 情报中的对方目标
        # self.moveObjectInfoEncoder = MoveObjectInfoEncoder(maxIdCount=60,
        #                                               maxJbCount=4,
        #                                               maxTypeCount=13,
        #                                               maxModelCount=10,
        #                                               maxFormationBinCodeLen=8,
        #                                               xGridLength=1000,
        #                                               xMaplength=300000,
        #                                               yGridLength=1000,
        #                                               yMaplength=300000,
        #                                               flyMaxSpeed=250,
        #                                               unitCourse=30,
        #                                               maxDamageCount=3 )
        # self.scalar_encoder = ScalarInfoEncoder()
        self.obs_parse = ObsParse()

    def reset(self):
        self._init()

    def step(self, sim_time, obs_blue, **kwargs):
        # t1 = time.time()

        # my_code,ids = self.obs_parse.encode_my_units(obs_blue)
        # print(np.shape(my_code))
        # print(my_code)
        # print(ids)
        # enemy_code,ids = self.obs_parse.encode_enemy_units(obs_blue)
        # print(np.shape(enemy_code))
        # print(enemy_code)
        # print(ids)

        # scalar_info = self.obs_parse.encode_scalar(obs_blue)
        # print(np.shape(scalar_info))
        # print(scalar_info)
        #
        # damage = self.obs_parse.get_my_damage(obs_blue)
        # print('damage', damage)
        # enemy_damage = self.obs_parse.get_enemy_damage(obs_blue)
        # print('enemy_damage', enemy_damage)


        cmd_list = []
        # print_info(obs_blue['units'])
        # print_info_qbs(obs_blue['qb'])
        # self.target_classify(obs_blue['qb'], sim_time)

        # cmd_awacs = self.awacs_agent.step(sim_time, obs_blue)
        # cmd_list.extend(cmd_awacs)

        # cmd_bomber = self.bomber_agent.step(sim_time, obs_blue)
        # cmd_list.extend(cmd_bomber)

        # cmd_fighter = self.fighter_agent.step(sim_time, obs_blue)
        # cmd_list.extend(cmd_fighter)

        cmd_ship = self.ship_agent.step(sim_time, obs_blue)
        cmd_list.extend(cmd_ship)

        # cmd_sam = self.sam_agent.step(sim_time, obs_blue)
        # cmd_list.extend(cmd_sam)

        # print('----time----', time.time() - t1)
        return cmd_list

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



