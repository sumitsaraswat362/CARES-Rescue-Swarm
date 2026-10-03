import json

import pytest

from tools.diagnose_connectivity import diagnose


def write_trace(tmp_path, states):
    frames = []
    for time, state, radio_failed, edges in states:
        frames.append({'time': time, 'dt': 1.0, 'uavs': [
            {'id': 0, 'state': state, 'radio_failed': radio_failed, 'position': [0, 0, 10]}],
            'edges': edges})
    (tmp_path / 'raw_trace.jsonl').write_text('\n'.join(json.dumps(f) for f in frames))
    (tmp_path / 'run_manifest.json').write_text(json.dumps({'seed': 1, 'source_sha256': 'fixture'}))


def test_radio_failure_keeps_original_denominator_and_labels_exclusion(tmp_path):
    write_trace(tmp_path, [(1, 'idle', False, [[0, -1]]),
                           (2, 'idle', True, []), (3, 'failed', True, [])])
    result = diagnose(tmp_path)
    assert result['all_active_connected_pct'] == pytest.approx(100 / 3)
    assert result['all_radio_capable_survivors_connected_pct'] == 100
    assert result['operational_population_time_s'] == 1
    assert result['permanent_radio_exclusion_present_s'] == 1
    assert result['disconnections'][0]['start_s'] == 1
    assert result['disconnections'][0]['end_s'] == 2
    assert result['population_transitions'][1]['excluded'] == [{'id': 0, 'reason': 'radio_failed'}]


def test_empty_operational_population_is_undefined(tmp_path):
    write_trace(tmp_path, [(1, 'idle', True, [])])
    assert diagnose(tmp_path)['all_radio_capable_survivors_connected_pct'] is None


def test_directed_multihop_graph_and_recovery_interval(tmp_path):
    write_trace(tmp_path, [(1, 'idle', False, [[0, 1], [1, -1]]),
                           (2, 'idle', False, [[-1, 0]]),
                           (3, 'idle', False, [[0, -1]])])
    result = diagnose(tmp_path)
    assert result['all_active_connected_pct'] == pytest.approx(200 / 3)
    assert result['per_vehicle']['0']['no_graph_route_s'] == 1
    assert result['disconnections'][0]['duration_s'] == 1
    assert result['disconnections'][0]['reason'] == 'no_graph_route'
