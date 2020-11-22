import sys
sys.path.append('/drill')
from drill.algo.bp.common.game_runner import BaseEnvRunner
from drill.flow.sampler.local_predictor import LocalPredictor
from config.config import gear_config, training_config
from drill.algo.bp.servers.process_config import process_config

if __name__ == '__main__':
    config = process_config(gear_config, training_config)
    predictors = {}
    for name, conf in config['agents'].items():
        policy_conf = conf['policy']
        policy_class = policy_conf.pop('class')
        policy = policy_class()(name, **policy_conf)
        predictor = LocalPredictor(policy)
        predictor.restore("/HDD2/jts/train_model/models/red_player-checkpoint-160")
        predictors[name] = predictor
    gear_config = config['env_runner']['gear_config']
    # hard-code gamma and lambda
    env_runner = BaseEnvRunner(-1, predictors, 0.99, 0.95, gear_config)
    i = 1
    while True:
        rollout = env_runner.generate_rollout()
        print('Episode num: {} Episode info: {}'.format(i, rollout[1].data))
        i += 1
