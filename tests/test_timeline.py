"""§4: every timeline segment stays inside its limits; total typical length 34-44 s, validation range 25-50 s."""
from src.config import TIMELINE, settings


def test_segments_inside_limits():
    t = TIMELINE
    assert t.cold_open_s == 0.5 and t.flash_forward_s == 1.0
    assert t.gameplay_target_min_s == 26 and t.gameplay_target_max_s == 36
    assert t.forced_resolution_s <= t.hard_stop_s == 38
    assert [e[0] for e in t.escalation] == [0, 12, 22] and [e[1] for e in t.escalation] == [1.0, 1.3, 1.65]
    assert t.replay_s == 2.2 and t.replay_speed == 0.4 and t.winner_card_s == 2.5 and t.loop_tail_s == 0.4


def test_total_duration_range():
    t, v = TIMELINE, settings()["video"]
    for gameplay in (t.gameplay_target_min_s, t.gameplay_target_max_s, t.hard_stop_s):
        for ff in (0.0, t.flash_forward_s):
            total = ff + t.cold_open_s + gameplay + t.tail_s()
            assert v["duration_min_s"] <= total <= v["duration_max_s"]
    typical = t.cold_open_s + 31 + t.tail_s()
    assert 34 <= typical <= 44


def test_two_stage_fits():
    t = TIMELINE
    total = t.two_stage_qualifier_s + t.two_stage_sting_s + t.two_stage_final_s
    assert t.gameplay_target_min_s <= total <= t.gameplay_target_max_s


def test_speed_steps():
    t = TIMELINE
    assert t.speed_at(5) == 1.0 and t.speed_at(12.5) == 1.3 and t.speed_at(30) == 1.65
