import copy

from src.story.pipeline import score_verdict
from src.story.validate import validate_part, validate_plan, validate_title


def card(name, color, hair):
    return {"name": name, "age": "30", "gender": "male", "region": "Kolkata, India", "build": "lean",
            "face_shape": "oval", "eyes": "brown", "eyebrows": "thick", "hair": hair, "skin_tone": "brown",
            "outfit": "khaki shirt", "accessory": "towel", "signature_color": color,
            "anchors": ["a", "b", "c"], "visual_prompt": f"{name} look"}


PLAN = {"title": "The Golden Rickshaw", "category": "moral_fable", "logline": "x", "moral": "Honesty is the richest fare.",
        "parts": 3, "setting": "Kolkata", "cast": [card("Raju", "yellow", "short black"), card("Mira", "red", "long braid")],
        "beats": [{"part": 1, "cliffhanger_type": "reveal", "payoff_next": "p"},
                  {"part": 2, "cliffhanger_type": "betrayal", "payoff_next": "p"},
                  {"part": 3, "cliffhanger_type": None, "payoff_next": None}]}


def panel(i, chars=(), lines=()):
    return {"id": i, "image_prompt": "scene", "duration": 6.5,
            "characters": [{"name": n, "position": "left"} for n in chars],
            "dialogue": [{"speaker": "Raju", "line": l} for l in lines]}


def part(n, total=3):
    p = {"part": n, "title": f"He Found Gold in His Rickshaw… | Pt {n}/{total}", "hook_text": "Whose gold is this?",
         "panels": [panel(i, ["Raju"], ["Short line here."]) for i in range(1, 9)]}
    if n > 1:
        p["previously"] = "Raju found gold."
    if n == total:
        p["moral_card"] = "Honesty is the richest fare."
    return p


def test_title_rules():
    assert validate_title("He Found Gold in His Rickshaw… | Pt 1/3", 1, 3) == []
    assert any("connector" in e for e in validate_title("He Found Gold and | Pt 1/3", 1, 3))
    assert any("end with" in e for e in validate_title("He Found Gold in His Rickshaw", 1, 3))
    assert any("longer" in e for e in validate_title("A" * 55 + " | Pt 1/3", 1, 3))


def test_plan_valid_and_duplicate_colors_rejected():
    assert validate_plan(PLAN) == []
    bad = copy.deepcopy(PLAN)
    bad["cast"][1]["signature_color"] = "yellow"
    assert any("signature_color" in e for e in validate_plan(bad))


def test_plan_requires_payoffs_and_lock_fields():
    bad = copy.deepcopy(PLAN)
    bad["beats"][0]["payoff_next"] = None
    del bad["cast"][0]["accessory"]
    errs = validate_plan(bad)
    assert any("payoff" in e for e in errs) and any("accessory" in e for e in errs)


def test_part_valid():
    names = {"Raju", "Mira"}
    for n in (1, 2, 3):
        assert validate_part(part(n), 3, names) == [], n


def test_part_rules_catch_problems():
    names = {"Raju", "Mira"}
    p = part(3)
    p["panels"][0] = panel(1, ["Raju", "Mira", "Raju"], ["one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen"])
    del p["moral_card"]
    errs = validate_part(p, 3, names)
    assert any("more than 2" in e for e in errs)
    assert any("> 14 words" in e for e in errs)
    assert any("moral_card" in e for e in errs)


def test_judge_thresholds():
    good = {k: 8 for k in ["hook", "clarity", "tension", "twist", "emotion", "cliffhanger", "moral_payoff", "readability"]}
    assert score_verdict({"scores": good | {"safety": 10}})["passed"]
    assert not score_verdict({"scores": good | {"safety": 9}})["passed"]
    assert not score_verdict({"scores": good | {"hook": 7, "safety": 10}})["passed"]


def test_normalize_durations_fits_window():
    from src.story.pipeline import normalize_durations
    p = {"panels": [{"duration": 4.8} for _ in range(8)]}  # 38.4s -> too short
    normalize_durations(p)
    total = sum(x["duration"] for x in p["panels"])
    assert 45 <= total <= 60 and all(4 <= x["duration"] <= 7 for x in p["panels"])
    p = {"panels": [{"duration": 10} for _ in range(9)]}  # 90s -> too long
    normalize_durations(p)
    assert 45 <= sum(x["duration"] for x in p["panels"]) <= 60
