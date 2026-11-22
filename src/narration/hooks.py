"""Viral hook + one-breath rules for the first ~4 s of every Short.

Line 1 (t = 0.04 s, hype): a scroll-stopping HOOK about this arena (<= 7 words).
Line 2 (right after it, normal): the RULES - what the arena does + how you win (<= 12 words), so a viewer who has never
seen the channel understands the game before the first knockout. Rules lines are fixed text (never LLM-rewritten), so
they always match the real mechanic and goal.
"""
from __future__ import annotations

import random

# arena -> (hooks, mechanic). Mechanic: one short sentence, <= 6 words, no win condition.
ARENA_LINES: dict[str, tuple[tuple[str, ...], str]] = {
    # ---------------------------------------------------------------- v6 arenas
    "glass_bridge": (("Half these glass panels are FAKE!", "One wrong step and you're gone!"),
                     "Fake glass shatters, real glass holds."),
    "red_light": (("Move on red and you get zapped!", "This giant eye sees EVERYTHING!"),
                  "Green means go. Red means freeze."),
    "color_floor": (("Wrong colour? The floor disappears!", "Can you find the right colour in time?"),
                    "Only the called colour stays up."),
    "tilt_table": (("The whole table tilts toward the crowd!", "One heavy ball can sink everyone!"),
                   "The table tips wherever balls bunch up."),
    "whirlpool_drain": (("This whirlpool swallows balls whole!", "Get too close and you're flushed!"),
                        "The current drags everyone to the drain."),
    "spotlight_panic": (("Stay in the light and you burn!", "Those spotlights are hunting them!"),
                        "Sweeping beams zap anyone caught inside."),
    "plinko_cashout": (("One drop. Gold bin or spikes!", "Pure luck decides who survives this!"),
                       "Bounce down the pegs into a bin."),
    "big_bubble": (("Giant bubbles, zero grip. Good luck!", "Land on top or go swimming!"),
                   "Bounce across the bubbles, avoid the water."),
    "spinning_logs": (("These logs roll you straight into the water!", "Can they keep their balance?"),
                      "Spinning logs carry you, or dunk you."),
    "duel_dome": (("Two enter, one goes to the final!", "This dome has a hole in the floor!"),
                  "The floor pocket grows. Don't fall in."),
    "triangle_throne": (("Three corners. Three pits. One throne!", "Only one ball sits on the throne!"),
                        "Every corner is a pit. It shrinks."),
    "needle_drop": (("Fewer safe pads every round!", "Miss the pad and the needles get you!"),
                    "Get on a glowing pad. Needles pop!"),
    "inferno_ascent": (("Climb fast or the lava gets you!", "The lava is rising. Jump!"),
                       "Spring pads launch you up. Lava follows."),
    "knock_doors": (("Which door is the trapdoor?", "One of these doors is a trap!"),
                    "Doors break, bounce you, or drop you."),
    "lily_pads": (("These lily pads sink if you stop!", "Stand still and the frog eats you!"),
                  "Pads sink under you. Keep hopping."),
    "raft_rapids": (("Too many balls and the raft sinks!", "Pick the wrong raft and you drown!"),
                    "Rafts drift and sink under weight."),
    "sweeper_circuit": (("Jump the low arm, duck the high one!", "These sweeper arms show no mercy!"),
                        "Giant arms sweep the track. Time it."),
    "wall_rush": (("Find the hole or get flattened!", "The wall is coming. Pick a lane!"),
                  "Walls slide in. Fit through the gap."),
    "gravity_wells": (("These planets pull you in!", "Get too close to a planet. Gone!"),
                      "Planets pull balls into deadly orbits."),
    "giant_ball_brawl": (("One giant ball. Everyone's a target!", "Shove the giant ball into the goal!"),
                         "Push the giant ball into a goal."),
    "clockwork_cogs": (("Ride the gears or fall forever!", "One bad jump off these gears..."),
                       "Spinning gears are the only floor."),
    "pinball_pit": (("They're the pinballs now!", "Real flippers. Real drain. Real pain!"),
                    "Flippers launch you. The drain kills."),
    "swing_canyon": (("Jump at the wrong time and fall forever!", "These swings are over a bottomless canyon!"),
                     "Ride the swings, jump at the peak."),
    # ---------------------------------------------------------------- legacy arenas
    "ramp_descent": (("Full speed down the ramp of doom!",), "Race down the ramps, dodge the drops."),
    "pachinko_drop": (("A pachinko machine full of balls!",), "Bounce down through the pegs."),
    "crumbling_bridge": (("This bridge is falling apart under them!",), "Tiles crack and drop under weight."),
    "collapse_tower": (("The tower collapses floor by floor!",), "Floors give way. Fire rises."),
    "crusher_gauntlet": (("Giant crushers. Tiny balls. Uh oh!",), "Slip under the crushers before they slam."),
    "flat_track": (("A flat track... what could go wrong?",), "Straight track, pits, and a chasing wall."),
    "pit_platforms": (("Jump the pits or vanish!",), "Hop from platform to platform."),
    "tiered_tower": (("A tower with a nasty way down!",), "Drop down the tiers without falling off."),
    "narrow_bridge": (("This bridge fits one ball. Maybe.",), "One narrow bridge. No railings."),
    "bouncy_pad_field": (("Bounce pads everywhere. Total chaos!",), "Bounce pads fling you forward. Or off."),
    "seesaw_gauntlet": (("Seesaws that flip you into the void!",), "Seesaws tip under weight."),
    "conveyor_chaos": (("The floor is moving. Backwards!",), "Conveyor belts push you around."),
    "rotating_disc": (("The disc spins and shrinks!",), "The spinning disc keeps shrinking."),
    "sumo_pool_pit": (("Sumo, but with a deadly pool!",), "Shove rivals into the pit."),
    "maze_corridors": (("Lost in the maze of doom!",), "Navigate the maze corridors."),
    "hex_tile_drop": (("The floor vanishes tile by tile!",), "Hex tiles drop after you touch them."),
    "bumper_ring": (("Bumpers everywhere. Somebody's flying!",), "Bumpers bounce you toward the edge."),
}

GOAL_LINES: dict[str, str] = {
    "reach_finish": "First to the flag wins!",
    "last_one_standing": "Last ball alive wins!",
    "survive_timer": "Survive the clock to win!",
    "push_others_out": "Knock everyone off to win!",
    "collect_items": "Most crowns wins!",
    "hold_a_zone": "Hold the zone to win!",
    "hot_potato_bomb": "Don't be holding the bomb!",
}

# arena-specific win wording for reach_finish (where "the flag" isn't a flag)
FINISH_LINES: dict[str, str] = {
    "plinko_cashout": "Land in the gold bin to win!",
    "pinball_pit": "Hit the jackpot lane to win!",
    "inferno_ascent": "First to the top wins!",
}

GENERIC_HOOKS = ("Only one ball survives this!", "Pick your ball before it's too late!")


def hook_line(arena: str, rng: random.Random) -> str:
    hooks = ARENA_LINES.get(arena, (GENERIC_HOOKS, ""))[0] or GENERIC_HOOKS
    return rng.choice(list(hooks))


def rules_line(arena: str, goal: str | None, single_winner: bool = False) -> str:
    mech = ARENA_LINES.get(arena, ((), ""))[1]
    g = goal or ""
    if single_winner and g in ("survive_timer", "collect_items", "hold_a_zone"):
        g = "last_one_standing"          # single-winner races play on to ALIVE: 1, so say exactly that
    win = FINISH_LINES.get(arena, "") if g == "reach_finish" else ""
    win = win or GOAL_LINES.get(g, "")
    return " ".join(p for p in (mech, win) if p).strip()
