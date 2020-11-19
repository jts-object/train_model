from drill.api.bp.gear.player import Player
from .les.player_adapter import LesBluePlayer
from .jtzd.player_adapter import JtzdBluePlayer
from .continue_.player_adapter import ContinueBluePlayer
import random



class RandomPlayer(Player):
    def __init__(self):
        # self.players = [LesBluePlayer, JtzdBluePlayer, ContinueBluePlayer]
        self.players = [LesBluePlayer]
        self.org_player = self._choise_random_player_cls()()
        print(self.org_player)
    
    def _choise_random_player_cls(self):
        player_cls = random.choice(self.players)
        return player_cls

    def step(self, raw_obs, env_step_info):
        return self.org_player.step(raw_obs, env_step_info)

    def reset(self, raw_obs, env_step_info):
        self.org_player = self._choise_random_player_cls()()
        print(self.org_player)
