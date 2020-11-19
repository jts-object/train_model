import numpy as np
import math
from pathfinding.core.diagonal_movement import DiagonalMovement
from pathfinding.core.grid import Grid
from pathfinding.finder.a_star import AStarFinder


class Unit(object):
    def __init__(self, info_map):
        self.avaliable = True

        self.id = info_map['ID']
        self.unit_type = info_map['LX']

        self.x = info_map['X']
        self.y = info_map['Y']
        self.z = info_map['Z']

    def astar_path_finding(self, matrix, end_point, map_grid):
        grid = Grid(matrix=matrix)
        start_x, start_y = map_grid.get_idx(self.x, self.y)
        start_x = np.clip(start_x, 0, map_grid.x_n-1)
        start_y = np.clip(start_y, 0, map_grid.y_n-1)
        start = grid.node(start_x, start_y)
        end = grid.node(*end_point)
        finder = AStarFinder(diagonal_movement=DiagonalMovement.always)
        path, _ = finder.find_path(start, end, grid)
        return path

    def get_pos(self):
        return self.x, self.y, self.z

    def get_unit_id(self):
        return self.id

    def compute_2d_distance(self, x, y):
        d_x = self.get_pos()[0] - x
        d_y = self.get_pos()[1] - y
        return math.sqrt(math.pow(d_x, 2) + math.pow(d_y, 2))

    def compute_2d_distance_unit(self, unit):
        # 计算本单位与unit的2D距离
        d_x = self.get_pos()[0] - unit.get_pos()[0]
        d_y = self.get_pos()[1] - unit.get_pos()[1]
        return math.sqrt(d_x ** 2 + d_y ** 2)

