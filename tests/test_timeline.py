"""§4 timeline (with the owner's 2026-11-20 pacing override): every segment inside its limits and the total video
lands in the 20-28 s v3.0 retention target (validation range 20-50 s)."""
from src.config import TIMELINE, settings


def test_segments_inside_limits():
    t = TIMELINE
    assert 0.0 <= t.cold_open_s <= 1.5 and t.flash_forward_s <= 1.5
    assert t.gameplay_target_min_s < t.gameplay_target_max_s <= t.forced_resolution_s <= t.hard_stop_s
    starts = [e[0] for e in t.escalation]
    assert starts == sorted(starts) and starts[0] == 0 and starts[-1] < t.forced_resolution_s
    assert [e[1] for e in t.escalation] == [1.0, 1.3, 1.65]
    assert abs(t.replay_source_s / t.replay_s - t.replay_speed) < 0.01
    assert 2.5 <= t.winner_card_s <= 3.0 and t.loop_tail_s == 0.0


def test_total_duration_range():
    t, v = TIMELINE, settings()["video"]
    for gameplay in (t.gameplay_target_min_s, t.gameplay_target_max_s, t.hard_stop_s):
        for ff in (0.0, t.flash_forward_s):
            total = ff + t.cold_open_s + gameplay + t.tail_s()
            assert v["duration_min_s"] <= total <= v["duration_max_s"]
    for gameplay in (t.gameplay_target_min_s, t.gameplay_target_max_s):
        assert 22.0 <= t.cold_open_s + gameplay + t.tail_s() <= 32.0


def test_two_stage_fits():
    t = TIMELINE
    total = t.two_stage_qualifier_s + t.two_stage_sting_s + t.two_stage_final_s
    assert t.gameplay_target_min_s <= total <= t.gameplay_target_max_s


def test_speed_steps():
    t = TIMELINE
    s1, s2 = t.escalation[1][0], t.escalation[2][0]
    assert t.speed_at(s1 - 0.5) == 1.0 and t.speed_at(s1 + 0.5) == 1.3 and t.speed_at(s2 + 1) == 1.65
