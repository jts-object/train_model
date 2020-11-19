from enum import Enum
import math
import json

from env.env_cmd_cs import EnvCmd, Point
from env.env_def import UnitType, UnitStatus, BLUE_AIRPORT_ID


AWACS_PATROL_POINT = [100000, 0, 7500]

AWACS_PATROL_POINT_N = [-130000, 70, 7500]
AWACS_PATROL_POINT_S = [-130000, -70, 7500]

# dir, len, wid, speed, time, mode:0:air/1:surface/2:both
AWACS_PATROL_PARAMS = [270, 10000, 10000, 160, 7200, 2]


class Awacs(object):
    def __init__(self):
        self.civil = set()        # 情报中的中立
        self.unknown = set()      # 初始态势（xx秒内）的未知目标
        self.unknown_new = set()  # 新出现的未知目标
        self.opponent = set()     # 情报中的对方目标
        self.state = 0            # 0--初始化状态, 1--巡逻空域设置完成,2--航线机动
        self.awacs_id = -1

    def step(self, sim_time, obs_red):
        cmd_list = []
        # 设置初始巡逻任务
        if self.state == 0:
            for awacs in obs_red['units']:
                if awacs['LX'] == 12:
                    self.awacs_id = awacs['ID']
                    cmd_list.extend(self._awacs_patrol(awacs['ID'], AWACS_PATROL_POINT, AWACS_PATROL_PARAMS))
                    print('awacs current pos:', awacs['X'], awacs['Y'], awacs['Z'])
                    self.state = 1

        if sim_time > 100:
            if not self._is_awacs_alive(obs_red):
                return cmd_list
            # 分析蓝方歼击机和舰船的位置，调整预警机的巡逻空域
            # 计算当前蓝方歼击机距离预警机的距离，返回最小距离，红方预警机调整前进与后撤
            if self._threat_analysis(obs_red) != None:
                x, y = self._threat_analysis(obs_red)
                cmd_list.extend(self._awacs_patrol(self.awacs_id, [x, y, 7500], AWACS_PATROL_PARAMS))

        return cmd_list

    # 预警机区域巡逻
    @staticmethod
    def _awacs_patrol(self_id, AWACS_PATROL_POINT, AWACS_PATROL_PARAMS):
        return [EnvCmd.make_awcs_areapatrol(self_id, *AWACS_PATROL_POINT, *AWACS_PATROL_PARAMS)]


    @staticmethod
    def _awacs_line_patrol(self_id, point_list):
        return [EnvCmd.make_awcs_linepatrol(self_id, 200, 0, 'line', point_list)]

    def _get_awacs_pos(self, obs_red):
        for unit in obs_red['units']:
            if unit['ID'] == self.awacs_id:
                return unit['X'], unit['Y'], unit['Z']
        return None, None, None

    # 计算当前蓝方歼击机距离红方预警机的距离，返回最小距离，
    def _get_fighter_dist(self, obs_red):
        x1,y1,z1 = self._get_awacs_pos(obs_red)
        dist_list = [150]
        for unit in obs_red['qb']:
            if unit['LX'] == 11 and unit['WH'] == 1:
                x2,y2 = unit['X'], unit['Y']
                dis = math.sqrt((x1 - x2) * (x1 - x2) + (y1 - y2) * (y1 - y2)) / 1000
                dist_list.append(dis)
        dist_list.sort()

        return dist_list[0]

    # 统计红方的歼击机在预警机前方的数量，还得要有弹药
    def _static_self_fighter(self, obs_red):
        x1, y1, z1 = self._get_awacs_pos(obs_red)
        num = 0
        y_total = 0
        for unit in obs_red['units']:
            if unit['LX'] == 11 and unit['WH'] == 1 :
                if unit['X'] < x1 and '170' in unit['WP'].keys() and int(unit['WP']['170']) > 0:
                    num += 1
                    y_total += unit['Y']
        return num, y_total/(num+0.001)

    # 威胁分析
    def _threat_analysis(self, obs_red):
        # 首先判别红方预警机是否活着
        x1, y1, z1 = self._get_awacs_pos(obs_red)
        dis_min = self._get_fighter_dist(obs_red)
        fighter_num, y_mean = self._static_self_fighter(obs_red)
        if dis_min > 70 and fighter_num > 3:
            x, y = max(x1-5, 20), y_mean
            if x > 170000:
                x = 170000
            elif x < -165000:
                x = -165000
            if y > 170000:
                y = 170000
            elif y < -165000:
                y = -165000

            return x, y
        else:
            return None

    # 计算与蓝方舰船的距离
    def _get_blue_ship_dist(self, obs_red):
        x1, y1, z1 = self._get_awacs_pos(obs_red)
        for unit in obs_red['qb']:
            if unit['LX'] == 21 and unit['WH'] == 1:
                x2, y2 = unit['X'], unit['Y']
                dis = math.sqrt((x1 - x2) * (x1 - x2) + (y1 - y2) * (y1 - y2)) / 1000
                return dis
        return 150

    def _rocket(self, obs_blue):
        for rock in obs_blue['rockets']:
            print('rock info:', rock['N1'], rock['N2'], rock['WH'])

    # 判别当前预警机是否还活着
    def _is_awacs_alive(self, obs_red):
        for unit in obs_red['units']:
            if unit['LX'] == 12 and unit['WH'] == 1:
                return True

        return False
