from enum import Enum
import math
import json

from env.env_cmd_cs import EnvCmd
from env.env_def import UnitType, UnitStatus, BLUE_AIRPORT_ID

FIGHTER_PATROL_POINT1 = [-20000, 20000, 7500]
FIGHTER_PATROL_POINT2 = [-40000, 10000, 7500]
FIGHTER_PATROL_POINT3 = [20000, 0, 7500]
FIGHTER_PATROL_POINT4 = [-40000, -10000, 7500]
FIGHTER_PATROL_POINT5 = [-20000, -20000, 7500]
FIGHTER_PATROL_POINT6 = [-40000, 90000, 7500]

FIGHTER_PATROL_PARAMS = [90, 10000, 10000, 270, 7200]

flag_print = False

class Fighter(object):
    def __init__(self):
        self.civil = set()        # 情报中的中立
        self.unknown = set()      # 初始态势（xx秒内）的未知目标
        self.unknown_new = set()  # 新出现的未知目标
        self.opponent = set()     # 情报中的对方目标
        self.state = 0            # 0--初始化状态, 1--巡逻空域设置完成,2--航线机动
        self.team_ids = set()
        self.fighters = set()
        self.target_red = set()
        self.fighter_task = dict()   # 歼击机拦截任务("蓝方歼击机ID":"红方飞机ID")
        self.fighter_jammer = set()  # 正在拦截干扰机的飞机
        self.fighter_awacs = set()   # 正在拦截预警机的飞机
        self.take_off_index = 0

    def step(self, sim_time, obs_blue):
        self.target_classify(obs_blue['qb'], sim_time)
        cmd_list = []
        # 飞机按批全部起飞
        if self.state == 0 and sim_time > 120:
            # print('self.take_off_index:', self.take_off_index)
            if self.take_off_index < 1:
                cmd_list.extend(self._takeoff_area_patrol(2, 11, FIGHTER_PATROL_POINT1, FIGHTER_PATROL_PARAMS, obs_blue))
            elif self.take_off_index < 2:
                cmd_list.extend(self._takeoff_area_patrol(2, 11, FIGHTER_PATROL_POINT2, FIGHTER_PATROL_PARAMS, obs_blue))
            elif self.take_off_index < 3:
                cmd_list.extend(self._takeoff_area_patrol(2, 11, FIGHTER_PATROL_POINT3, FIGHTER_PATROL_PARAMS, obs_blue))
            elif self.take_off_index < 4:
                cmd_list.extend(self._takeoff_area_patrol(2, 11, FIGHTER_PATROL_POINT4, FIGHTER_PATROL_PARAMS, obs_blue))
            elif self.take_off_index < 5:
                cmd_list.extend(self._takeoff_area_patrol(2, 11, FIGHTER_PATROL_POINT5, FIGHTER_PATROL_PARAMS, obs_blue))
            elif self.take_off_index < 6:
                cmd_list.extend(self._takeoff_area_patrol(2, 11, FIGHTER_PATROL_POINT6, FIGHTER_PATROL_PARAMS, obs_blue))
            self.take_off_index += 1

        # 当前有作战能力(存活,且有弹药)的蓝方歼击机编号
        cur_alive = set()
        for unit in obs_blue['units']:
            if unit['LX'] == 11 and unit['WH'] == 1 and '170' in unit['WP'].keys() and int(unit['WP']['170']) > 0:
                cur_alive.add(unit['ID'])

        # 当前情报中的所有目标
        cur_alive_qb = set()
        for unit in obs_blue['qb']:
            cur_alive_qb.add(unit['ID'])


        if sim_time > 480:
            # 红方当前存活的歼击机、预警机、干扰机、轰炸机
            red_fighter = []
            red_awacs = []
            red_jammer = []
            red_bomber = []
            for unit in obs_blue['qb']:
                if unit['LX'] == 11 and unit['ID'] not in red_fighter:
                    red_fighter.append(unit['ID'])
                elif unit['LX'] == 12 and unit['ID'] not in red_awacs:
                    red_awacs.append(unit['ID'])
                elif unit['LX'] == 13 and unit['ID'] not in red_jammer:
                    red_jammer.append(unit['ID'])
                elif unit['LX'] == 15 and unit['ID'] not in red_bomber:
                    red_bomber.append(unit['ID'])

            # 判别有拦截任务的歼击机是否存活,拦截对象是否存活,己方飞机没有弹药(需返航)
            pop_ids = set()
            for id in self.fighter_task.keys():
                if id not in cur_alive:
                    pop_ids.add(id)
                elif self.fighter_task[id] not in cur_alive_qb:
                    pop_ids.add(id)

                for unit in obs_blue['units']:
                    if unit['ID'] == id:
                        if '170' not in  unit['WP'].keys() or int(unit['WP']['170']) == 0:
                            pop_ids.add(id)

            for id in pop_ids:
                self.fighter_task.pop(id)

            self.fighter_jammer = self.fighter_jammer - set(pop_ids)
            self.fighter_awacs = self.fighter_awacs - set(pop_ids)

            # attck jammer
            cur_task_target = list(self.fighter_task.values())     # 红方被拦截的飞机
            cur_task_fighter = set(self.fighter_task.keys())       # 蓝方有拦截任务的歼击机
            free_fighter = cur_alive - self.fighter_jammer         # 蓝方没有拦截任务的歼击机

            # 还需改进，发现干扰机，需要改变原来飞机的作战任务，转而进攻干扰机
            for jammer in red_jammer:
                if cur_task_target.count(jammer) < 1 and len(free_fighter) > 0:
                    id_dis = self.calc_distance_all_2(free_fighter, jammer, obs_blue) # 计算出最近的空闲的蓝方歼击机编号及距离
                    if id_dis[1] < 75:   # 发现干扰机需要前出去拦截(大于射程)，还需要防范红方绕行，则需要
                        cmd_list.extend(self._airattack(id_dis[0], jammer, 0))
                        if flag_print:
                            print('fighter attack jammer:', id_dis[0], jammer)
                        self.fighter_task[id_dis[0]] = jammer
                        self.fighter_jammer.add(id_dis[0])
                        cur_task_target = list(self.fighter_task.values())
                        cur_task_fighter = set(self.fighter_task.keys())
                        free_fighter = cur_alive - self.fighter_jammer


            # attck awacs
            cur_task_target = list(self.fighter_task.values())
            cur_task_fighter = set(self.fighter_task.keys())
            free_fighter = cur_alive - self.fighter_jammer - self.fighter_awacs
            for awacs in red_awacs:
                if cur_task_target.count(awacs) < 3 and len(free_fighter) > 0:  # 用if而不用while，是1次指新增一个，
                    id_dis = self.calc_distance_all_2(free_fighter, awacs, obs_blue)
                    if id_dis[1] < 75:   # 发现预警机需要前出去拦截(大于射程)
                        cmd_list.extend(self._airattack(id_dis[0], awacs, 0))
                        if flag_print:
                            print('fighter attack awacs:', id_dis[0], awacs)
                        self.fighter_task[id_dis[0]] = awacs
                        self.fighter_awacs.add(id_dis[0])
                        cur_task_target = list(self.fighter_task.values())
                        cur_task_fighter = set(self.fighter_task.keys())
                        free_fighter = cur_alive - self.fighter_jammer

            # attack bomber
            cur_task_target = list(self.fighter_task.values())
            cur_task_fighter = set(self.fighter_task.keys())
            free_fighter = cur_alive - self.fighter_jammer - self.fighter_awacs
            for bomber in red_bomber:
                if cur_task_target.count(bomber) < 1 and len(free_fighter) > 0:
                    id_dis = self.calc_distance_all_2(free_fighter, bomber, obs_blue)
                    if id_dis[1] < 55:   # 发现轰炸机
                        cmd_list.extend(self._airattack(id_dis[0], bomber, 0))
                        if flag_print:
                            print('fighter attack bomber:', id_dis[0], bomber)
                        self.fighter_task[id_dis[0]] = bomber
                        cur_task_target = list(self.fighter_task.values())
                        cur_task_fighter = set(self.fighter_task.keys())
                        free_fighter = cur_alive - cur_task_fighter
                #
                # if cur_task_target.count(bomber) < 1:
                #     for fighter_id in cur_alive:
                #         if fighter_id not in cur_task_fighter and self.calc_distance(fighter_id, bomber, obs_blue) < 80:
                #             cmd_list.extend(self._airattack(fighter_id, bomber, 0))
                #             self.fighter_task[fighter_id] = bomber
                #             break

            cur_task_target = list(self.fighter_task.values())
            cur_task_fighter = set(self.fighter_task.keys())
            free_fighter = cur_alive - self.fighter_jammer - self.fighter_awacs
            red_fighter = self.calc_distance_all(free_fighter, red_fighter, obs_blue)
            for fighter in red_fighter:
                if cur_task_target.count(fighter) < 1 and len(free_fighter) > 0:
                    for fighter_id in cur_alive:
                        if fighter_id not in cur_task_fighter and self.calc_distance(fighter_id, fighter, obs_blue) < 55:
                            cmd_list.extend(self._airattack(fighter_id, fighter, 0))
                            if flag_print:
                                print('fighter attack fighter:', fighter_id, fighter)
                            self.fighter_task[fighter_id] = fighter
                            break

            # 缺少威胁分析，判别红方来袭飞机，是否有兵力去应对
            # cur_task_target = list(self.fighter_task.values())
            # cur_task_fighter = set(self.fighter_task.keys())
            # free_fighter = cur_alive - cur_task_fighter
            # for opp in self.opponent:
            #     if opp == 30001:
            #         continue
            #     if cur_task_target.count(opp) < 1 and len(free_fighter) > 0:
            #         for fighter_id in cur_alive:
            #             if fighter_id not in cur_task_fighter and self.calc_distance(fighter_id, opp, obs_blue) < 70:
            #                 cmd_list.extend(self._airattack(fighter_id, opp, 0))
            #                 self.fighter_task[fighter_id] = opp
            #                 break
            #
            # cur_task_target = list(self.fighter_task.values())
            # cur_task_fighter = set(self.fighter_task.keys())
            # for opp in self.unknown_new:
            #     if cur_task_target.count(opp) < 1 and len(free_fighter) > 0:
            #         for fighter_id in cur_alive:
            #             if fighter_id not in cur_task_fighter and self.calc_distance(fighter_id, opp, obs_blue) < 70:
            #                 cmd_list.extend(self._airattack(fighter_id, opp, 0))
            #                 self.fighter_task[fighter_id] = opp
            #                 break


        # 歼击机需要回撤，没必要过半场，还要回来掩护预警机
        for unit in obs_blue['units']:
            # 歼击机、活着、当前没有拦截任务、太靠前, 则回撤
            if unit['LX'] == 11 and unit['WH'] == 1 and unit['ID'] not in self.fighter_task.keys() and unit['X'] > -20000:
                y = unit['Y']
                if unit['Y'] > 170500:
                    y = 170500
                elif unit['Y'] < -165000:
                    y = -165000
                cmd_list.extend(self._area_patrol(unit['ID'], [-30000, y, 0], FIGHTER_PATROL_PARAMS))

        for unit in obs_blue['units']:
            if unit['LX'] == 11:
                if '170' not in unit['WP'].keys() or int(unit['WP']['170']) == 0:
                    # 无弹药的飞机需要返航
                    cmd_list.extend(self._returntobase(unit['ID']))
                    if flag_print:
                        print('fighter return to base:', unit['ID'])

        if sim_time > 2500:
            airports = obs_blue['airports'][0]
            if airports['AIR'] > 0:
                cmd_list.extend(self._takeoff_area_patrol(2, 11, FIGHTER_PATROL_POINT1, FIGHTER_PATROL_PARAMS, obs_blue))

        return cmd_list

    @staticmethod
    def _takeoff_area_patrol(num, lx, patrol_point, patrol_params, obs_blue):
        airports = obs_blue['airports'][0]
        fighter_num = airports['AIR']

        if fighter_num >= num:
            fighter_num -= num
        else:
            num = fighter_num

        return [EnvCmd.make_takeoff_areapatrol(BLUE_AIRPORT_ID, num, lx, *patrol_point, *patrol_params)]


    # 返航
    @staticmethod
    def _returntobase(unit_id, airport_id=20001):
        return [EnvCmd.make_returntobase(unit_id, airport_id)]

    @staticmethod
    def _airattack(self_id, target_id, type=0):
        return [EnvCmd.make_airattack(self_id, target_id, type)]

    @staticmethod
    def _area_patrol(self_id, patrol_point, patrol_params):
        return [EnvCmd.make_areapatrol(self_id, *patrol_point, *patrol_params)]


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

    #按距离排序 ids1 blue, ids2 red，考虑集合为空的情况
    def calc_distance_all(self, ids1, ids2, obs_blue):
        if len(ids1) == 0 or len(ids2) == 0:
            return []
        dis_s = dict() # 每个红方目标与蓝方的最小距离
        for id2 in ids2:
            dis_t = []  # 某个红方目标分别与所有蓝方的距离
            for id1 in ids1:
                dis = self.calc_distance(id1, id2, obs_blue)
                dis_t.append(dis)
            dis_t.sort()
            dis_s[id2] = dis_t[0]

        li_s = sorted(dis_s.items(), key=lambda kv: (kv[1], kv[0]))

        li_return = []
        for i in range(len(li_s)):
            li_return.append(li_s[i][0])

        return  li_return

    # ids1 --blue fighters,  id2 red target
    def calc_distance_all_2(self, ids1, id2, obs_blue):
        dis_t = dict()  # 某个红方目标分别与所有蓝方的距离
        for id1 in ids1:
            dis = self.calc_distance(id1, id2, obs_blue)
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

    # 分析干扰机是否需要打击
    def jammer_analyse(self, jammer_id, obs_blue):
        for unit in obs_blue['qb']:
            if unit['ID'] == jammer_id:
                if unit['X'] < 0:
                    return True
        return False

    def threat_analyse(self, obs_blue):
        for unit in obs_blue['qb']:
            pass
