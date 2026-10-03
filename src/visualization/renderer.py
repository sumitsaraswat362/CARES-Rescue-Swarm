import pygame
import pygame.gfxdraw
import numpy as np
import math
from typing import Dict, List, Tuple

class Renderer:
    def __init__(self, world, uavs, gcs, width=1280, height=900):
        pygame.init()
        self.width = width
        self.height = height
        self.screen = pygame.display.set_mode((self.width, self.height), pygame.HWSURFACE | pygame.DOUBLEBUF | pygame.SRCALPHA)
        pygame.display.set_caption("CARES — Resilient BVLOS Swarm Control System")
        
        self.world = world
        self.uavs = uavs
        self.gcs = gcs
        
        # Professional fonts
        self.font = pygame.font.SysFont("couriernew", 14)
        self.font_large = pygame.font.SysFont("couriernew", 18, bold=True)
        self.font_title = pygame.font.SysFont("couriernew", 24, bold=True)
        
        # Cyberpunk / Military Palette
        self.colors = {
            'bg': (10, 14, 23),
            'grid': (20, 30, 50),
            'hud_bg': (15, 20, 35, 200),
            'text': (200, 220, 255),
            'text_highlight': (0, 255, 200),
            'gcs': (255, 255, 255),
            'gcs_pulse': (255, 255, 255, 50),
            'obstacle': (255, 50, 50, 30),
            'obstacle_border': (255, 80, 80),
            'poi_un': (255, 80, 0),
            'poi_surv': (0, 255, 100),
            'uav_scout': (0, 220, 255),    # Cyan
            'uav_relay': (255, 150, 0),    # Orange
            'uav_failed': (255, 0, 50),    # Red
            'uav_rtl': (255, 220, 0),      # Yellow
            'uav_recharge': (100, 255, 100),
            'uav_idle': (100, 100, 120),
            'link_strong': (0, 255, 150),
            'link_med': (255, 200, 0),
            'link_weak': (255, 50, 50)
        }
        
        self.scale = 1.0
        if hasattr(self.world, 'width') and hasattr(self.world, 'height'):
            self.scale = min(self.width / self.world.width, self.height / self.world.height)
            
        self.pulse_frame = 0

    def _transform(self, pos: np.ndarray) -> Tuple[int, int]:
        return (int(pos[0] * self.scale), self.height - int(pos[1] * self.scale))

    def _draw_aaline_thick(self, surface, color, start_pos, end_pos, thickness=1):
        """Draw thick anti-aliased line."""
        center_x = (start_pos[0] + end_pos[0]) / 2
        center_y = (start_pos[1] + end_pos[1]) / 2
        length = math.hypot(end_pos[0] - start_pos[0], end_pos[1] - start_pos[1])
        angle = math.atan2(start_pos[1] - end_pos[1], start_pos[0] - end_pos[0])
        
        ul = (center_x + (length/2.) * math.cos(angle) - (thickness/2.) * math.sin(angle),
              center_y + (length/2.) * math.sin(angle) + (thickness/2.) * math.cos(angle))
        ur = (center_x - (length/2.) * math.cos(angle) - (thickness/2.) * math.sin(angle),
              center_y - (length/2.) * math.sin(angle) + (thickness/2.) * math.cos(angle))
        bl = (center_x + (length/2.) * math.cos(angle) + (thickness/2.) * math.sin(angle),
              center_y + (length/2.) * math.sin(angle) - (thickness/2.) * math.cos(angle))
        br = (center_x - (length/2.) * math.cos(angle) + (thickness/2.) * math.sin(angle),
              center_y - (length/2.) * math.sin(angle) - (thickness/2.) * math.cos(angle))
              
        pygame.gfxdraw.aapolygon(surface, (ul, ur, br, bl), color)
        pygame.gfxdraw.filled_polygon(surface, (ul, ur, br, bl), color)

    def _draw_dashed_line(self, surface, color, start_pos, end_pos, width=1, dash_length=10):
        x1, y1 = start_pos
        x2, y2 = end_pos
        dl = math.hypot(x2 - x1, y2 - y1)
        if dl == 0: return
        dashes = int(dl / dash_length)
        for i in range(dashes):
            if i % 2 == 0:
                start = (x1 + (x2-x1) * i/dashes, y1 + (y2-y1) * i/dashes)
                end = (x1 + (x2-x1) * (i+1)/dashes, y1 + (y2-y1) * (i+1)/dashes)
                pygame.draw.line(surface, color, start, end, width)

    def _draw_glow(self, surface, color, pos, radius):
        """Draw a soft glow effect."""
        glow_surf = pygame.Surface((radius*2, radius*2), pygame.SRCALPHA)
        for r in range(radius, 0, -2):
            alpha = int(255 * (1 - r/radius)**2 * 0.3)
            pygame.draw.circle(glow_surf, (*color[:3], alpha), (radius, radius), r)
        surface.blit(glow_surf, (pos[0]-radius, pos[1]-radius), special_flags=pygame.BLEND_ALPHA_SDL2)

    def render(self, metrics: dict, mission_log: list):
        self.screen.fill(self.colors['bg'])
        self.pulse_frame += 1
        
        # 1. Draw Grid
        grid_spacing = int(100 * self.scale)
        if grid_spacing > 0:
            for x in range(0, self.width, grid_spacing):
                pygame.draw.line(self.screen, self.colors['grid'], (x, 0), (x, self.height), 1)
            for y in range(0, self.height, grid_spacing):
                pygame.draw.line(self.screen, self.colors['grid'], (0, y), (self.width, y), 1)

        # 2. Draw Obstacles
        if hasattr(self.world, 'obstacles'):
            for obs in self.world.obstacles:
                pos = self._transform(np.array([obs.x, obs.y]))
                r = int(obs.radius * self.scale)
                
                obs_surf = pygame.Surface((r*2, r*2), pygame.SRCALPHA)
                pygame.draw.circle(obs_surf, self.colors['obstacle'], (r, r), r)
                pygame.draw.circle(obs_surf, self.colors['obstacle_border'], (r, r), r, 2)
                self.screen.blit(obs_surf, (pos[0]-r, pos[1]-r))

        # 3. Draw Recharge Stations
        if hasattr(self.world, 'recharge_stations'):
            for rs in self.world.recharge_stations:
                pos = self._transform(rs.pos)
                pygame.draw.rect(self.screen, (255, 255, 0), (pos[0]-15, pos[1]-15, 30, 30), 2)
                pygame.draw.rect(self.screen, (100, 100, 0), (pos[0]-12, pos[1]-12, 24, 24))
                pygame.draw.line(self.screen, (255,255,0), (pos[0]+5, pos[1]-10), (pos[0]-5, pos[1]+2), 3)
                pygame.draw.line(self.screen, (255,255,0), (pos[0]-5, pos[1]+2), (pos[0]+5, pos[1]+2), 3)
                pygame.draw.line(self.screen, (255,255,0), (pos[0]+5, pos[1]+2), (pos[0]-5, pos[1]+10), 3)

        # 4. Draw PoIs
        if hasattr(self.world, 'pois'):
            for poi in self.world.pois:
                pos = self._transform(np.array([poi.x, poi.y]))
                if getattr(poi, 'surveyed', False):
                    pygame.draw.circle(self.screen, self.colors['poi_surv'], pos, 8)
                    pygame.draw.circle(self.screen, self.colors['poi_surv'], pos, 14, 1)
                else:
                    self._draw_glow(self.screen, self.colors['poi_un'], pos, 25)
                    pygame.draw.circle(self.screen, self.colors['poi_un'], pos, 8)
                    # Pulsing outer ring
                    pulse_r = 12 + math.sin(self.pulse_frame * 0.1) * 4
                    pygame.draw.circle(self.screen, self.colors['poi_un'], pos, int(pulse_r), 2)
                    
                    # Priority text
                    pri_lbl = self.font.render(f"P{getattr(poi, 'priority', 1):.0f}", True, (255,255,255))
                    self.screen.blit(pri_lbl, (pos[0]+12, pos[1]-12))

        # 5. Draw Links (Mesh Network)
        if hasattr(self.gcs, 'compute_connectivity_graph'):
            try:
                graph = self.gcs.compute_connectivity_graph(self.uavs)
                gcs_pos = self._transform(self.world.gcs_pos)
                
                drawn = set()
                for i, neighbors in graph.items():
                    pos_i = gcs_pos if i == -1 else self._transform(self.uavs[i].pos)
                    for j in neighbors:
                        if i == j: continue
                        link = tuple(sorted([i, j]))
                        if link in drawn: continue
                        drawn.add(link)
                        
                        pos_j = gcs_pos if j == -1 else self._transform(self.uavs[j].pos)
                        
                        # Distance determines link color/thickness
                        dist = math.hypot(pos_i[0]-pos_j[0], pos_i[1]-pos_j[1]) / self.scale
                        if dist < 100: color = self.colors['link_strong']
                        elif dist < 150: color = self.colors['link_med']
                        else: color = self.colors['link_weak']
                        
                        self._draw_dashed_line(self.screen, color, pos_i, pos_j, width=2, dash_length=8)
            except Exception:
                pass

        # 6. Draw GCS
        gcs_pos = self._transform(self.world.gcs_pos)
        self._draw_glow(self.screen, self.colors['gcs'], gcs_pos, 40)
        pulse = int(abs(math.sin(self.pulse_frame * 0.05)) * 20)
        pygame.draw.circle(self.screen, (*self.colors['gcs'][:3], 50), gcs_pos, 20 + pulse)
        pygame.draw.polygon(self.screen, self.colors['gcs'], [
            (gcs_pos[0], gcs_pos[1]-15), (gcs_pos[0]+15, gcs_pos[1]), 
            (gcs_pos[0], gcs_pos[1]+15), (gcs_pos[0]-15, gcs_pos[1])
        ])

        # 7. Draw UAVs
        for uav in self.uavs:
            pos = self._transform(uav.pos)
            
            # Determine color based on state
            color = self.colors['uav_idle']
            state = getattr(uav, 'state', None)
            if state == 'scout': color = self.colors['uav_scout']
            elif state == 'relay': color = self.colors['uav_relay']
            elif state == 'failed': color = self.colors['uav_failed']
            elif state == 'return_to_launch': color = self.colors['uav_rtl']
            elif state == 'recharge': color = self.colors['uav_recharge']
            
            self._draw_glow(self.screen, color, pos, 30)
            
            # Heading triangle
            vel = getattr(uav, 'velocity', np.array([0,0]))
            heading = 0
            if np.linalg.norm(vel) > 0.1:
                heading = math.atan2(-vel[1], vel[0]) # -y because pygame y goes down
                
            length = 15
            width = 10
            p1 = (pos[0] + length * math.cos(heading), pos[1] + length * math.sin(heading))
            p2 = (pos[0] + width * math.cos(heading + 2.5), pos[1] + width * math.sin(heading + 2.5))
            p3 = (pos[0] + width * math.cos(heading - 2.5), pos[1] + width * math.sin(heading - 2.5))
            
            pygame.gfxdraw.aapolygon(self.screen, (p1, p2, p3), color)
            pygame.gfxdraw.filled_polygon(self.screen, (p1, p2, p3), color)
            
            # UAV ID Label
            lbl = self.font.render(f"U{uav.id}", True, (255,255,255))
            self.screen.blit(lbl, (pos[0]+15, pos[1]-15))
            
            # Draw assigned task line (thin)
            if hasattr(uav, 'target_pos') and uav.target_pos is not None and state not in ['idle', 'failed']:
                tgt_pos = self._transform(uav.target_pos)
                pygame.draw.line(self.screen, color, pos, tgt_pos, 1)

            # Battery Bar
            if hasattr(uav, 'battery'):
                bat_pct = uav.battery.level
                bat_color = (0, 255, 0) if bat_pct > 0.5 else (255, 255, 0) if bat_pct > 0.2 else (255, 0, 0)
                pygame.draw.rect(self.screen, bat_color, (pos[0]-10, pos[1]+15, int(20*bat_pct), 3))
                pygame.draw.rect(self.screen, (255,255,255), (pos[0]-10, pos[1]+15, 20, 3), 1)

        # 8. Draw HUD Overlay
        hud_w = 300
        hud_h = 350
        hud_surf = pygame.Surface((hud_w, hud_h), pygame.SRCALPHA)
        pygame.draw.rect(hud_surf, self.colors['hud_bg'], (0, 0, hud_w, hud_h), border_radius=10)
        pygame.draw.rect(hud_surf, self.colors['text_highlight'], (0, 0, hud_w, hud_h), 2, border_radius=10)
        self.screen.blit(hud_surf, (20, 20))
        
        title = self.font_title.render("CARES COMMAND HUD", True, self.colors['text_highlight'])
        self.screen.blit(title, (35, 35))
        
        hud_y = 75
        fields = [('sim_time','Time (s)'), ('delivered_completion_pct','Delivered (%)'),
                  ('acquired_completion_pct','Acquired (%)'), ('all_uav_connectivity_pct','Connected (%)'),
                  ('hop_pdr_pct','Hop PDR (%)'), ('pending_observations','Pending'),
                  ('separation_violation_frames','Unsafe frames'), ('mbb_handoffs_completed','Handoffs')]
        for k, label in fields:
            v = metrics.get(k)
            k = label
            if isinstance(v, float): text = f"{k.upper()}: {v:.2f}"
            else: text = f"{k.upper()}: {v}"
            lbl = self.font_large.render(text, True, self.colors['text'])
            self.screen.blit(lbl, (35, hud_y))
            hud_y += 30
            
        # Draw Event Log (Bottom Left)
        log_h = 180
        log_w = 500
        log_y_start = self.height - log_h - 20
        log_surf = pygame.Surface((log_w, log_h), pygame.SRCALPHA)
        pygame.draw.rect(log_surf, self.colors['hud_bg'], (0, 0, log_w, log_h), border_radius=5)
        self.screen.blit(log_surf, (20, log_y_start))
        
        log_title = self.font_large.render("SYSTEM EVENTS LOG", True, self.colors['text_highlight'])
        self.screen.blit(log_title, (30, log_y_start + 10))
        
        ly = log_y_start + 40
        for log in mission_log[-6:]:
            if isinstance(log, dict) and 'message' in log:
                msg = f"[{log.get('time', 0.0):.1f}s] {log['message']}"
            else:
                msg = str(log)
            lbl = self.font.render(msg, True, (200, 200, 200))
            self.screen.blit(lbl, (30, ly))
            ly += 22

        # Draw Keyboard Controls (Bottom Right)
        ctrl_text = "[SPACE] Pause  [+] Speed Up  [-] Speed Down  [F] Inject Fault  [P] Inject PoI  [ESC] Quit"
        ctrl_lbl = self.font.render(ctrl_text, True, (150, 150, 150))
        self.screen.blit(ctrl_lbl, (self.width - ctrl_lbl.get_width() - 20, self.height - 30))

        pygame.display.flip()
        
    def handle_events(self) -> dict:
        events = {
            'quit': False, 'pause': False, 'speed_change': 0.0,
            'inject_failure': False, 'inject_poi': False
        }
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                events['quit'] = True
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE: events['quit'] = True
                elif event.key == pygame.K_SPACE: events['pause'] = True
                elif event.key == pygame.K_EQUALS: events['speed_change'] = 1.0
                elif event.key == pygame.K_MINUS: events['speed_change'] = -1.0
                elif event.key == pygame.K_f: events['inject_failure'] = True
                elif event.key == pygame.K_p: events['inject_poi'] = True
        return events

    def cleanup(self):
        pygame.quit()
