from src import server


def test_duplicate_pause_reset_and_stale_generation():
    s=server.SimState();s.init('scenarios/relay_required.yaml')
    generation=s.generation
    cmd={'action':'pause','command_id':'pause-1','generation':generation}
    first=server.handle_command(s,cmd)
    assert first['status']=='accepted' and s.mission.paused
    assert server.handle_command(s,cmd)==first and s.mission.paused
    reset={'action':'reset','command_id':'reset-1','generation':generation}
    receipt=server.handle_command(s,reset)
    assert s.generation==generation+1
    assert server.handle_command(s,reset)==receipt and s.generation==generation+1
    stale={'action':'kill_uav','uav_id':0,'command_id':'stale','generation':generation}
    assert server.handle_command(s,stale)['status']=='rejected'
    assert s.mission.uavs[0].state.value!='failed'
    receipts=server.serialize_state(s)['command_receipts']
    assert any(r['command_id']=='reset-1' and r['status']=='accepted' for r in receipts)


def test_conflicting_id_and_invalid_commands_do_not_mutate_mission():
    s=server.SimState();s.init('scenarios/relay_required.yaml')
    server.handle_command(s,{'action':'pause','command_id':'same'})
    assert server.handle_command(s,{'action':'reset','command_id':'same'})['status']=='rejected'
    assert s.generation==1 and s.mission.paused
    assert server.handle_command(s,{'action':'kill_uav','uav_id':'0'})['status']=='rejected'
    assert server.handle_command(s,{'action':'unknown'})['status']=='rejected'
    assert server.handle_command(s,[])['status']=='rejected'
