"""Versioned analytic environment fixtures, not calibrated aircraft/geodata models.

Coordinates and heights are metres; altitude is above the declared datum. Terrain
is a plane plus x-aligned triangular ridges, so segment clearance is exact at its
piecewise-linear breakpoints. Coverage is a cell-centre raster estimate.
"""
import math
import numpy as np


class TerrainModel:
    version = 'cares-terrain/v1'

    def __init__(self, spec=None):
        self.spec = spec or {}
        self.base = float(self.spec.get('base_m', 0))
        self.sx = float(self.spec.get('slope_x', 0))
        self.sy = float(self.spec.get('slope_y', 0))
        self.ridges = [dict(r) for r in self.spec.get('ridges', [])]
        values = [self.base,self.sx,self.sy]
        for r in self.ridges:
            values.extend([r['x_m'],r['half_width_m'],r['height_m']])
            if r['half_width_m'] <= 0 or r['height_m'] < 0:
                raise ValueError('Ridge width must be positive and height nonnegative')
        if not all(math.isfinite(v) for v in values):
            raise ValueError('Terrain parameters must be finite')

    def height(self, x, y):
        return float(self.base+self.sx*x+self.sy*y+sum(
            r['height_m']*max(0,1-abs(x-r['x_m'])/r['half_width_m']) for r in self.ridges))

    def breakpoints(self, a, b):
        points = {0.,1.}
        if b[0] != a[0]:
            for r in self.ridges:
                for x in (r['x_m']-r['half_width_m'],r['x_m'],r['x_m']+r['half_width_m']):
                    t=(x-a[0])/(b[0]-a[0])
                    if 0<t<1:points.add(t)
        return sorted(points)

    def clear(self, a, b, clearance=0):
        return all(a[2]+t*(b[2]-a[2]) >= self.height(a[0]+t*(b[0]-a[0]),a[1]+t*(b[1]-a[1]))+clearance-1e-9
                   for t in self.breakpoints(a,b))


class CameraModel:
    version = 'cares-camera/v1'

    def __init__(self, fov_deg=60, min_agl_m=10, max_agl_m=120, max_speed_mps=1):
        if not 0<fov_deg<180 or not 0<min_agl_m<=max_agl_m or max_speed_mps<=0:
            raise ValueError('Invalid camera bounds')
        self.fov_deg,self.min_agl_m,self.max_agl_m,self.max_speed_mps=fov_deg,min_agl_m,max_agl_m,max_speed_mps

    def radius(self, agl):
        return agl*math.tan(math.radians(self.fov_deg/2))

    def accepts(self, position, target, speed, terrain):
        agl=position[2]-terrain.height(*position[:2])
        return (self.min_agl_m<=agl<=self.max_agl_m and speed<self.max_speed_mps
                and math.dist(position[:2],target)<=self.radius(agl)
                and terrain.clear(position,[*target,terrain.height(*target)]))


class CoverageGrid:
    def __init__(self,width,height,cell_m=10):
        if min(width,height,cell_m)<=0:raise ValueError('Positive coverage dimensions required')
        self.width,self.height,self.cell_m=width,height,cell_m
        self.cells=set()

    def observe(self, position, camera, terrain):
        agl=position[2]-terrain.height(*position[:2])
        if not camera.min_agl_m<=agl<=camera.max_agl_m:return
        r=camera.radius(agl);s=self.cell_m
        for ix in range(max(0,math.floor((position[0]-r)/s)),min(math.ceil(self.width/s),math.floor((position[0]+r)/s)+1)):
            for iy in range(max(0,math.floor((position[1]-r)/s)),min(math.ceil(self.height/s),math.floor((position[1]+r)/s)+1)):
                point=[(ix*s+min(self.width,(ix+1)*s))/2,(iy*s+min(self.height,(iy+1)*s))/2]
                if math.dist(position[:2],point)<=r and terrain.clear(position,[*point,terrain.height(*point)]):
                    self.cells.add((ix,iy))

    @property
    def area_m2(self):
        return sum(min(self.cell_m,self.width-x*self.cell_m)*min(self.cell_m,self.height-y*self.cell_m) for x,y in self.cells)


def bounded_velocity(velocity, desired, dt, max_accel):
    if dt<=0 or max_accel<=0:raise ValueError('Positive timestep and acceleration required')
    change=np.asarray(desired)-np.asarray(velocity);norm=float(np.linalg.norm(change))
    return np.asarray(velocity)+change*min(1.,max_accel*dt/max(norm,1e-12))


def extra_power_w(airspeed, climb_speed, mass_kg, payload_kg=0, efficiency=.7, drag_coefficient=0):
    if mass_kg<=0 or payload_kg<0 or not 0<efficiency<=1 or drag_coefficient<0:
        raise ValueError('Invalid energy parameters')
    # No regenerative descent credit. Payload hover term is an explicit synthetic
    # assumption (20 W/kg), not an identified motor/propeller model.
    return float((mass_kg+payload_kg)*9.80665*max(0,climb_speed)/efficiency+20*payload_kg+drag_coefficient*abs(airspeed)**3)
