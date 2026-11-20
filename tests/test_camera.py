"""Camera (§15 + owner review): no gameplay frame may show an empty screen while anyone is alive."""
import random

from src.characters.roster import HEROES, make_extras
from src.config import W
from src.games import recipe_generator
from src.physics import trace as T
from src.physics.camera import track
from src.physics.engine import Sim


def _empty_frames(arena: str, goal: str, seed: int) -> int:
    r, _ = recipe_generator.generate([], 1, seed, arena=arena, goal=goal)
    rng = random.Random(seed)
    tr = Sim(r, list(HEROES), make_extras(4, rng), seed).run()
    bad = 0
    for f, c in enumerate(track(tr)):
        alive = [i for i in range(len(tr.keys)) if tr.flags[f][i] & T.ALIVE]
        seen = [i for i in alive if 0 < c.to_screen(*tr.frames[f][i][:2])[0] < W
                and 330 < c.to_screen(*tr.frames[f][i][:2])[1] < 1650]
        bad += bool(alive) and not seen
    return bad


def test_never_empty_side():
    for arena, goal in (("flat_track", "reach_finish"), ("tiered_tower", "last_one_standing")):
        assert _empty_frames(arena, goal, 4242) == 0


def test_never_empty_top():
    assert _empty_frames("rotating_disc", "push_others_out", 7) == 0
