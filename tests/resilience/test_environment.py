import math
from types import SimpleNamespace
import numpy as np
import pytest
from src.resilience.environment import TerrainModel,CameraModel,CoverageGrid,bounded_velocity,extra_power_w
from src.resilience.planner import Planner
from tests.resilience.test_transport import net


def test_exact_slope_and_thin_ridge_clearance():
    terrain=TerrainModel({'base_m':2,'slope_x':.1,'ridges':[{'x_m':5,'half_width_m':.01,'height_m':10}]})
    assert terrain.height(10,0)==3
    assert not terrain.clear([0,0,10],[10,0,10]) # Thin peak cannot be skipped by sample spacing.
    assert terrain.clear([0,0,13],[10,0,13])
    with pytest.raises(ValueError):TerrainModel({'ridges':[{'x_m':0,'half_width_m':0,'height_m':1}]})


def test_terrain_changes_radio_and_planner_feasibility():
    t,_=net(range_m=500)
    t.world.terrain=TerrainModel({'ridges':[{'x_m':50,'half_width_m':10,'height_m':30}]})
    for u in t.vehicles:u.altitude=10
    t.refresh(0)
    assert t.edges[-1,0]==0
    t.world.terrain=TerrainModel();t.refresh(0)
    assert t.edges[-1,0]>0
    world=SimpleNamespace(width=100,height=100,obstacles=[],terrain=TerrainModel({'ridges':[{'x_m':50,'half_width_m':10,'height_m':30}]}),terrain_ceiling_m=25)
    assert not Planner(world).plan([10,50],[90,50])


def test_camera_agl_footprint_speed_and_occlusion():
    camera=CameraModel(fov_deg=60);terrain=TerrainModel({'base_m':20})
    assert camera.accepts([0,0,50],[10,0],0,terrain)
    assert not camera.accepts([0,0,25],[0,0],0,terrain)
    assert not camera.accepts([0,0,50],[20,0],0,terrain)
    assert not camera.accepts([0,0,50],[0,0],1,terrain)
    ridge=TerrainModel({'ridges':[{'x_m':5,'half_width_m':1,'height_m':25}]})
    assert not camera.accepts([0,0,30],[10,0],0,ridge)


def test_coverage_union_partial_boundary_cells_no_double_count():
    grid=CoverageGrid(25,20,10);camera=CameraModel(fov_deg=90);terrain=TerrainModel()
    grid.observe([12.5,10,30],camera,terrain)
    assert len(grid.cells)==6 and grid.area_m2==500
    grid.observe([12.5,10,30],camera,terrain)
    assert grid.area_m2==500


def test_acceleration_and_energy_units_timestep_convergence():
    for dt in (.1,.05):
        velocity=np.zeros(2);position=np.zeros(2)
        for _ in range(round(2/dt)):
            previous=velocity.copy();velocity=bounded_velocity(velocity,[10,0],dt,2)
            assert np.linalg.norm(velocity-previous)<=2*dt+1e-9
            position+=(velocity+previous)*.5*dt
        assert velocity[0]==pytest.approx(4)
        assert position[0]==pytest.approx(4)
    power=extra_power_w(0,2,2,0,1,0)
    assert power==pytest.approx(2*9.80665*2)
    assert power*5/3600==pytest.approx(2*9.80665*10/3600)
    assert extra_power_w(0,-2,2,0,1,0)==0
    assert extra_power_w(10,0,2,.5,1,.01)==20


def test_environment_runtime_exports_real_json(tmp_path):
    import json
    import yaml
    from src.resilience.runtime import Runtime
    spec=yaml.safe_load(open('scenarios/analytic_environment_v2.yaml'))
    spec['simulation']['duration_s']=1
    path=tmp_path/'fixture.yaml';path.write_text(yaml.safe_dump(spec))
    runtime=Runtime(str(path))
    while runtime.mission.running:runtime.step()
    runtime.save(tmp_path/'run')
    result=json.loads((tmp_path/'run/final_report.json').read_text())
    assert 'mapped_area_estimate_m2' in result
    assert result['duration_s']==1


def test_leaving_target_resets_continuous_survey_dwell():
    from src.core.uav import UAV
    u=UAV(0,[0,0],{})
    u.assign_scout_task(1,np.array([100.,0.]),0)
    u.survey_timer=9;u.detection_confidence=.9
    u.update(.1,1,np.zeros(2))
    assert u.survey_timer==0 and u.detection_confidence==0
