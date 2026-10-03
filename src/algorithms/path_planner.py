import numpy as np
import heapq
from typing import List, Tuple

class PathPlanner:
    def __init__(self, world, grid_resolution=20.0):
        self.world = world
        self.grid_resolution = grid_resolution

    def _pos_to_grid(self, pos: np.ndarray) -> Tuple[int, int]:
        return (int(pos[0] // self.grid_resolution), int(pos[1] // self.grid_resolution))

    def _grid_to_pos(self, grid: Tuple[int, int]) -> np.ndarray:
        return np.array([grid[0] * self.grid_resolution + self.grid_resolution / 2, 
                         grid[1] * self.grid_resolution + self.grid_resolution / 2])
                         
    def _is_collision(self, grid: Tuple[int, int], custom_obstacles=None) -> bool:
        pos = self._grid_to_pos(grid)
        import os
        import numpy as np
        reactive = os.environ.get("CARES_REACTIVE_SENSING", "0") == "1"
        
        if reactive:
            if custom_obstacles is None:
                return False  # Start with blank map
            else:
                for obs in custom_obstacles:
                    if np.linalg.norm(pos - np.array([obs['x'], obs['y']])) <= obs['radius'] + 5.0:
                        return True
                return False
        else:
            if hasattr(self.world, 'is_in_obstacle'):
                return self.world.is_in_obstacle(pos)
            return False

    def plan_with_obstacles(self, start: np.ndarray, goal: np.ndarray, obstacles, uav_battery=None, uav_speed: float = 10.0) -> List[np.ndarray]:
        return self.plan(start, goal, uav_battery, uav_speed, custom_obstacles=obstacles)

    def plan(self, start: np.ndarray, goal: np.ndarray, uav_battery=None, uav_speed: float = 10.0, custom_obstacles=None) -> List[np.ndarray]:
        start_grid = self._pos_to_grid(start)
        goal_grid = self._pos_to_grid(goal)
        
        if self._is_collision(goal_grid, custom_obstacles):
            # Goal is inside obstacle
            return []
            
        open_set = []
        heapq.heappush(open_set, (0, start_grid))
        
        came_from = {}
        g_score = {start_grid: 0}
        
        def heuristic(a, b):
            return np.sqrt((a[0]-b[0])**2 + (a[1]-b[1])**2)
            
        f_score = {start_grid: heuristic(start_grid, goal_grid)}
        
        # Battery budget pre-computation
        energy_budget_j = float('inf')
        joules_per_meter = 6.6
        if uav_battery:
            # current_wh * 3600 = Joules
            available_j = uav_battery.current_wh * 3600.0
            reserve_j = uav_battery.capacity_wh * uav_battery.warning_threshold * 3600.0
            energy_budget_j = max(0.0, available_j - reserve_j)
            joules_per_meter = uav_battery.cruise_power_w / max(uav_speed, 0.1)
            
            # Quick fail: If straight-line distance to goal + straight-line from goal to charger exceeds budget, skip A* entirely!
            straight_line_dist = float(np.linalg.norm(start - goal))
            if hasattr(self.world, 'nearest_recharge_station'):
                _, rtl_dist = self.world.nearest_recharge_station(goal)
            else:
                rtl_dist = 0.0
            min_energy_required = (straight_line_dist + rtl_dist) * joules_per_meter
            if min_energy_required > energy_budget_j:
                return []
        
        while open_set:
            current = heapq.heappop(open_set)[1]
            
            if current == goal_grid:
                path = []
                while current in came_from:
                    path.append(self._grid_to_pos(current))
                    current = came_from[current]
                path.append(start)
                path.reverse()
                
                return self._smooth_path(path)
                
            for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)]:
                neighbor = (current[0] + dx, current[1] + dy)
                
                if self._is_collision(neighbor, custom_obstacles):
                    continue
                    
                dist_step = np.sqrt(dx**2 + dy**2) * self.grid_resolution
                
                # Wind-aware cost: headwind = costs more, tailwind = costs less
                step_dir = np.array([dx, dy], dtype=np.float64)
                if np.linalg.norm(step_dir) > 0:
                    step_dir /= np.linalg.norm(step_dir)
                wind = getattr(self.world, 'wind_vector', np.zeros(2))
                wind_component = float(np.dot(wind, step_dir))  # positive = tailwind
                # Cost multiplier: headwind (negative) increases cost, tailwind reduces it
                wind_cost_factor = max(0.5, 1.0 - wind_component / max(uav_speed, 1.0))
                
                energy_step_cost = dist_step * joules_per_meter * wind_cost_factor * (1.1 if dx != 0 and dy != 0 else 1.0)
                
                tentative_g_score = g_score[current] + energy_step_cost
                
                # Check RTL budget (can we make it back to the nearest charger from this node?)
                if uav_battery and hasattr(self.world, 'nearest_recharge_station'):
                    pos_neighbor = self._grid_to_pos(neighbor)
                    _, rtl_dist = self.world.nearest_recharge_station(pos_neighbor)
                    rtl_cost_j = rtl_dist * joules_per_meter
                    if tentative_g_score + rtl_cost_j > energy_budget_j:
                        continue  # Prune this path, exceeds battery budget
                
                
                if neighbor not in g_score or tentative_g_score < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g_score
                    f_score[neighbor] = tentative_g_score + heuristic(neighbor, goal_grid) * self.grid_resolution * 6.6
                    heapq.heappush(open_set, (f_score[neighbor], neighbor))
                    
        return [] # No path found

    def _smooth_path(self, path: List[np.ndarray]) -> List[np.ndarray]:
        if len(path) <= 2:
            return path
            
        smoothed = [path[0]]
        for i in range(1, len(path) - 1):
            # Simplistic smoothing: just include points that change direction
            v1 = path[i] - smoothed[-1]
            v2 = path[i+1] - path[i]
            n1 = v1 / (np.linalg.norm(v1) + 1e-8)
            n2 = v2 / (np.linalg.norm(v2) + 1e-8)
            
            if np.dot(n1, n2) < 0.99: # Direction change
                smoothed.append(path[i])
        smoothed.append(path[-1])
        return smoothed

    def path_energy_cost(self, path: List[np.ndarray], cruise_power_w: float, speed: float) -> float:
        total_dist = 0.0
        for i in range(len(path) - 1):
            total_dist += np.linalg.norm(path[i+1] - path[i])
        
        # Energy = Power * Time = Power * (Distance / Speed)
        return cruise_power_w * (total_dist / max(speed, 0.1))

