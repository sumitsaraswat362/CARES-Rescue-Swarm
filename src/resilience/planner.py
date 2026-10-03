"""Bounded A* on the preflight map, with segment checks and exact endpoints."""
import heapq
import math
import numpy as np

def _grid_to_world(node, resolution):
    """Convert integer grid node to float64 world coordinates."""
    return np.array(node, dtype=np.float64) * resolution

class Planner:
    def __init__(self,world,resolution=25):
        self.world=world;self.resolution=resolution;self.cache={};self.unreachable=set()
    def clear(self,a,b):
        a=np.asarray(a,dtype=np.float64);b=np.asarray(b,dtype=np.float64)
        if not(0<=b[0]<=self.world.width and 0<=b[1]<=self.world.height):return False
        if hasattr(self.world,'terrain'):
            z=self.world.terrain_ceiling_m
            if not self.world.terrain.clear([*a,z],[*b,z]):return False
        v=b-a
        for o in self.world.obstacles:
            oc=np.asarray(o.center,dtype=np.float64)
            t=float(np.clip(np.dot(oc-a,v)/max(float(np.dot(v,v)),1e-9),0,1))
            if float(np.linalg.norm(a+t*v-oc))<o.radius+5:return False
        return True
    def plan(self,start,goal,**kwargs):
        a=np.asarray(start,dtype=np.float64);b=np.asarray(goal,dtype=np.float64)
        if a.shape != (2,) or b.shape != (2,) or not np.isfinite([a,b]).all():
            raise ValueError('Planner endpoints must be finite 2D coordinates')
        if not self.clear(a,a) or not self.clear(b,b):return []
        if self.clear(a,b):return [a.copy(),b.copy()]
        r=self.resolution
        def anchor(point):
            center=tuple(int(x) for x in np.rint(point/r))
            candidates=[(center[0]+dx,center[1]+dy) for dx in (-1,0,1) for dy in (-1,0,1)]
            valid=[v for v in candidates if self.clear(point,_grid_to_world(v,r))]
            return min(valid,key=lambda v:(float(np.linalg.norm(_grid_to_world(v,r)-point)),v)) if valid else None
        s,g=anchor(a),anchor(b)
        if s is None or g is None:return []
        key=(s,g)
        if key in self.unreachable:return []
        if key in self.cache:
            path=[a.copy()]+[p.copy() for p in self.cache[key]]+[b.copy()]
            if all(self.clear(x,y) for x,y in zip(path,path[1:])):return path
        todo=[(0,s)];cost={s:0};parent={};visited=set()
        while todo:
            _,u=heapq.heappop(todo)
            if u in visited:continue
            visited.add(u)
            if u==g:
                nodes=[]
                while u!=s:nodes.append(_grid_to_world(u,r));u=parent[u]
                nodes.reverse();nodes=[_grid_to_world(s,r)]+nodes;path=[a.copy()]+nodes+[b.copy()]
                if not all(self.clear(x,y) for x,y in zip(path,path[1:])):return []
                self.cache[key]=nodes
                return path
            for dx,dy in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
                v=(u[0]+dx,u[1]+dy)
                if v in visited or not self.clear(_grid_to_world(u,r),_grid_to_world(v,r)):continue
                c=cost[u]+math.hypot(dx,dy)
                if c<cost.get(v,math.inf):
                    cost[v]=c;parent[v]=u
                    heapq.heappush(todo,(c+math.hypot(v[0]-g[0],v[1]-g[1]),v))
        self.unreachable.add(key)
        return []
