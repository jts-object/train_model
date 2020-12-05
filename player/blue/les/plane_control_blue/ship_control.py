from enum import Enum
import math
import json

from env.env_cmd_cs import EnvCmd
from env.env_def import UnitType, UnitStatus, BLUE_AIRPORT_ID

print_flag = False


class Ship(object):
    def __init__(self):
        self.civil = set()        # 情报中的中立目标
        self.unknown = set()      # 初始态势（xx秒内）的未知目标
        self.unknown_new = set()  # 新出现的未知目标
        self.opponent = set()     # 情报中的对方目标
        self.state = 0            # 0--初始化状态, 1--巡逻区域设置完成, 2--机动
        self.ship_id = -1

        self.radar_flag = True

    def step(self, sim_time, obs_blue):
        self.target_classify(obs_blue['qb'], sim_time)
        cmd_list = []
        cmd_list_2 = []
        
        if sim_time > 100 and self.radar_flag:
            for unit in obs_blue['units']:
                if unit['LX'] == 21:
                    cmd_list_2.append(EnvCmd.make_ship_radarcontrol(unit['ID'], 0))
                    self.radar_flag = False
                if unit['LX'] == UnitType.AWACS:
                    cmd_list_2.append(EnvCmd.make_awcs_areapatrol(unit['ID'], -70000, 20000, 8000, 270, 10, 10, 100, 3600))


        ship_id = [unit['ID'] for unit in obs_blue['units'] if unit['LX'] == UnitType.SHIP]
        ship_id = ship_id[0] if len(ship_id) > 0 else None 
        # for sid in ship_id:
        for unit in obs_blue['qb']:
            if unit['LX'] == UnitType.A2A or unit['LX'] == UnitType.A2G:
                if ship_id:
                    if self.calc_distance(ship_id, unit['ID'], obs_blue) <= 95:
                        cmd_list_2.append(EnvCmd.make_ship_addtarget(ship_id, unit['ID']))
                    else:
                        cmd_list_2.append(EnvCmd.make_ship_removetarget(ship_id, unit['ID']))

        # 设置初始部署任务，多个备选区域，可以动态调整，对战过程中分析和记录对方的出兵策略，
        if self.state == 0:
            for unit in obs_blue['units']:
                if unit['LX'] == 21 and unit['WH'] == 1:
                    self.ship_id = unit['ID']
                    cmd_list_2.extend(self._ship_movedeploy(unit['ID'], -120000, 80000))
                    cmd_list_2.extend(self._ship_movedeploy(unit['ID'], -60000, 30000))
                    # cmd_list.extend(self._ship_movedeploy(unit['ID'], -10000, 0))
                    # cmd_list.extend(self._ship_movedeploy(unit['ID'], 0, 20000))
                    self.state = 1
                    return cmd_list_2


        # alive_ship = False  # 舰船是否活着
        # for unit in obs_blue['units']:
        #     if unit['LX'] == 21 and unit['WH'] == 1:
        #         alive_ship = True
        # if not alive_ship:  # 舰船损失，返回空指令
        #     return cmd_list

        # # 红方当前存活的歼击机、预警机、干扰机、轰炸机
        # red_fighter = []
        # red_awacs = []
        # red_jammer = []
        # red_bomber = []
        # for unit in obs_blue['qb']:
        #     if unit['LX'] == 11 and unit['WH'] == 1:
        #         red_fighter.append(unit['ID'])
        #     elif unit['LX'] == 12 and unit['WH'] == 1:
        #         red_awacs.append(unit['ID'])
        #     elif unit['LX'] == 13 and unit['WH'] == 1:
        #         red_jammer.append(unit['ID'])
        #     elif unit['LX'] == 15 and unit['WH'] == 1:
        #         red_bomber.append(unit['ID'])

        # # 护卫舰在某些情况下是需要放弃目标的

        # # 干扰机
        # for jammer in red_jammer:
        #     if self.calc_distance(self.ship_id, jammer, obs_blue) <= 70:
        #         cmd_list.extend(self._ship_addtarget(self.ship_id, jammer))
        #         if print_flag:
        #             print('attack jammer')

        # for awacs in red_awacs:
        #     if self.calc_distance(self.ship_id, awacs, obs_blue) <= 70:
        #         cmd_list.extend(self._ship_addtarget(self.ship_id, awacs))
        #         if print_flag:
        #             print('attack awacs')

        # for bommer in red_bomber:
        #     if self.calc_distance(self.ship_id, bommer, obs_blue) <= 113:
        #         cmd_list.extend(self._ship_addtarget(self.ship_id, bommer))
        #         if print_flag:
        #             print('attack bommer')
        #         print('ship id attack bommer and dis = ', self.ship_id, self.calc_distance(self.ship_id, bommer, obs_blue))
        # print('obs_blue qb', obs_blue['qb'])
        # cmd_list_2.extend(cmd_list)
        
        

        return cmd_list_2


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

    def get_pos_by_id(self, id, obs_blue):
        for unit in obs_blue['units']:
            if unit['ID'] == id:
                return unit['X'], unit['Y']

        for unit in obs_blue['qb']:
            if unit['ID'] == id:
                return unit['X'], unit['Y']

        return 140000, 0

    def calc_distance(self, id1, id2, obs_blue):
        x1, y1 = self.get_pos_by_id(id1, obs_blue)
        x2, y2 = self.get_pos_by_id(id2, obs_blue)
        dis = math.sqrt((x1-x2)*(x1-x2) + (y1-y2)*(y1-y2))/1000
        return dis