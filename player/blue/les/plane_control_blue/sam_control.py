from enum import Enum
import math
import json

from env.env_cmd_cs import EnvCmd
from env.env_def import UnitType, UnitStatus, BLUE_AIRPORT_ID

flag_print = False

class Sam(object):
    def __init__(self):
        self.civil = set()        # 情报中的中立
        self.unknown = set()      # 初始态势（xx秒内）的未知目标
        self.unknown_new = set()  # 新出现的未知目标
        self.opponent = set()     # 情报中的对方目标
        self.state = 0            # 0--初始化状态, 1--巡逻区域设置完成,2--机动

    def step(self, sim_time, obs_blue):
        cmd_list = []
        sam_ids = dict()  # 当前存活的地防及雷达开关机状态

        for unit in obs_blue['units']:
            if unit['LX'] == 31 and unit['WH'] == 1:
                # sam_ids.add(unit['ID'])
                sam_ids[unit['ID']] = unit['ST']
                if flag_print:
                    print(unit['ID'], unit['ST'])

                if unit['ST'] == 32:
                    cmd_list.extend(self._ground_radarcontrol(unit['ID'], 1))


        self.target_classify(obs_blue['qb'], sim_time)

        # 红方当前存活的歼击机、预警机、干扰机、轰炸机
        red_fighter = []
        red_awacs = []
        red_jammer = []
        red_bomber = []
        for unit in obs_blue['qb']:
            if unit['LX'] == 11 and unit['WH'] == 1:
                red_fighter.append(unit['ID'])
            elif unit['LX'] == 12 and unit['WH'] == 1:
                red_awacs.append(unit['ID'])
            elif unit['LX'] == 13 and unit['WH'] == 1:
                red_jammer.append(unit['ID'])
            elif unit['LX'] == 15 and unit['WH'] == 1:
                red_bomber.append(unit['ID'])

        # 如果蓝方歼击机和预警机的全都损失，则地防只打击红方轰炸机
        attack_target = []
        blue_fighter = []
        blue_awacs = []
        for unit in obs_blue['units']:
            if unit['LX'] == 11 and unit['WH'] == 1:
                blue_fighter.append(unit['ID'])
            if unit['LX'] == 12 and unit['WH'] == 1:
                blue_awacs.append(unit['ID'])
        fighter_num_airports = obs_blue['airports'][0]['AIR']  # 机场的可用歼击机数量

        if len(blue_fighter) + fighter_num_airports + len(blue_awacs) == 0:
            attack_target = [13, 15]

        for sam_id in sam_ids.keys():
            # 默认地防开机，如果射程内没有预警机、干扰机或轰炸机，且只有歼击机，则关机
            need_turn_off = False
            for unit in obs_blue['qb']:
                if unit['LX'] == 12 and self.calc_distance(sam_id, unit['ID'], obs_blue) <= 95:
                    need_turn_off = False
                    break
                if unit['LX'] == 13 and self.calc_distance(sam_id, unit['ID'], obs_blue) <= 95:
                    need_turn_off = False
                    break
                if unit['LX'] == 15 and self.calc_distance(sam_id, unit['ID'], obs_blue) <= 100:
                    need_turn_off = False
                    break
            if need_turn_off and sam_ids[sam_id] != 90:  # 雷达当前开机状态，需要关机
                # cmd_list.extend(self._ground_radarcontrol(sam_id, 0))
                if flag_print:
                    print('sam turn off:', sam_id)
            if not need_turn_off and sam_ids[sam_id] != 91:  # 雷达当前关机机状态，需要开机
                cmd_list.extend(self._ground_radarcontrol(sam_id, 1))
                if flag_print:
                    print('sam turn on:', sam_id)


        # 干扰机
        for jammer in red_jammer:
            for sam_id in sam_ids.keys():
                if self.calc_distance(sam_id, jammer, obs_blue) <= 95:
                    cmd_list.extend(self._ground_addtarget(sam_id, jammer))
                    if flag_print:
                        print('sam attack jammer:', sam_id, jammer)

        for awacs in red_awacs:
            for sam_id in sam_ids.keys():
                if self.calc_distance(sam_id, awacs, obs_blue) <= 95:
                    cmd_list.extend(self._ground_addtarget(sam_id, awacs))
                    if flag_print:
                        print('sam attack awacs:', sam_id, awacs)

        for bommer in red_bomber:
            for sam_id in sam_ids.keys():
                if self.calc_distance(sam_id, bommer, obs_blue) <= 95:
                    cmd_list.extend(self._ground_addtarget(sam_id, bommer))
                    if flag_print:
                        print('sam attack bommer:', sam_id, bommer)

        for fighter in red_fighter:
            for sam_id in sam_ids.keys():
                if self.calc_distance(sam_id, fighter, obs_blue) <= 100:
                    # cmd_list.extend(self._ship_removetarget(sam_id, fighter))
                    # print('sam remove fighter:', sam_id, fighter)
                    pass

        return cmd_list


    @staticmethod
    def _ground_addtarget(self_id, target_id):
        return [EnvCmd.make_ground_addtarget(self_id, target_id)]

    @staticmethod
    def _ship_removetarget(self_id, target_id):
        return [EnvCmd.make_ship_removetarget(self_id, target_id)]

    @staticmethod
    def _ground_radarcontrol(self_id, on_off):
        return [EnvCmd.make_ground_radarcontrol(self_id, on_off)]

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
                return unit['X'], unit['Y'], unit['Z']

        for unit in obs_blue['qb']:
            if unit['ID'] == id:
                return unit['X'], unit['Y'], unit['Z']

        return 140000, 0, 0

    def calc_distance(self, id1, id2, obs_blue):
        x1, y1, z1 = self.get_pos_by_id(id1, obs_blue)
        x2, y2, z2 = self.get_pos_by_id(id2, obs_blue)
        dis = math.sqrt((x1-x2)*(x1-x2) + (y1-y2)*(y1-y2) + (z1-z2)*(z1-z2))/1000
        return dis


def print_info(units):
    for unit in units:
        if unit['LX'] == 31:
            print('id: {:3d}, tmid: {:4d}, speed: {:3.0f}, x: {:6.0f}, y: {:6.0f}, z: {:5.0f}, '
                  'type: {:3d}, state: {:3d}, alive: {:2d}, hang: {:3.0f}'.format
                  (unit['ID'], unit['TMID'], unit['SP'], unit['X'], unit['Y'], unit['Z'],
                   unit['LX'], unit['ST'], unit['WH'], unit['Hang']))
