from lia.system_stats import snapshot


def test_snapshot_keys_and_ranges():
    snap = snapshot(3, False, 14)
    assert 0 <= snap["cpu"] <= 100
    assert 0 <= snap["mem"] <= 100
    assert snap["pedidos_hoje"] == 3
    assert snap["limite"] is False
    assert snap["uso_plano"] == 14


def test_snapshot_without_usage():
    assert snapshot(0, True)["uso_plano"] is None
