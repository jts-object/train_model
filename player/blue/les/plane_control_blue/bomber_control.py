from enum import Enum
import math
import json

from env.env_cmd_cs import EnvCmd
from env.env_def import UnitType, UnitStatus, BLUE_AIRPORT_ID

BOMBER_PATROL_POINT1 = [-65000, -43000, 7500]
BOMBER_PATROL_POINT2 = [-65000, -20000, 7500]

# dir, len, wid, speed, time
BOMBER_PATROL_PARAMS = [270, 20000, 20000, 220, 7200]


flag_print = True

class Bomber(object):
    def __init__(self):
        self.civil = set()        # 情报中的中立
        self.unknown = set()      # 初始态势（xx秒内）的未知目标
        self.unknown_new = set()  # 新出现的未知目标
        self.opponent = set()     # 情报中的对方目标
        self.state = 0            # 0--初始化状态, 1--巡逻空域设置完成,2--航线机动
        self.bomber_ids1 = set()  # 前往第1个巡逻空域的飞机
        self.team_id1 = -1
        self.ship_id1 = -1
        self.bomber_ids2 = set()  # 前往第2个巡逻空域的飞机
        self.team_id2 = -1
        self.ship_id2 = -1
        self.target_ship_all = set()   # 记录累计发现的红方舰船
        self.target_ship_pro = set()   # 记录已经发过突击指令的舰船

    def step(self, sim_time, obs_blue):
        cmd_list = []
        cur_alive_units = set()   # 蓝方当前存活的轰炸机(在空)
        cur_alive_ship = set()    # 红方存活（能探测到）的舰船

        for unit in obs_blue['units']:
            if unit['LX'] == 15 and unit['WH'] == 1:
                cur_alive_units.add(unit['ID'])

        for unit in obs_blue['qb']:
            if unit['LX'] == 21 and unit['WH'] == 1:
                cur_alive_ship.add(unit['ID'])
            # 曾经探测到的舰船，当前情报里有对应ID,但没有类型时，依然打击
            if self.ship_id1 == unit['ID'] and unit['WH'] == 1:
                cur_alive_ship.add(unit['ID'])
            if self.ship_id2 == unit['ID'] and unit['WH'] == 1:
                cur_alive_ship.add(unit['ID'])

        if flag_print:
            print('all_red_ship:', self.target_ship_all)
            print('cur_alive_red_ship:', cur_alive_ship)
            print('airport bomber num:', obs_blue['airports'][0]['BOM'])
            print('self.bomber_ids1:', self.bomber_ids1)
            print('self.bomber_ids2', self.bomber_ids2)

        if self.state == 0:  # 起飞阶段
            if obs_blue['airports'][0]['BOM'] == 4:
                for unit in obs_blue['units']:
                    if unit['LX'] == 15:
                        self.bomber_ids1.add(unit['ID'])
            elif obs_blue['airports'][0]['BOM'] == 0:
                for unit in obs_blue['units']:
                    if unit['LX'] == 15 and unit['ID'] not in self.bomber_ids1:
                        self.bomber_ids2.add(unit['ID'])
                self.state = 1

            if obs_blue['airports'][0]['BOM'] > 4:
                cmd_list.extend(self._takeoff_area_patrol(1, BOMBER_PATROL_POINT1, BOMBER_PATROL_PARAMS, obs_blue))
            elif obs_blue['airports'][0]['BOM'] > 0:
                cmd_list.extend(self._takeoff_area_patrol(1, BOMBER_PATROL_POINT2, BOMBER_PATROL_PARAMS, obs_blue))

        elif self.state == 1:
            self.state = 2
        elif self.state == 2:
            self.state = 3
        elif self.state == 3 and sim_time > 200:
            # 根据态势改变轰炸机的任务
            for unit in obs_blue['qb']:
                if unit['LX'] == 21 and unit['WH'] == 1:
                    self.target_ship_all.add(unit['ID'])

            for ship_id in self.target_ship_all:
                if len(self.target_ship_pro) == 0:  # 先发现的舰船由南边编队打击
                    angle = self._calc_angle(self.bomber_ids1, ship_id, obs_blue)
                    for bomber_id in self.bomber_ids1:
                        team_id = self._get_team_id(bomber_id, obs_blue)
                        if team_id != -1:
                            cmd_list.extend(self._target_hunt(team_id, ship_id, 90-angle, 90))
                            if flag_print:
                                print('bomber attack ship:', bomber_id, ship_id)
                    self.ship_id1 = ship_id
                    self.target_ship_pro.add(ship_id)

                elif len(self.target_ship_pro) == 1 and ship_id not in self.target_ship_pro:
                    angle = self._calc_angle(self.bomber_ids2, ship_id, obs_blue)
                    for bomber_id in self.bomber_ids2:
                        team_id = self._get_team_id(bomber_id, obs_blue)
                        if team_id != -1:
                            cmd_list.extend(self._target_hunt(team_id, ship_id, 90-angle, 90))
                            if flag_print:
                                print('bomber attack ship:', bomber_id, ship_id)

                    self.ship_id2 = ship_id
                    self.target_ship_pro.add(ship_id)


            # # 第1个舰船曾经打击过，现在不在了，第2个舰船还活着，则编队1打击舰船2
            # if self.ship_id1 not in cur_alive_ship and self.ship_id1 in self.target_ship_pro and self.ship_id2 in cur_alive_ship:
            #     angle = self._calc_angle(self.team_id1, self.ship_id2, obs_blue)
            #     cmd_list.extend(self._targethunt(self.team_id1, self.ship_id2, 90-angle, 90))
            #     print('轰炸机编队1改打舰船2')
            # # 第2个舰船曾经打击过，现在不在了，第1个舰船还活着，则编队2打击舰船1
            # if self.ship_id2 not in cur_alive_ship and self.ship_id2 in self.target_ship_pro and self.ship_id1 in cur_alive_ship:
            #     angle = self._calc_angle(self.team_id2, self.ship_id1, obs_blue)
            #     cmd_list.extend(self._targethunt(self.team_id2, self.ship_id1, 90-angle, 90))
            #     print('轰炸机编队2改打舰船1')

        for unit in obs_blue['units']:
            if unit['LX'] == 15 and unit['WH'] == 1:
                if '360' not in unit['WP'].keys() or int(unit['WP']['360']) == 0:
                    cmd_list.extend(self._returntobase(unit['ID']))

            pass

        if sim_time > 1200: # 如果看不到红方舰船，则打击红方机场
            # 获取当前编队号
            cur_team_ids = set()
            for unit in obs_blue['units']:
                if unit['LX'] == 15:
                    cur_team_ids.add(unit['TMID'])
            # 两个舰船都打击过，现在都不在了，则突击红方机场
            # print('两个舰船都打击过，现在都不在了，则突击红方机场')
            # print(len(cur_alive_ship), len(self.target_ship_pro), cur_team_ids)
            # print('两个舰船都打击过，现在都不在了，则突击红方机场')
            if len(cur_alive_ship) == 0 and len(self.target_ship_pro) == 2:
                for team_id in cur_team_ids:
                    cmd_list.extend(self._target_hunt(team_id, 30001, 90, 90))
                    if flag_print:
                        print('attack red airport')
            pass

        if sim_time > 1000:
            airports = obs_blue['airports'][0]
            if airports['BOM'] > 0:
                cmd_list.extend(self._takeoff_area_patrol(2, BOMBER_PATROL_POINT1, BOMBER_PATROL_PARAMS, obs_blue))


        # print('bomber_ids1:', self.bomber_ids1, cur_alive_units-self.bomber_ids2)
        # print('bomber_ids2:', self.bomber_ids2, cur_alive_units-self.bomber_ids1)
        return cmd_list

    # 起飞到指定空域
    @staticmethod
    def _takeoff_area_patrol(num, area_hunt_point, area_hunt_area, obs_blue):
        airports = obs_blue['airports'][0]
        bomber_num = airports['BOM']

        if bomber_num >= num:
            bomber_num -= num
        else:
            num = bomber_num

        # make_takeoff_areapatrol(airport_id, fly_num, fly_type, px, py, pz, direction, length, width, speed, patrol_time)
        return [EnvCmd.make_takeoff_areapatrol(20001, num, 15, *area_hunt_point, *area_hunt_area)]

    # 目标突击
    @staticmethod
    def _target_hunt(self_id, target_id, direction, range):
        return [EnvCmd.make_targethunt(self_id, target_id, direction, range)]

    # 返航
    @staticmethod
    def _returntobase(self_id, airport_id=20001):
        return [EnvCmd.make_returntobase(self_id, airport_id)]

    def _calc_angle(self, bomber_set, ship_id, obs_blue):
        x_b = 0
        y_b = 0
        x_s = 0
        y_s = 0
        for unit in obs_blue['units']:
            if unit['ID'] in bomber_set:
                x_b = unit['X']
                y_b = unit['Y']
                break
        for unit in obs_blue['qb']:
            if unit['ID'] == ship_id:
                x_s = unit['X']
                y_s = unit['Y']
                break
        angle = math.atan((y_s-y_b)/(x_s-x_b))*180/(math.pi)
        return angle

    def _get_team_id(self, bomber_id, obs_blue):
        for unit in obs_blue['units']:
            if unit['ID'] == bomber_id:
                return unit['TMID']

        return -1