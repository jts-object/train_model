from enum import Enum
import math
import json

from env.env_cmd_cs import EnvCmd, Point
from env.env_def import UnitType, UnitStatus, BLUE_AIRPORT_ID


AWACS_PATROL_POINT = [-100000, 0, 7500]

AWACS_PATROL_POINT_N = [-130000, 70000, 7500]
AWACS_PATROL_POINT_S = [-130000, -70000, 7500]

# dir, len, wid, speed, time, mode:0:air/1:surface/2:both
AWACS_PATROL_PARAMS = [270, 20000, 20000, 160, 7200, 2]


class Awacs(object):
    def __init__(self):
        self.civil = set()        # 情报中的中立
        self.unknown = set()      # 初始态势（xx秒内）的未知目标
        self.unknown_new = set()  # 新出现的未知目标
        self.opponent = set()     # 情报中的对方目标
        self.state = 0            # 0--初始化状态, 1--巡逻空域设置完成,2--航线机动
        self.awacs_id = -1

    def step(self, sim_time, obs_blue):
        # self._rocket(obs_blue)
        cmd_list = []
        # 设置初始巡逻任务
        if self.state == 0:
            for awacs in obs_blue['units']:
                if awacs['LX'] == 12:
                    self.awacs_id = awacs['ID']
                    cmd_list.extend(self._awacs_patrol(awacs['ID'], AWACS_PATROL_POINT, AWACS_PATROL_PARAMS))
                    # print('awacs current pos:', awacs['X'], awacs['Y'], awacs['Z'])
                    self.state = 1

        # 设置预警机的巡逻航线，如果未见敌方目标，预警机可以适当前出，增加探测范围，如果出现威胁，则后撤至安全区域
        # if self.state == 1 and self.awacs_id != -1:
        #     print('awacs_id:', self.awacs_id)
        #     x,y,z = self._get_awacs_pos(obs_blue)
        #     if x != None:
        #         cmd_list.extend(self._awcs_linepatrol(self.awacs_id, [ Point(0,0,z)]))

        # 预警机存活状态判别
        if self.state == 1 and sim_time > 100:
            alive_awacs = False  # 预警机存活状态
            for unit in obs_blue['units']:
                if unit['LX'] == 12 and unit['WH'] == 1:
                    alive_awacs = True
            # 如果预警机损失，则直接返回空指令
            if not alive_awacs:
                return cmd_list

        # 推演一段时间后根据战场态势调整预警机的巡逻空域
        if self.state == 1 and sim_time > 2000:
            alvie_n = False       # 北指挥所存活状态
            alvie_s = False       # 南指挥所存活状态
            for unit in obs_blue['units']:
                if unit['LX'] == 41 and unit['Y'] > 0 and unit['WH'] == 1:
                    alvie_n = True
                if unit['LX'] == 41 and unit['Y'] < 0 and unit['WH'] == 1:
                    alvie_s = True


            # 北岛失守，预警机南撤
            if not alvie_n and alvie_s:
                cmd_list.extend(self._awacs_patrol(self.awacs_id, AWACS_PATROL_POINT_S, AWACS_PATROL_PARAMS))
                self.state = 2

            # 南岛失守，预警机北撤
            if alvie_n and not alvie_s:
                cmd_list.extend(self._awacs_patrol(self.awacs_id, AWACS_PATROL_POINT_N, AWACS_PATROL_PARAMS))
                self.state = 2
            # 红方歼击机突破防守直奔预警机而来，预警机适当后撤，为歼击机拦截争取时间
            pass

            # 判别预警机是否需要朝某个岛机动

        # print(cmd_list)
        if self.state == 1 and sim_time > 1200: # 蓝方没有歼击机了，或者蓝方歼击机数量小于4，预警机撤回南岛
            cur_alive_fighter = set()
            for unit in obs_blue['units']:
                if unit['LX'] == 11 and unit['WH'] == 1:
                    cur_alive_fighter.add(unit['ID'])

            if len(cur_alive_fighter) + obs_blue['airports'][0]['AIR'] < 5:
                cmd_list.extend(self._awacs_patrol(self.awacs_id, AWACS_PATROL_POINT_S, AWACS_PATROL_PARAMS))

        return cmd_list

    # 预警机区域巡逻
    @staticmethod
    def _awacs_patrol(self_id, AWACS_PATROL_POINT, AWACS_PATROL_PARAMS):
        return [EnvCmd.make_awcs_areapatrol(self_id, *AWACS_PATROL_POINT, *AWACS_PATROL_PARAMS)]


    @staticmethod
    def _awcs_linepatrol(self_id, point_list):
        return [EnvCmd.make_awcs_linepatrol(self_id, 200, 0, 'line', point_list)]

    def _get_awacs_pos(self, obs_blue):
        for unit in obs_blue['units']:
            if unit['ID'] == self.awacs_id:
                return unit['X'], unit['Y'], unit['Z']
        return None, None, None

    def _threat_ana(self, obs_blue):
        for unit_qb in obs_blue['qb']:
            if unit_qb['LX'] == 11:
                pass

    def _rocket(self, obs_blue):
        for rock in obs_blue['rockets']:
            print('rock info:', rock['N1'], rock['N2'], rock['WH'])
