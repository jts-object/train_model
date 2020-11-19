from enum import Enum
import math
import json

from env.env_cmd_cs import EnvCmd
from env.env_def import UnitType, UnitStatus, BLUE_AIRPORT_ID

# 突击南岛时轰炸机的发生位置（突击前需要清除蓝方歼击机）
FIGHTER_PATROL_POINT1 = [-55000, -54000, 7500]
FIGHTER_PATROL_POINT2 = [0, 0, 7500]

FIGHTER_PATROL_POINT3 = [-60000, 50000, 7500]


FIGHTER_PATROL_PARAMS = [0, 20000, 10000, 270, 7200]

flag_print = False

class Fighter(object):
    def __init__(self):
        self.civil = set()        # 情报中的中立
        self.unknown = set()      # 初始态势（xx秒内）的未知目标
        self.unknown_new = set()  # 新出现的未知目标
        self.opponent = set()     # 情报中的对方目标

        self.state = 0               # 0--初始化状态, 1--巡逻空域设置完成,2--航线机动
        self.fighter_task = dict()   # 歼击机拦截任务("蓝方歼击机ID":"红方飞机ID")
        self.fighter_task_important = dict()  # 重要的拦截任务，拦截在射程范围内的对方歼击机
        self.fighter_awacs = set()   # 正在拦截预警机的飞机
        self.take_off_index = 0      # 刚开始时的起飞序号

        self.command_post_south = -1  # 指挥所ID
        self.command_post_north = -1

        self.red_north_damage = False  # 北指挥所是否已经摧毁
        self.red_south_damage = False

    def step(self, sim_time, obs_red):
        # self.target_classify(obs_red['qb'], sim_time)
        # 判别两个指挥所的状态，目前各兵种分别判断，后续整合
        self.command_post_south = -1
        self.command_post_north = -1
        for unit in obs_red['qb']:
            if unit['LX'] == 41:
                if unit['Y'] < 0:
                    self.command_post_south = unit['ID']
                else:
                    self.command_post_north = unit['ID']
        if sim_time > 500:
            if self.command_post_south == -1:
                self.red_south_damage = True
            if self.command_post_north == -1:
                self.red_north_damage = True

        cmd_list = []
        # 飞机按批全部起飞，按照先打南指挥所的策略派兵
        if self.state == 0 and sim_time > 10:
            if flag_print:
                print('self.take_off_index:', self.take_off_index)
            if self.take_off_index < 12:
                cmd_list.extend(self._takeoff_area_patrol(1, 11, FIGHTER_PATROL_POINT1, FIGHTER_PATROL_PARAMS, obs_red))
            elif self.take_off_index < 20:
                cmd_list.extend(self._takeoff_area_patrol(1, 11, FIGHTER_PATROL_POINT2, FIGHTER_PATROL_PARAMS, obs_red))
            self.take_off_index += 1

        # 当前有作战能力(存活,且有弹药)的红方歼击机编号
        cur_alive = set()
        for unit in obs_red['units']:
            if unit['LX'] == 11 and unit['WH'] == 1 and '170' in  unit['WP'].keys() and int(unit['WP']['170']) > 0:
                cur_alive.add(unit['ID'])


        if sim_time > 480:
            # 蓝方当前存活的歼击机、预警机、轰炸机
            blue_fighter = []
            blue_awacs = []
            blue_bomber = []
            for unit in obs_red['qb']:
                if unit['LX'] == 11 and unit['ID'] not in blue_fighter:
                    blue_fighter.append(unit['ID'])
                elif unit['LX'] == 12 and unit['ID'] not in blue_awacs:
                    blue_awacs.append(unit['ID'])
                elif unit['LX'] == 15 and unit['ID'] not in blue_bomber:
                    blue_bomber.append(unit['ID'])

            # 判别有拦截任务的歼击机是否存活,拦截对象是否存活,己方飞机没有弹药(需返航)
            self.fighter_task = self._clean_attack_task(self.fighter_task, cur_alive, obs_red)
            self.fighter_task_important = self._clean_attack_task(self.fighter_task_important, cur_alive, obs_red)


            # attck awacs
            tmp = [item[0] for item in self.fighter_task.items() if item[1] in blue_awacs ]
            self.fighter_awacs = set(tmp)
            cur_task_target = list(self.fighter_task.values())       # 蓝方被拦截的飞机
            cur_task_fighter = set(self.fighter_task.keys())         # 红方有拦截任务的歼击机
            free_fighter = cur_alive - self.fighter_awacs - set(self.fighter_task_important.keys())
            for awacs in blue_awacs:
                if cur_task_target.count(awacs) < 3 and len(free_fighter) > 0:  # 用if而不用while，是1次指新增一个，
                    id_dis = self.calc_distance_all_2(free_fighter, awacs, obs_red)
                    if id_dis[1] < 75:   # 发现预警机需要前出去拦截(大于射程)
                        cmd_list.extend(self._airattack(id_dis[0], awacs, 0))
                        if flag_print:
                            print('fighter attack awacs:', id_dis[0], awacs)
                        self.fighter_task[id_dis[0]] = awacs
                        self.fighter_awacs.add(id_dis[0])
                        cur_task_target = list(self.fighter_task.values())
                        cur_task_fighter = set(self.fighter_task.keys())


            # attack bomber
            cur_task_target = list(self.fighter_task.values())
            cur_task_fighter = set(self.fighter_task.keys())
            free_fighter = cur_alive - self.fighter_awacs - set(self.fighter_task_important.keys())
            for bomber in blue_bomber:
                if cur_task_target.count(bomber) < 1 and len(free_fighter) > 0:
                    id_dis = self.calc_distance_all_2(free_fighter, bomber, obs_red)
                    if id_dis[1] < 45:   # 发现轰炸机
                        cmd_list.extend(self._airattack(id_dis[0], bomber, 0))
                        if flag_print:
                            print('fighter attack bomber:', id_dis[0], bomber)
                        self.fighter_task[id_dis[0]] = bomber
                        cur_task_target = list(self.fighter_task.values())
                        cur_task_fighter = set(self.fighter_task.keys())
                        free_fighter = cur_alive - cur_task_fighter

            # 拦截歼击机
            cur_task_target = list(self.fighter_task.values())
            cur_task_fighter = set(self.fighter_task.keys())
            free_fighter = cur_alive - self.fighter_awacs - set(self.fighter_task_important.keys())
            red_fighter = self.calc_distance_all(free_fighter, blue_fighter, obs_red)
            for fighter in blue_fighter:
                if cur_task_target.count(fighter) < 1 and len(free_fighter) > 0:
                    for fighter_id in cur_alive:
                        if fighter_id not in cur_task_fighter: # and self.calc_distance(fighter_id, fighter, obs_red) < 100:
                            cmd_list.extend(self._airattack(fighter_id, fighter, 0))
                            if flag_print:
                                print('fighter attack fighter:', fighter_id, fighter)
                            self.fighter_task[fighter_id] = fighter
                            break

            # 拦截近距离的歼击机
            cur_task_target = list(self.fighter_task_important.values())
            cur_task_fighter = set(self.fighter_task_important.keys())
            free_fighter = cur_alive - cur_task_fighter
            red_fighter = self.calc_distance_all(free_fighter, blue_fighter, obs_red)

            for fighter in blue_fighter:
                if cur_task_target.count(fighter) < 2 and len(free_fighter) > 0:
                    for fighter_id in cur_alive:
                        if fighter_id not in cur_task_fighter and self.calc_distance(fighter_id, fighter, obs_red) < 50:
                            cmd_list.extend(self._airattack(fighter_id, fighter, 0))
                            if flag_print:
                                print('fighter attack fighter:', fighter_id, fighter)
                            self.fighter_task[fighter_id] = fighter
                            self.fighter_task_important[fighter_id] = fighter
                            break

            if self.red_south_damage:
                for fighter_id in cur_alive:
                    cmd_list.extend(self._area_patrol(fighter_id, FIGHTER_PATROL_POINT3, FIGHTER_PATROL_PARAMS))
                    if flag_print:
                        print('fighter area patrol:', fighter_id, unit)

            # # 当所有飞机都没有拦截任务时，主动出击
            # for unit in blue_fighter
            if len(self.fighter_task.keys()) == 0 and sim_time > 1200:
                for unit in blue_fighter:
                    for fighter_id in cur_alive:
                        if fighter_id not in cur_task_fighter:
                            cmd_list.extend(self._airattack(fighter_id, unit, 0))
                            if flag_print:
                                print('fighter attack fighter:', fighter_id, unit)
                            self.fighter_task[fighter_id] = unit
                            break

        # 已经开战后，暂时没有拦截任务（以及任务已经完成的）的战斗机，继续前进
        if sim_time > 1200:
            for unit in obs_red['units']:
                if unit['LX'] == 11 and unit['ID'] not in self.fighter_task.keys() and unit['X'] > -10000:
                    y = min(unit['Y'] + 10000, 80000)
                    if y > 170000:
                        y = 170000
                    elif y < -165000:
                        y = -165000
                    cmd_list.extend(self._area_patrol(unit['ID'], [-20000, y, 7500], FIGHTER_PATROL_PARAMS))
                    if flag_print:
                        print('fighter fly to left :', unit['ID'])

        # 没有弹药的飞机返航
        for unit in obs_red['units']:
            if unit['LX'] == 11:
                if '170' not in unit['WP'].keys() or int(unit['WP']['170']) == 0:
                    # 无弹药的飞机需要返航
                    cmd_list.extend(self._returntobase(unit['ID']))
                    if flag_print:
                        print('fighter return to base:', unit['ID'])

        if sim_time > 2000:
            airports = obs_red['airports'][0]
            if airports['AIR'] > 0:
                cmd_list.extend(self._takeoff_area_patrol(2, 11, FIGHTER_PATROL_POINT1, FIGHTER_PATROL_PARAMS, obs_red))

        return cmd_list

    @staticmethod
    def _takeoff_area_patrol(num, lx, patrol_point, patrol_params, obs_red):
        airports = obs_red['airports'][0]
        fighter_num = airports['AIR']

        if fighter_num >= num:
            fighter_num -= num
        else:
            num = fighter_num

        return [EnvCmd.make_takeoff_areapatrol(30001, num, lx, *patrol_point, *patrol_params)]

    @staticmethod
    def _area_patrol(self_id, patrol_point, patrol_params):
        return [EnvCmd.make_areapatrol(self_id, *patrol_point, *patrol_params)]

    # 返航
    @staticmethod
    def _returntobase(unit_id, airport_id=30001):
        return [EnvCmd.make_returntobase(unit_id, airport_id)]

    @staticmethod
    def _airattack(self_id, target_id, type=0):
        return [EnvCmd.make_airattack(self_id, target_id, type)]


    def get_pos_by_id(self, id, obs_red):
        for unit in obs_red['units']:
            if unit['ID'] == id:
                return unit['X'], unit['Y']

        for unit in obs_red['qb']:
            if unit['ID'] == id:
                return unit['X'], unit['Y']

        return 140000, 0

    def calc_distance(self, id1, id2, obs_red):
        x1, y1 = self.get_pos_by_id(id1, obs_red)
        x2, y2 = self.get_pos_by_id(id2, obs_red)
        dis = math.sqrt((x1-x2)*(x1-x2) + (y1-y2)*(y1-y2))/1000
        return dis

    #按距离排序 ids1 red, ids2 blue，考虑集合为空的情况
    def calc_distance_all(self, ids1, ids2, obs_red):
        if len(ids1) == 0 or len(ids2) == 0:
            return []
        dis_s = dict() # 每个蓝方目标与红方的最小距离
        for id2 in ids2:
            dis_t = []  # 某个蓝方目标分别与所有红方的距离
            for id1 in ids1:
                dis = self.calc_distance(id1, id2, obs_red)
                dis_t.append(dis)
            dis_t.sort()
            dis_s[id2] = dis_t[0]

        li_s = sorted(dis_s.items(), key=lambda kv: (kv[1], kv[0]))

        li_return = []
        for i in range(len(li_s)):
            li_return.append(li_s[i][0])

        return  li_return

    # 返回值[己方平台编号、距离]
    # ids1 --己方兵力编号列表,  id2 对方目标编号，计算离对方目标最近的我方兵力，
    def calc_distance_all_2(self, ids1, id2, obs_red):
        dis_t = dict()  # 某个红方目标分别与所有蓝方的距离
        for id1 in ids1:
            dis = self.calc_distance(id1, id2, obs_red)
            dis_t[id1] = dis

        li_s = sorted(dis_t.items(), key=lambda kv: (kv[1], kv[0]))

        if len(li_s) == 0:
            return [0, 200]

        return li_s[0]


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


    def threat_analyse(self, obs_red):
        for unit in obs_red['qb']:
            pass

    # 整理当前的拦截任务列表,判别有拦截任务的歼击机是否存活,拦截对象是否存活,己方飞机没有弹药(需返航)
    def _clean_attack_task(self, fighter_task, cur_alive, obs_red):
        # 当前情报中的所有目标
        cur_alive_qb = set()
        for unit in obs_red['qb']:
            cur_alive_qb.add(unit['ID'])

        pop_ids = set()
        for id in fighter_task.keys():
            if id not in cur_alive:
                pop_ids.add(id)
            elif fighter_task[id] not in cur_alive_qb:
                pop_ids.add(id)
            for unit in obs_red['units']:
                if unit['ID'] == id:
                    if '170' not in unit['WP'].keys() or int(unit['WP']['170']) == 0:
                        pop_ids.add(id)
        for id in pop_ids:
            fighter_task.pop(id)

        return fighter_task
