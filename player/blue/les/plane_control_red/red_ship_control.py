from enum import Enum
import math
import json

from env.env_cmd_cs import EnvCmd
from env.env_def import UnitType, UnitStatus, BLUE_AIRPORT_ID

flag_print = False


class Ship(object):
    def __init__(self):
        self.civil = set()        # 情报中的中立目标
        self.unknown = set()      # 初始态势（xx秒内）的未知目标
        self.unknown_new = set()  # 新出现的未知目标
        self.opponent = set()     # 情报中的对方目标
        self.state = 0            # 0--初始化状态, 1--巡逻区域设置完成,2--机动
        self.ship_id = -1

    def step(self, sim_time, obs_red):
        # self.target_classify(obs_red['qb'], sim_time)
        cmd_list = []
        alive_ship = []  # 舰船是否活着
        for unit in obs_red['units']:
            if unit['LX'] == 21 and unit['WH'] == 1:
                alive_ship.append(unit['ID'])
        if flag_print:
            print(alive_ship)

        # 设置初始部署任务，多个备选区域，可以动态调整，对战过程中分析和记录对方的出兵策略，
        if self.state == 0 and len(alive_ship) == 2:
            cmd_list.extend(self._ship_movedeploy(alive_ship[0], 40000, 40000))
            cmd_list.extend(self._ship_movedeploy(alive_ship[1], 40000, -40000))
            self.state = 1
            return cmd_list

        if len(alive_ship) == 0:  # 舰船损失，返回空指令
            return cmd_list

        # 蓝方当前存活的歼击机、预警机、轰炸机
        blue_fighter = []
        blue_awacs = []
        blue_bomber = []
        for unit in obs_red['qb']:
            if unit['LX'] == 11 and unit['WH'] == 1:
                blue_fighter.append(unit['ID'])
            elif unit['LX'] == 12 and unit['WH'] == 1:
                blue_awacs.append(unit['ID'])
            elif unit['LX'] == 15 and unit['WH'] == 1:
                blue_bomber.append(unit['ID'])

        # 护卫舰在某些情况下是需要放弃目标的
        for ship_id in alive_ship:
            for awacs in blue_awacs:
                if self.calc_distance(ship_id, awacs, obs_red) <= 100:
                    cmd_list.extend(self._ship_addtarget(ship_id, awacs))
                    if flag_print:
                        print('attack awacs', ship_id, awacs)
            for fighter in blue_fighter:
                if self.calc_distance(ship_id, fighter, obs_red) <= 100:
                    cmd_list.extend(self._ship_addtarget(ship_id, fighter))
                    if flag_print:
                        print('attack fighter', ship_id, fighter)
            for bommer in blue_bomber:
                if self.calc_distance(ship_id, bommer, obs_red) <= 100:
                    cmd_list.extend(self._ship_addtarget(ship_id, bommer))
                    if flag_print:
                        print('attack bommer', ship_id, bommer)

        return cmd_list


    @staticmethod
    def _ship_movedeploy(self_id, px, py, pz=0, direction=0, radar_state=1):
        return [EnvCmd.make_ship_movedeploy(self_id, px, py, pz, direction, radar_state)]

    @staticmethod
    def _ship_addtarget(self_id, target_id):
        return [EnvCmd.make_ship_addtarget(self_id, target_id)]

    # 将情报中的目标分类
    def target_classify(self, qbs, sim_time):
        for unit in qbs:
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

    def get_pos_by_id(self, id, obs_red):
        for unit in obs_red['units']:
            if unit['ID'] == id:
                return unit['X'], unit['Y']

        for unit in obs_red['qb']:
            if unit['ID'] == id:
                return unit['X'], unit['Y']

        return -140000, 0

    def calc_distance(self, id1, id2, obs):
        x1, y1 = self.get_pos_by_id(id1, obs)
        x2, y2 = self.get_pos_by_id(id2, obs)
        dis = math.sqrt((x1-x2)*(x1-x2) + (y1-y2)*(y1-y2))/1000
        return dis
