"""Standard-library sensor/terrain evidence reconstruction, independent of runtime."""
import math


def ground(spec,x,y):
    plane=spec.get('base_m',0)+spec.get('slope_x',0)*x+spec.get('slope_y',0)*y
    return plane+sum(r['height_m']*max(0,1-abs(x-r['x_m'])/r['half_width_m']) for r in spec.get('ridges',[]))


def segment_clear(spec,position,destination):
    fractions=[0.,1.]
    if destination[0]!=position[0]:
        for ridge in spec.get('ridges',[]):
            for x in [ridge['x_m']-ridge['half_width_m'],ridge['x_m'],ridge['x_m']+ridge['half_width_m']]:
                fraction=(x-position[0])/(destination[0]-position[0])
                if 0<fraction<1:fractions.append(fraction)
    for t in fractions:
        point=[a+(b-a)*t for a,b in zip(position,destination)]
        if point[2]+1e-9<ground(spec,*point[:2]):return False
    return True


def visible(spec,position,target):
    return segment_clear(spec,position,[*target,ground(spec,*target)])

def camera_valid(model,position,velocity,target):
    terrain=model.get('terrain',{});camera=model.get('camera',{})
    agl=position[2]-ground(terrain,*position[:2])
    radius=agl*math.tan(math.radians(camera.get('fov_deg',60)/2))
    return (camera.get('min_agl_m',10)<=agl<=camera.get('max_agl_m',120)
            and math.hypot(*velocity)<camera.get('max_speed_mps',1)
            and math.dist(position[:2],target)<=radius and visible(terrain,position,target))


def mapped_cells(model,world,position,velocity):
    terrain=model.get('terrain',{});camera=model.get('camera',{})
    agl=position[2]-ground(terrain,*position[:2]);size=model.get('coverage_cell_m',10)
    if not camera.get('min_agl_m',10)<=agl<=camera.get('max_agl_m',120) or math.hypot(*velocity)>=camera.get('max_speed_mps',1):return set()
    radius=agl*math.tan(math.radians(camera.get('fov_deg',60)/2));cells=set()
    # Enumerate only bounding-box cells, then reconstruct centre containment.
    for x in range(max(0,int(math.floor((position[0]-radius)/size))),min(math.ceil(world['width']/size),int((position[0]+radius)//size)+1)):
        for y in range(max(0,int(math.floor((position[1]-radius)/size))),min(math.ceil(world['height']/size),int((position[1]+radius)//size)+1)):
            target=[(x*size+min(world['width'],(x+1)*size))/2,(y*size+min(world['height'],(y+1)*size))/2]
            if math.dist(position[:2],target)<=radius and visible(terrain,position,target):cells.add((x,y))
    return cells
