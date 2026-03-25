from hud.cost import estimate_cost


def test_estimate_cost_zero_tokens():
    assert estimate_cost(0, 0) == 0.0


def test_estimate_cost_input_only():
    # 1M input tokens at $3/M = $3.0
    result = estimate_cost(1_000_000, 0)
    assert abs(result - 3.0) < 0.0001


def test_estimate_cost_output_only():
    # 1M output tokens at $15/M = $15.0
    result = estimate_cost(0, 1_000_000)
    assert abs(result - 15.0) < 0.0001


def test_estimate_cost_combined():
    # 100k input + 50k output
    result = estimate_cost(100_000, 50_000)
    expected = 100_000 / 1_000_000 * 3.0 + 50_000 / 1_000_000 * 15.0
    assert abs(result - expected) < 0.0001
