import numpy as np
from itertools import chain


class MoveObjectInfoEncoder:

    def __init__(self, maxIdCount, maxJbCount, maxTypeCount, maxModelCount, maxFormationBinCodeLen,
                 xGridLength, xMaplength, yGridLength, yMaplength, flyMaxSpeed, unitCourse, maxDamageCount):
        self.maxIdCount = maxIdCount
        self.maxJbCount = maxJbCount
        self.maxTypeCount = maxTypeCount
        self.maxModelCount = maxModelCount
        # 最大编队号二进制编码长度
        self.maxFormationBinCodeLen = maxFormationBinCodeLen

        # x轴上一个格子的长度
        self.xGridLength = xGridLength
        # x轴上整个地图的长度
        self.xMaplength = xMaplength
        # y轴上一个格子的长度
        self.yGridLength = yGridLength
        # y轴上整个地图的长度
        self.yMaplength = yMaplength
        self.flyMaxSpeed = flyMaxSpeed
        self.unitCourse = unitCourse
        self.maxDamageCount = maxDamageCount
        # x轴长度的二进制编码的最大长度
        xmaxGridCount = xMaplength // self.xGridLength + 1
        self.xPBinaryCodeLength = len(list(chain(*bin(xmaxGridCount)))) - 2
        ymaxGridCount = yMaplength // self.yGridLength + 1
        self.yPBinaryCodeLength = len(list(chain(*bin(ymaxGridCount)))) - 2
        self.model_list = ['SU-27', 'SU-35']  # 型号名称列表
        # 类型列表 0-未知 11-作战飞机；12-预警机；13-电子干扰机；14-无人侦察机；21-护卫舰；31-地面防空；41-机场
        self.type_list = [0, 11, 12, 13, 14, 15, 21, 31,32, 41, 42, 29, 19]

        # m_Extent.SetLeft(-175155);
        # m_Extent.SetRight(174777);
        # m_Extent.SetTop(-175733);
        # m_Extent.SetBottom(175745);
        # boardlist 为[左，右，上，下]界限
        self.boardlist = [-175155, 174777, -175733, 175745]
        pass

    # 参数-base；结构-MoveObjectInfo
    # self.id = 0  # 目标标识 （暂时无需编码）
    # self.jb = 0  # 军别：0蓝（敌）1红（我）2绿（友）3黄（不明）
    # self.type = 0  # 类型 0-未知 11-作战飞机；12-预警机；13-电子干扰机；14-无人侦察机；21-护卫舰；31-地面防空；41-机场
    # self.model = ""  # 型号
    # self.formation = 1  # # 编队号，0-没有编队
    # self.sub_id = 0  # 子编队ID （暂时无需编码）
    # self.x = 0  # 当前位置X，单位：米
    # self.y = 0  # 当前位置Y，单位：米
    # self.z = 0  # 当前高度Z，单位：米 （暂时无需编码）
    # self.speed = 0  # 当前速度，单位：米/秒
    # self.course = 0  # 当前航向
    # self.pitch = 0  # 俯仰 （暂时无需编码）
    # self.roll = 0  # 横滚（暂时无需编码）
    # self.damage = 0  # 损伤程度，【0~100】
    # self.alive = 1  # 存活状态，0击毁，1存活
    def encodingMoveObjectInfo(self, unit):
        jbArray = self.encodejb(unit['JB'])
        typeArray = self.encodeType(unit['LX'])

        # formationArray = self.encodeFormation(info.formation)
        binaryXPadd0 = self.encodeXPosition(unit['X'])
        binaryYPadd0 = self.encodeYPosition(unit['Y'])
        flySpeedArray = self.encodeFlySpeed(unit['SP'])
        discreteCourseArray = self.encodeCourse(unit['HX'])
        damageArray = self.encodeDamage(unit['DA'])
        aliveArray = self.encodeAlive(unit['WH'])

        code = np.concatenate((jbArray, typeArray, binaryXPadd0, binaryYPadd0,
                               flySpeedArray, discreteCourseArray, damageArray, aliveArray))
        return code

    def encode_my_units(self, units):
        code = np.zeros((21, 53))  # 蓝方一共21架飞机（歼击机12,轰炸机8,预警机）
        ids = np.zeros(21, dtype=np.int)
        indx = 0
        for unit in units:
            if unit['LX'] == 11:
                code_single = self.encodingMoveObjectInfo(unit)
                # print(len(code_single))
                code[indx] = code_single
                ids[indx] = unit['ID']
                indx += 1
        indx = 12
        for unit in units:
            if unit['LX'] in [12, 15]:
                code_single = self.encodingMoveObjectInfo(unit)
                # print(len(code_single))
                code[indx] = code_single
                indx += 1
        return code, ids

    def encode_enemy_units(self, units):
        code = np.zeros((41, 53))  # 红方一共41架飞机（歼击机20,轰炸16,预警,干扰,侦察3）
        ids = np.zeros(41, dtype=np.int)
        indx = 0
        for unit in units:
            if unit['LX'] in [11, 12, 13, 14, 15]:
                code_single = self.encodingMoveObjectInfo(unit)
                # print(len(code_single))
                code[indx] = code_single
                ids[indx] = unit['ID']
                indx += 1
        return code, ids

    # 军别：0蓝（敌）1红（我）2绿（友）3黄（不明）
    def encodejb(self, jb):
        jbArray = np.zeros(self.maxJbCount)
        int_jb = int(jb)
        jbArray[int_jb] = 1
        return jbArray

    # 类型 0-未知 11-作战飞机；12-预警机；13-电子干扰机；14-无人侦察机；21-护卫舰；31-地面防空；41-机场
    def encodeType(self, unit_type):
        typeArray = np.zeros(self.maxTypeCount)
        int_unit_type = int(unit_type)
        indx = self.type_list.index(int_unit_type)  # 考虑不在列表里的情况
        typeArray[indx] = 1
        return typeArray

    # model---型号名称
    def encodeModel(self, model):
        modelArray = np.zeros(self.maxModelCount)
        indx = self.model_list.index(model)  # 是否考虑型号名称不在已有列表里的情况
        modelArray[indx] = 1
        return modelArray

    # 编队号，0-没有编队
    def encodeFormation(self, formation):
        int_formation = int(formation)
        binaryFormidAdd0 = np.zeros(self.maxFormationBinCodeLen)
        if int_formation == 0:
            return binaryFormidAdd0
        else:
            int_relative_formid = int_formation - 1000
            binary_formid = np.asarray(list(chain(*bin(int_relative_formid)))[2:])
            addZerolength = self.maxFormationBinCodeLen - binary_formid.size
            zeroArray = np.zeros(addZerolength)
            binaryFormidAdd0 = np.concatenate((zeroArray, binary_formid))
            binaryFormidAdd0 = binaryFormidAdd0.astype(float)

        return binaryFormidAdd0

    # 当前位置X，单位：米
    # m_Extent.SetLeft(-175155);
    # m_Extent.SetRight(174777);
    # m_Extent.SetTop(-175733);
    # m_Extent.SetBottom(175745);
    def encodeXPosition(self, xposition):
        #计算x轴格子的个数
        xposition = int(float(xposition)) - int(self.boardlist[0])
        xGridCount = self.xMaplength//self.xGridLength
        # xGridArray = np.zeros(xGridCount)
        #计算xposition应该落在第几个格子里
        xPIndex = xposition//self.xGridLength
        #xPIndex编为二进制再转为numpy array
        binaryXP = np.asarray(list(chain(*bin(xPIndex)))[2:])
        #binaryXP在左边补0，长度变为最大长度
        addZerolength = self.xPBinaryCodeLength - binaryXP.size
        zeroArray = np.zeros(addZerolength)
        binaryXPadd0 = np.concatenate((zeroArray, binaryXP))
        binaryXPadd0 = binaryXPadd0.astype(float)
        return binaryXPadd0

    # 当前位置Y，单位：米
    def encodeYPosition(self, yposition):
        # 计算y轴格子的个数
        yposition = int(float(yposition)) - int(self.boardlist[2])
        yGridCount = self.yMaplength // self.yGridLength
        yGridArray = np.zeros(yGridCount)
        # 计算yposition应该落在第几个格子里
        yPIndex = yposition // self.yGridLength
        # xPIndex编为二进制再转为numpy array
        binaryYP = np.asarray(list(chain(*bin(yPIndex)))[2:])
        # binaryYP在左边补0，长度变为最大长度
        addZerolength = self.yPBinaryCodeLength - binaryYP.size
        zeroArray = np.zeros(addZerolength)
        binaryYPadd0 = np.concatenate((zeroArray, binaryYP))
        binaryYPadd0 = binaryYPadd0.astype(float)
        return binaryYPadd0

    # 当前速度，单位：米/秒
    def encodeFlySpeed(self, flySpeed):
        float_flySpeed = float(flySpeed)
        flySpeedArray = np.zeros(1)
        flySpeedArray[0] = float_flySpeed/self.flyMaxSpeed
        return flySpeedArray

    # 当前航向
    def encodeCourse(self, course):
        discreteCourseCount = 360//self.unitCourse
        discreteCourseArray = np.zeros(discreteCourseCount)
        courseIndex = int(float(course))//self.unitCourse
        discreteCourseArray[courseIndex] = 1
        return discreteCourseArray

    # 损伤程度，【0~100】
    def encodeDamage(self, damage):
        damageLevel = int(self.maxDamageCount * damage / 100)
        damageLevel = min(damageLevel, self.maxDamageCount-1)
        damageArray = np.zeros(self.maxDamageCount)
        damageArray[damageLevel] = 1
        return damageArray

    # 存活状态，0击毁，1存活
    def encodeAlive(self, alive):

        aliveArray = np.zeros(2)
        aliveArray[int(alive)] = 1
        return aliveArray

    # def encodeCategory(self, category):
    #     categoryArray = np.zeros(self.maxCategoryCount)
    #     categoryArray[category] = 1
    #     return categoryArray


# 统计信息：
# 蓝方[轰炸机15、预警机12、雷达32、歼击机11、舰船21、地防31、机场42、指挥所41]
# 红方[轰炸机15、预警机12、侦察机14、干扰机13、歼击机11、舰船21、雷达32、机场42]
class ScalarInfoEncoder:
    def __init__(self,):
        pass

    def encode_scalar(self, obs):
        code = np.zeros(16, dtype=np.int)
        for unit in obs['units']:
            unit_type = unit['LX']
            if unit_type == 15:
                code[0] += 1
            elif unit_type == 12:
                code[1] += 1
            elif unit_type == 32:
                code[2] += 1
            elif unit_type == 11:
                code[3] += 1
            elif unit_type == 21:
                code[4] += 1
            elif unit_type == 31:
                code[5] += 1
            elif unit_type == 41:
                code[7] += 1
        if obs['airports'][0]['WH'] == 1:
            code[6] = 1

        for unit in obs['qb']:
            unit_type = unit['LX']
            if unit_type == 15:
                code[8] += 1
            elif unit_type == 12:
                code[9] += 1
            elif unit_type == 14:
                code[10] += 1
            elif unit_type == 31:
                code[11] += 1
            elif unit_type == 11:
                code[12] += 1
            elif unit_type == 21:
                code[13] += 1
            elif unit_type == 32:
                code[14] += 1

            code[15] = 1

        return code


class ObsParse(object):
    def __init__(self,):
        self.moveObjectInfoEncoder = MoveObjectInfoEncoder(maxIdCount=60,
                                                           maxJbCount=4,
                                                           maxTypeCount=13,
                                                           maxModelCount=10,
                                                           maxFormationBinCodeLen=8,
                                                           xGridLength=1000,
                                                           xMaplength=300000,
                                                           yGridLength=1000,
                                                           yMaplength=300000,
                                                           flyMaxSpeed=250,
                                                           unitCourse=30,
                                                           maxDamageCount=3)
        self.scalar_encoder = ScalarInfoEncoder()
        self.blue_total_units = [8, 1, 2, 12, 1, 3, 1, 2]
        self.pre_step_damage = np.zeros(8, dtype=np.int)   # 蓝方上一阶段的总损失
        self.pre_step_red_obs = dict()                     # 上一阶段观测到的红方目标

    def encode_my_units(self, obs):
        return self.moveObjectInfoEncoder.encode_my_units(obs['units'])

    def encode_enemy_units(self, obs):
        return self.moveObjectInfoEncoder.encode_enemy_units(obs['qb'])

    def encode_scalar(self, obs):
        return self.scalar_encoder.encode_scalar(obs)

    # 总损失，返回8维数组，依次表示[轰炸机、预警机、雷达、歼击机、舰船、地防、机场、指挥所]的损失数量
    # 统计单步损失
    def get_my_damage(self, obs):
        cur_alive = self.encode_scalar(obs)[:8]     # 当前在空的
        cur_alive[0] += obs['airports'][0]['BOM']   # 当前机场的
        cur_alive[1] += obs['airports'][0]['AWCS']  # 当前机场的
        cur_alive[3] += obs['airports'][0]['AIR']   # 当前机场的

        damage_total = self.blue_total_units - cur_alive
        # print('damage_total:', damage_total)
        damage_cur_step = damage_total - self.pre_step_damage
        self.pre_step_damage = damage_total
        # print('damage_cur_step:', damage_cur_step)
        return damage_cur_step

    # 返回8维数组，依次表示[轰炸机、预警机、侦察机、干扰机、歼击机、舰船、雷达、机场]
    def get_enemy_damage(self, obs):
        damage = np.zeros(8, dtype=np.int)
        red_fighter = set()
        red_awacs = set()
        red_jammer = set()
        red_bomber = set()
        for unit in obs['qb']:
            if unit['LX'] == 11 and unit['ID'] not in red_fighter:
                red_fighter.add(unit['ID'])
            elif unit['LX'] == 12 and unit['ID'] not in red_awacs:
                red_awacs.add(unit['ID'])
            elif unit['LX'] == 13 and unit['ID'] not in red_jammer:
                red_jammer.add(unit['ID'])
            elif unit['LX'] == 15 and unit['ID'] not in red_bomber:
                red_bomber.add(unit['ID'])

        if len(self.pre_step_red_obs.keys()) > 1:
            damage[4] = len(self.pre_step_red_obs['fighter'] - red_fighter)
            damage[1] = len(self.pre_step_red_obs['awacs'] - red_awacs)
            damage[3] = len(self.pre_step_red_obs['jammer'] - red_jammer)
            damage[0] = len(self.pre_step_red_obs['bomber'] - red_bomber)

        # 第一次调用时会默认初始化四个元素
        self.pre_step_red_obs['fighter'] = red_fighter
        self.pre_step_red_obs['awacs'] = red_awacs
        self.pre_step_red_obs['jammer'] = red_jammer
        self.pre_step_red_obs['bomber'] = red_bomber

        return damage

    def reset(self):
        self.pre_step_red_obs.clear()
        self.pre_step_damage = np.zeros(8, dtype=np.int)


if __name__ == "__main__":
    pre = dict()

    pre['a'] = {1, 2}
    pre['b'] = {2, 3}
    pre['c'] = set()

    t1 = set()
    t1.add(2)

    print(len(pre['c'] - t1))
    pre.clear()
    print(pre)
