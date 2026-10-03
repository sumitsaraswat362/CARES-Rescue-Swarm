import pytest
import numpy as np
from src.core.uav import UAV, UAVState

def test_camera_cone_accumulation():
    uav = UAV(1, [0, 0], {})
    uav.state = UAVState.SCOUT
    uav.altitude = 40.0
    uav.target_pos = np.array([0.0, 0.0]) # same position
    uav.assigned_task_id = 1
    uav.survey_radius = 30.0
    
    # Distance = 0, Altitude = 40 -> perfect conditions (0.15 per sec)
    dt = 1.0
    uav.update(dt, 0.0)
    assert uav.detection_confidence > 0.0
    assert uav.detection_confidence < 0.2
    
    # Fast forward to completion
    for _ in range(7):
        uav.update(dt, 0.0)
    assert 1 not in uav.tasks_completed  # Confidence alone cannot bypass the 10 s dwell.
    for _ in range(3):
        uav.update(dt, 0.0)
    assert 1 in uav.tasks_completed
    assert uav.assigned_task_id is None
    assert uav.detection_confidence == 0.0 # Resets after completion

def test_camera_cone_altitude_penalty():
    uav1 = UAV(1, [0, 0], {})
    uav1.state = UAVState.SCOUT
    uav1.altitude = 40.0
    uav1.target_pos = np.array([0.0, 0.0])
    uav1.assigned_task_id = 1
    
    uav2 = UAV(2, [0, 0], {})
    uav2.state = UAVState.SCOUT
    uav2.altitude = 80.0 # Higher altitude -> slower
    uav2.target_pos = np.array([0.0, 0.0])
    uav2.assigned_task_id = 2
    
    dt = 1.0
    uav1.update(dt, 0.0)
    uav2.update(dt, 0.0)
    
    assert uav2.detection_confidence < uav1.detection_confidence
    
if __name__ == "__main__":
    pytest.main(["-v", "test_synthetic_vision.py"])
