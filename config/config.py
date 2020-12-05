from env.nj01_env import NJ01Env
from player.red.agent_player import PlayerConfig, NJ01Player
from player.blue.blue_agent_player import bluePlayerConfig, bluePlayer
from player.blue.random_player import RandomPlayer

from env.env_def import MapInfo, SideType

from drill.api.bp.agent.features.types import PlainFeature, RangedFeature, CategoricalFeature, VectorFeature
from drill.api.bp.agent.features.templates import SpatialFeatureTemplate, EntityFeatureTemplate, CommonFeatureTemplate, ActionMaskFeatureTemplate
from drill.api.bp.agent.actions import CategoricalAction, SingleSelectiveAction, UnorderedMultipleSelectiveAction, OrderedMultipleSelectiveAction, ChildHead, \
    MultipleHeadsAction


import os
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


default_entity_config = {
    # 特征抽取第一步
    'hidden_layer_sizes': [256, 128],   # 全连接层的结构

    # 特征抽取第二步
    'transformer_block_num': 2,         # transformer的层数，若为0表示不使用该结构
    'transformer_head_num': 2,          # multi_head 的头数
    'transformer_head_size': 8,         # 每个 head 的大小

    # 特征抽取第三步
    'pooling': 'max',  # 池化方式可选 ['max', 'attention']
    # 若pooling选了attention方式，则要填写如下相应参数
    'attention_pooling_query_num': 16,  # 查询向量的数目
    'attention_pooling_head_num': 2,    # multi_head 的头数
    'attention_pooling_head_size': 64,  # 每个 head 的大小
}

# implement your network config here
hidden_state_size = 256
network_config = {
    'aggregator_config': {'hidden_state_size': hidden_state_size},  # 每层gru的大小
}


# implement your feature templates dict here
feature_templates_list = [
    EntityFeatureTemplate(              # 我方单位信息
        name='my_units',
        max_length=PlayerConfig.MAX_MY_UNIT_LEN,                  # 我方单位数量最大值
        features={                      # 我方单位特征（可视情况进行二次设计）
            "x": RangedFeature((MapInfo.X_MIN, MapInfo.X_MAX)),
            "y": RangedFeature((MapInfo.Y_MIN, MapInfo.Y_MAX)),
            "z": RangedFeature((MapInfo.Z_MIN, MapInfo.Z_MAX)),
            "a2a": RangedFeature((0, MapInfo.A2A_WEAPON_NUM_MAX)),
            "a2g": RangedFeature((0, MapInfo.A2G_WEAPON_NUM_MAX)),
            "course": RangedFeature((MapInfo.COURSE_MIN, MapInfo.COURSE_MAX)),
            "speed": RangedFeature((MapInfo.SPEED_MIN, MapInfo.SPEED_MAX)),
            # "locked": CategoricalFeature(depth=2),
            "locked": PlainFeature(),
            "type": CategoricalFeature(depth=len(PlayerConfig.MY_UNIT_TYPES)),
        },
        encoder_config=default_entity_config    # 使用上述填写的特征抽取参数   
    ),
    EntityFeatureTemplate(              # 敌方单位信息
        name='en_units',
        max_length=PlayerConfig.MAX_EN_UNIT_LEN,                 # 敌方单位数量最大值
        features={                      # 敌方单位特征（可视情况进行二次设计）
            "x": RangedFeature((MapInfo.X_MIN, MapInfo.X_MAX)),
            "y": RangedFeature((MapInfo.Y_MIN, MapInfo.Y_MAX)),
            "z": RangedFeature((MapInfo.Z_MIN, MapInfo.Z_MAX)),
            "course": RangedFeature((MapInfo.COURSE_MIN, MapInfo.COURSE_MAX)),
            "speed": RangedFeature((MapInfo.SPEED_MIN, MapInfo.SPEED_MAX)),
            'type': CategoricalFeature(depth=len(PlayerConfig.EN_UNIT_TYPES)),
        },
        encoder_config=default_entity_config    # 使用上述填写的特征抽取参数
    ),
    SpatialFeatureTemplate(
        height=PlayerConfig.MINI_MAP_SIZE,
        width=PlayerConfig.MINI_MAP_SIZE,
        name='mini_map',
        features={
            "my_a2a": PlainFeature(),
            "my_a2g": PlainFeature(),
            "en_a2a": PlainFeature(),
            "en_a2g": PlainFeature(),
            "threat": PlainFeature(),
        }
    ),
    CommonFeatureTemplate(
        name='common',                  # 通用信息
        features={                      # 通用信息特征（可视情况进行二次设计）
            "sim_time": RangedFeature((MapInfo.SIM_TIME_MIN, MapInfo.SIM_TIME_MAX)),
        }
    ),
    ActionMaskFeatureTemplate(
        name="selected_units_mask",
        features={
            "mask": VectorFeature(PlayerConfig.MAX_MY_UNIT_LEN),
        },
        as_features=False,
    )
]

# implement your action space here
action_type = MultipleHeadsAction(
    [
        ChildHead(
            CategoricalAction(          # 选择执行何种动作
                name='meta_action',
                n=7, 
            )
        ),
        ChildHead(
            OrderedMultipleSelectiveAction(  # 选择执行该动作的我方单位
                name='selected_units',
                source_template=feature_templates_list[0],  # 我方单位数据来源
                max_count=10,
                action_mask="selected_units_mask",
            )
        ),
        ChildHead(
            CategoricalAction(          # 提供选择实施动作的必要数据（此处为移动动作的x位置）
                name='pos_x',
                n=PlayerConfig.GLOBAL_MOVE_SIZE
            )
        ),
        ChildHead(
            CategoricalAction(          # 提供选择实施动作的必要数据（此处为移动动作的y位置）
                name='pos_y',
                n=PlayerConfig.GLOBAL_MOVE_SIZE
            )
        ),
        ChildHead(
            SingleSelectiveAction(      # 提供选择实施动作的必要数据（此处为攻击对象）
                name='target_unit',
                source_template=feature_templates_list[1]   # 敌方单位数据来源
            )
        )

    ]
)


PREFIX = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
gear_config = {
    'players': [
        {
            'player_name': 'red_player',
            'class': NJ01Player(
                SideType.RED,
                feature_templates_list,
                action_type,
                network_config
            ),
            # 'agent_name': 'red_player',
        },

        # {
        #     'player_name': 'blue_player',
        #     'class': NJ01Player(
        #         SideType.BLUE,
        #         feature_templates_list,
        #         action_type,
        #         network_config
        #     ),
        #     'agent_name': 'red_player',
        # },

        # {
        #     'player_name': 'blue',
        #     'class': bluePlayer(
        #         SideType.BLUE,
        #         feature_templates_list_blue,
        #         action_type_blue,
        #         network_config,
        #     ),
        #     'agent_name': 'blue_player',
        # }, 

        {
            'player_name': 'blue',
            'class': RandomPlayer(),
        }

    ],
    'env': {
        'class': NJ01Env,
        'server_port': 6100,
        'volume_list': [],
        'max_game_len': None,
        'max_game_time': 10800,      # 每回合的最大时间限制
        'scen_name': '/home/Joint_Operation_scenario.ntedt',
        'prefix': PREFIX,
        'image_name': 'sim_fast:v2.8',
        # 'image_name': 'registry.inspir.ai:5000/combatmodserver:v1.4',
        'sim_speed': 20,            # 模拟速度
    },
    'is_external_env': True,
    'get_external_env_server_hosts_function': lambda x: x,
}


# def delayed_sampler_proxy_daemon():
#     from drill.flow.sampler.buffered_sampler import BufferedSampler
#     return BufferedSampler


training_config = {
    'agent_config': [
        {
            'agent_name': 'red_player',         # 红方智能体名称
            'inference_batch_size': None,       # 推演批数据的大小
            'training_batch_size': 128,         # 训练批数据的大小
            'trainer.retore_policy': False,
            'trainer.restore_version': None,
        }, 

        # {
        #     'agent_name': 'blue_player',        # 蓝方智能体名称
        #     'inference_batch_size': None,       # 推演批数据的大小
        #     'training_batch_size': 128,         # 训练批数据的大小
        #     'trainer.retore_policy': False,
        #     'trainer.restore_version': None,
        # }, 
    ],
    'sampler.env_num': 30,                      # 分布式采样中环境数量
    'sampler.sample_queue_size': 35,
    # 'sampler.class': delayed_sampler_proxy_daemon,
    'controller.episode_num': 25,               # 每多少局进行一次更新
    'controller.save_interval': 10,             # 每多少局存一次模型
}
