from enum import Enum
import math
import json

from env.env_cmd_cs import EnvCmd
from env.env_def import UnitType, UnitStatus, BLUE_AIRPORT_ID

BOMBER_PATROL_POINT1 = [50000, -43000, 7500]
BOMBER_PATROL_POINT2 = [50000, -20000, 7500]
BOMBER_PATROL_POINT3 = [50000, 0, 7500]
BOMBER_PATROL_POINT4 = [50000, 10000, 7500]

# dir, len, wid, speed, time
BOMBER_PATROL_PARAMS = [270, 20000, 20000, 220, 7200]


flag_print = True

# 指挥所是不需要探测的，只要还未摧毁，情报里会一直上报

class Bomber(object):
    def __init__(self):
        self.civil = set()        # 情报中的中立
        self.unknown = set()      # 初始态势（xx秒内）的未知目标
        self.unknown_new = set()  # 新出现的未知目标
        self.opponent = set()     # 情报中的对方目标

        self.state = 0            # 0--初始化状态, 1--巡逻空域设置完成,2--航线机动
        self.bomber_ids1 = set()  # 前往第1个巡逻空域的飞机
        self.bomber_ids2 = set()  # 前往第2个巡逻空域的飞机

        self.command_post_south = -1   # 指挥所ID
        self.command_post_north = -1
        self.ship_id = -1
        self.ship_find = False         # 是否发现了蓝方的舰船

        self.red_north_damage = False  # 北指挥所是否已经摧毁
        self.red_south_damage = False
        self.red_ship_damage = False

        self.bomber_list = []          # 红方所有轰炸机（按起飞先后顺序，不管损失）
        self.attack_south = set()      # 当前正在打击南指挥所的飞机
        self.attack_north = set()
        self.attack_ship = set()
        self.attack_task = dict()
        self.cur_task = 'None'         # 当前的打击任务，'None','South','North','Ship'


    def step(self, sim_time, obs_red):
        cmd_list = []
        cur_alive_units = set()   # 蓝方当前存活的轰炸机(在空)

        for unit in obs_red['units']:
            if unit['LX'] == 15 and unit['WH'] == 1:
                cur_alive_units.add(unit['ID'])
                if unit['ID'] not in self.bomber_list:
                    self.bomber_list.append(unit['ID'])

        # print('self.bomber_list:', self.bomber_list)

        self.command_post_south = -1
        self.command_post_north = -1
        self.ship_id = -1
        for unit in obs_red['qb']:
            if unit['LX'] == 41:
                if unit['Y'] < 0:
                    self.command_post_south = unit['ID']
                else:
                    self.command_post_north = unit['ID']
                # print('zhi hui suo:', unit['X'], unit['Y'], unit['Z'])
            if unit['LX'] == 21 and unit['WH'] == 1:
                self.ship_id = unit['ID']
                self.ship_find = True
        # print(self.ship_find, self.ship_id)

        # 实时判别三个目标的存活状态
        if sim_time > 100:
            if self.command_post_south == -1:
                self.red_south_damage = True
                self.cur_task = 'None'
            if self.command_post_north == -1:
                self.red_north_damage = True
            if self.ship_find and self.ship_id == -1:
                self.red_ship_damage = True

        if flag_print:
            print('airport bomber num:', obs_red['airports'][0]['BOM'])


        if obs_red['airports'][0]['BOM'] == 0:
            self.state = 2

        if self.state == 0 and sim_time > 300:  # 起飞阶段
            if obs_red['airports'][0]['BOM'] > 12:
                cmd_list.extend(self._takeoff_areapatrol(1, BOMBER_PATROL_POINT1, BOMBER_PATROL_PARAMS, obs_red))
        if self.state == 0 and sim_time > 400:  # 起飞阶段
            if obs_red['airports'][0]['BOM'] > 8:
                cmd_list.extend(self._takeoff_areapatrol(1, BOMBER_PATROL_POINT2, BOMBER_PATROL_PARAMS, obs_red))
                self.state = 1
        if self.state == 1 and sim_time > 500:  # 起飞阶段
            if obs_red['airports'][0]['BOM'] > 4:
                cmd_list.extend(self._takeoff_areapatrol(1, BOMBER_PATROL_POINT3, BOMBER_PATROL_PARAMS, obs_red))
        if self.state == 1 and sim_time > 600:  # 起飞阶段
            if obs_red['airports'][0]['BOM'] > 0:
                cmd_list.extend(self._takeoff_areapatrol(1, BOMBER_PATROL_POINT4, BOMBER_PATROL_PARAMS, obs_red))
                self.state = 2


        elif self.state >= 1 and sim_time > 500:
            # 目前的策略是先打南岛
            # 根据态势改变轰炸机的任务
            if not self.red_south_damage and self.cur_task != 'South':
                self.cur_task = 'South'
                indx = 0
                for bomber_id in cur_alive_units:
                    if bomber_id in self.attack_task.keys():
                        continue
                    angle = self._calc_angle(bomber_id, self.command_post_south, obs_red)
                    team_id = self._get_team_id(bomber_id, obs_red)
                    if team_id != -1:
                        cmd_list.extend(self._target_hunt(team_id, self.command_post_south, 270 - angle, 100))
                        self.attack_task[bomber_id] = self.command_post_south
                        if flag_print:
                            print('bomber attack command_post_south:', bomber_id, self.command_post_south)
                    indx += 1
                    if indx == 4:
                        break

            if self.red_south_damage and self.cur_task != 'North':
                self.cur_task = 'North'
                indx = 0
                for bomber_id in cur_alive_units:
                    if bomber_id in self.attack_task.keys():
                        continue
                    angle = self._calc_angle(bomber_id, self.command_post_north, obs_red)
                    team_id = self._get_team_id(bomber_id, obs_red)
                    if team_id != -1:
                        cmd_list.extend(self._target_hunt(team_id, self.command_post_north, 270 - angle, 100))
                        self.attack_task[bomber_id] = self.command_post_north
                        if flag_print:
                            print('bomber attack command_post_north:', bomber_id, self.command_post_north)
                    indx += 1
                    if indx == 4:
                        break

            # 南岛打完，舰船还在
            if self.red_south_damage and not self.red_ship_damage and self.ship_find and self.cur_task != 'Ship':
                self.cur_task = 'Ship'
                indx = 0
                for bomber_id in cur_alive_units:
                    if bomber_id in self.attack_task.keys():
                        continue
                    angle = self._calc_angle(bomber_id, self.ship_id, obs_red)
                    team_id = self._get_team_id(bomber_id, obs_red)
                    if team_id != -1:
                        cmd_list.extend(self._target_hunt(team_id, self.ship_id, 270 - angle, 100))
                        if flag_print:
                            print('bomber attack ship:', bomber_id, self.ship_id,)
                    indx += 1
                    if indx == 4:
                        break

            #
            for item in self.attack_task.items():
                if item[1] == -1:
                    continue
                angle = self._calc_angle(item[0], item[1], obs_red)
                team_id = self._get_team_id(item[0], obs_red)
                if team_id != -1:
                    cmd_list.extend(self._target_hunt(item[0], item[1], 270 - angle, 100))




        for unit in obs_red['units']:
            if unit['LX'] == 15 and unit['WH'] == 1:
                if '360' not in unit['WP'].keys() or int(unit['WP']['360']) == 0:
                    cmd_list.extend(self._returntobase(unit['ID']))

        if sim_time > 1000:
            airports = obs_red['airports'][0]
            if airports['BOM'] > 0:
                cmd_list.extend(self._takeoff_areapatrol(2, BOMBER_PATROL_POINT1, BOMBER_PATROL_PARAMS, obs_red))


        return cmd_list

    # 起飞到指定空域
    @staticmethod
    def _takeoff_areapatrol(num, area_hunt_point, area_hunt_area, obs_red):
        airports = obs_red['airports'][0]
        bomber_num = airports['BOM']

        if bomber_num >= num:
            bomber_num -= num
        else:
            num = bomber_num

        # make_takeoff_areapatrol(airport_id, fly_num, fly_type, px, py, pz, direction, length, width, speed, patrol_time)
        return [EnvCmd.make_takeoff_areapatrol(30001, num, 15, *area_hunt_point, *area_hunt_area)]

    # 目标突击
    @staticmethod
    def _target_hunt(self_id, target_id, direction, range):
        return [EnvCmd.make_targethunt(self_id, target_id, direction, range)]

    # 返航
    @staticmethod
    def _returntobase(self_id, airport_id=30001):
        return [EnvCmd.make_returntobase(self_id, airport_id)]

    def _calc_angle(self, bomber_id, post_id, obs_red):
        x_b = 0
        y_b = 0
        x_s = 0
        y_s = 0
        for unit in obs_red['units']:
            if unit['ID'] == bomber_id:
                x_b = unit['X']
                y_b = unit['Y']
                break
        for unit in obs_red['qb']:
            if unit['ID'] == post_id:
                x_s = unit['X']
                y_s = unit['Y']
                break
        angle = math.atan((y_s-y_b)/(x_s-x_b))*180/(math.pi)
        return angle

    def _get_team_id(self, bomber_id, obs_red):
        for unit in obs_red['units']:
            if unit['ID'] == bomber_id:
                return unit['TMID']

        return -1

