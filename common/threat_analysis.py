import numpy as np 


class ThreatAnalysis(object):

	def __init__(self, grid, threat_dict):
		self.grid = grid
		self.threat_dict = threat_dict

	def get_threat_matrix(self, obs):
		m = np.ones((self.grid.x_n, self.grid.y_n))
		for unit in obs['qb']:
			if unit['LX'] in self.threat_dict.keys():
				x_idx, y_idx = self.grid.get_idx(unit['X'], unit['Y'])
				threat_neighbor_range_x = int(self.threat_dict[unit['LX']] / self.grid.get_length_per_grid(axis=0))
				threat_neighbor_range_y = int(self.threat_dict[unit['LX']] / self.grid.get_length_per_grid(axis=1))
				for i in range(-threat_neighbor_range_x, threat_neighbor_range_x+1):
					for j in range(-threat_neighbor_range_y, threat_neighbor_range_y+1):
						x = np.clip(i+x_idx, 0, self.grid.x_n - 1)
						y = np.clip(j+y_idx, 0, self.grid.y_n - 1)
						if self._get_dist([x_idx, y_idx], [x, y]) < threat_neighbor_range_x:
							m[x][y] = 0
		return m.transpose()	

	def _get_dist(self, src, target):
		dist = np.sqrt(np.square(src[0] - target[0]) + np.square(src[1] - target[1]))
		return dist

