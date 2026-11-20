"""§17.2: 730 consecutive episodes (1 year at 2/day) with zero hard-rule violations and zero deadlocks."""
from src.games import recipe_generator as rg


def test_year_of_episodes_has_no_hard_violations():
    hist: list[dict] = []
    relaxed_count = 0
    for ep in range(730):
        day = ep // 2
        r, relaxed = rg.generate(hist, day, seed=1000 + ep)
        relaxed_count += bool(relaxed)
        # hard rules 1-3 are never relaxed
        assert not (rg._violations(r, hist, day) & {1, 2, 3}), f"episode {ep} violates a hard rule"
        hist.append(rg.history_entry(r, day))
    keys = [(h["arena"], h["goal"], tuple(h["hazards"]), h["twist"]) for h in hist]
    for i, k in enumerate(keys):   # rule 1 re-checked directly: no exact repeat within 365 days
        assert k not in keys[max(0, i - 730):i] or hist[keys.index(k, max(0, i - 730))]["day"] <= hist[i]["day"] - 365
    assert relaxed_count < 730 * 0.25


def test_goal_never_consecutive_and_compatible():
    hist: list[dict] = []
    for ep in range(200):
        r, _ = rg.generate(hist, ep // 2, seed=ep)
        if hist:
            assert r.goal != hist[-1]["goal"]
        assert rg.fits(rg.GOALS[r.goal], r.mode)
        assert all(rg.fits(rg.HAZARDS[h], r.mode) for h in r.hazards)
        assert r.twist is None or rg.twist_fits(r.twist, r.mode, r.arena)
        hist.append(rg.history_entry(r, ep // 2))
