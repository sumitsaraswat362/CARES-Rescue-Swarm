from types import SimpleNamespace
from src.px4_bridge.topics import topic_name


def test_versioned_status_and_unversioned_position_are_distinct():
    assert topic_name('/px4_1/', 'out', 'vehicle_status', SimpleNamespace(MESSAGE_VERSION=1)) == '/px4_1/fmu/out/vehicle_status_v1'
    assert topic_name('', 'out', 'vehicle_local_position', SimpleNamespace(MESSAGE_VERSION=0)) == '/fmu/out/vehicle_local_position'
    assert topic_name('', 'in', 'offboard_control_mode', SimpleNamespace()) == '/fmu/in/offboard_control_mode'
