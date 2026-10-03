from tools.qualification import jobs_for


def test_frozen_protocol_counts_unique_seeds_and_paired_inputs():
    jobs = jobs_for(['qualification', 'confirmation', 'burst'])
    assert len(jobs) == 600
    assert len({j['seed'] for j in jobs}) == 50
    assert len({j['id'] for j in jobs}) == 600
    for a, b in zip(jobs[::2], jobs[1::2]):
        assert a['side'] == 'reference' and b['side'] == 'candidate'
        assert all(a[k] == b[k] for k in ('stage', 'scenario', 'seed', 'mode', 'burst'))
    assert all(j['burst'] == .15 for j in jobs if j['stage'] == 'burst')
    assert all(j['burst'] is None for j in jobs if j['stage'] != 'burst')


def test_development_seeds_do_not_overlap_qualification():
    development = {j['seed'] for j in jobs_for(['development'])}
    qualification = {j['seed'] for j in jobs_for(['qualification', 'confirmation', 'burst'])}
    assert not development & qualification


def test_resume_rejects_tampered_raw_artifacts(tmp_path):
    import json
    import pytest
    from tools.qualification import artifact_hashes, execute_job
    job={'id':'example','side':'candidate'}
    directory=tmp_path/'example';directory.mkdir()
    raw=directory/'raw_trace.jsonl';raw.write_text('original\n')
    receipt={'job':job,'passed':False,'artifacts_sha256':artifact_hashes(directory)}
    (directory/'attempt.json').write_text(json.dumps(receipt))
    assert execute_job(job,{},tmp_path,1)==receipt
    raw.write_text('modified\n')
    with pytest.raises(ValueError,match='artifacts changed'):
        execute_job(job,{},tmp_path,1)
