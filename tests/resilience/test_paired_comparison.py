from tools.compare_runs import paired_interval


def test_no_samples_do_not_make_a_confidence_claim():
    assert paired_interval([]) is None


def test_small_identical_results_are_not_statistical_qualification():
    result = paired_interval([0, 0])
    assert result['mean_difference'] == 0
    assert result['bootstrap_95_low'] == result['bootstrap_95_high'] == 0
    assert not result['sample_size_at_least_30']


def test_paired_interval_is_reproducible_and_handles_mixed_effects():
    values = [-20, -10, 0, 10, 20] * 6
    result = paired_interval(values)
    assert result == paired_interval(values)
    assert result['mean_difference'] == 0
    assert result['bootstrap_95_low'] < 0 < result['bootstrap_95_high']
