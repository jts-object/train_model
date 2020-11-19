from drill.api.bp.gear.player import Player
from .blue_rule_agent_test import BlueRuleAgent
# from .blue_rule_agent_ccw import BlueRuleAgent


class LesBluePlayer(Player):
    def __init__(self):
        self.org_player = BlueRuleAgent()

    def step(self, raw_obs, env_step_info):
        
        sim_time = raw_obs['sim_time']
        raw_obs = raw_obs['blue']
        return self.org_player.step(sim_time, raw_obs), None

    def reset(self, raw_obs, env_step_info):
        self.org_player.reset()
