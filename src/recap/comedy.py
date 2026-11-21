"""MC Tuno's recap script writer for The Tuno Report (Takeshi's Castle / Ozzy Man energy, long-form edition).

Every line is built ONLY from real race facts (`src/recap/data.py`), picked deterministically per season/part with
anti-repeat, and kept TTS-friendly (<= ~20 words). Optional Gemini punch-up rewrites only the per-race winner lines
under a strict validator (names from facts only, safe charset, length cap); anything invalid keeps the bank line.
"""
from __future__ import annotations

import json
import os
import random
import re
from dataclasses import dataclass, field
from typing import Any

from src.characters.roster import HERO_BY_KEY
from src.recap.data import RaceInfo, SeasonRecap, part_stats

NUM = {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six", 7: "Seven", 8: "Eight", 9: "Nine", 10: "Ten",
       11: "Eleven", 12: "Twelve", 13: "Thirteen", 14: "Fourteen", 15: "Fifteen", 16: "Sixteen", 17: "Seventeen",
       18: "Eighteen", 19: "Nineteen", 20: "Twenty", 21: "Twenty-one", 22: "Twenty-two", 23: "Twenty-three",
       24: "Twenty-four", 25: "Twenty-five", 26: "Twenty-six", 27: "Twenty-seven", 28: "Twenty-eight",
       29: "Twenty-nine", 30: "Thirty"}
_SAFE = re.compile(r"^[A-Za-z0-9 ,.!?'\-:]+$")


@dataclass
class Line:
    text: str
    style: str = "normal"            # tts prosody: normal | hype | deadpan
    mood: str = "HYPED_TALKING"      # MC Tuno pose while speaking
    kind: str = ""


@dataclass
class Award:
    key: str
    title: str
    subtitle: str
    hero: str
    stat: str
    line: Line
    positive: bool


@dataclass
class RaceLines:
    intro: Line
    verdict: list[Line] = field(default_factory=list)
    lost: Line | None = None


def name(key: str | None) -> str:
    return HERO_BY_KEY[key].name if key in HERO_BY_KEY else "a crash dummy"


def times(n: int) -> str:
    return {1: "once", 2: "twice"}.get(int(n), f"{int(n)} times")


def plural(n: int, word: str) -> str:
    return f"{int(n)} {word}" + ("" if int(n) == 1 else "s")


# ---------------------------------------------------------------------------------------------- banks
ARENA_QUIPS: dict[str, tuple[str, ...]] = {
    "crusher_gauntlet": ("A hallway of giant stamping blocks. Health and safety quit on day one.",
                         "Giant crushers. Basically a panini press for balls."),
    "rotating_disc": ("A spinning pizza of doom. Last one on gets the crown.",
                      "A shrinking spinning disc. Like a merry-go-round with a body count."),
    "pachinko_drop": ("Pachinko. Vegas rules, except the chips scream.",
                      "A peg drop. Pure luck, zero skill. My kind of sport."),
    "sumo_pool_pit": ("Sumo in a paddling pool. Dignity optional.",
                      "A sumo pit. Shove or be shoved."),
    "crumbling_bridge": ("A bridge built by the lowest bidder. It shows.",
                         "A crumbling bridge. The planks have trust issues."),
    "collapse_tower": ("A tower that falls apart on purpose. Like my career.",
                       "A collapsing tower. Architects, look away."),
    "ramp_descent": ("Steep ramps. Gravity's doing the driving.",
                     "Downhill all the way. Brakes not included."),
    "flat_track": ("A flat track. The safest arena. So naturally, carnage.",
                   "Flat and simple. Nothing can go wrong. Famous last words."),
    "pit_platforms": ("Platforms over a bottomless pit. What could go wrong.",
                      "Jump the gaps or fall forever. Easy."),
    "tiered_tower": ("A tower with tiers. And by tiers, I mean tears.",
                     "Drop by drop, tier by tier. Mostly drop."),
    "narrow_bridge": ("A bridge one ball wide. Ten balls. You do the maths.",
                      "A razor-thin bridge. Elbows out."),
    "bouncy_pad_field": ("Bouncy pads everywhere. A trampoline park with a body count.",
                         "Launch pads. Physics has left the chat."),
    "seesaw_gauntlet": ("Seesaws. Playground equipment, now with eliminations.",
                        "Wobbly seesaws. Balance is a myth."),
    "conveyor_chaos": ("Conveyor belts. Airport baggage, but it hates you.",
                       "Runaway conveyors. Going nowhere fast."),
    "maze_corridors": ("A maze. Most of them can't find their own face.",
                       "Twisting corridors. Left, right, panic."),
    "hex_tile_drop": ("Hex tiles that vanish. The floor is temporary, the panic is forever.",
                      "Disappearing tiles. Stand still and you're gone."),
    "bumper_ring": ("A bumper ring. Pinball, but the balls have feelings.",
                    "Bumpers all round. It's a mosh pit with springs."),
}
GOAL_QUIPS: dict[str, str] = {
    "hot_potato_bomb": "Pass the bomb. Don't be holding it when it pops.",
    "hold_a_zone": "Hold the zone, like a toddler with the TV remote.",
    "collect_items": "Grab the most crowns. Greed is good.",
    "survive_timer": "Just survive the clock. The bar is on the floor.",
    "push_others_out": "Shove everyone out. Very on brand.",
}
STAGE_INTROS: dict[str, str] = {
    "play_in": "The Play-In. Seven hopefuls, one playoff seat, zero chill.",
    "qualifier_1": "Qualifier One. Top two seeds. The winner goes straight to the Grand Final.",
    "qualifier_2": "Qualifier Two. Last chance saloon. Two Grand Final tickets left.",
    "grand_final": "The Grand Final. Three balls. One crown. My nerves are shot.",
}
WINNER: dict[str, tuple[str, ...]] = {
    "glitch": ("Glitch wins! Lag is now officially a strategy.",
               "Glitch takes it. Nobody saw him finish, including Glitch.",
               "Glitch wins. Someone check the replay. The replay is buffering."),
    "bonk": ("Bonk wins. He didn't dodge anything. Everything dodged him.",
             "Bonk takes it. Heavy, slow, and somehow first.",
             "Bonk wins! Physics just stopped arguing with him."),
    "pip": ("Pip wins! A ping-pong ball! I need a lie down.",
            "Tiny Pip takes it. Size is just a number. A very small number.",
            "Pip wins. Everyone else just lost to table tennis equipment."),
    "boing": ("Boing wins! He bounced his way there. Steering optional.",
              "Boing takes it. No plan, all spring.",
              "Boing wins. Nobody, including Boing, knows how."),
    "sly": ("Sly wins. Calculated. Smug. Insufferable. Correct.",
            "Sly takes it, and he's already explaining why.",
            "Sly wins. Big brain energy, tiny cue ball."),
    "grumble": ("Grumble wins! And he's still angry about it.",
                "Grumble takes it out of pure spite.",
                "Grumble wins. First smile of the season? Nope. Still scowling."),
    "dash": ("Dash wins! Brakes are for cowards, apparently.",
             "Dash takes it. He didn't stop. He physically can't.",
             "Dash wins. The finish line just happened to be in the way."),
    "magneto": ("Magneto wins. Stuck to the track like gum on a shoe.",
                "Magneto takes it. Attractive performance. Literally.",
                "Magneto wins. Opposites attract. So does first place."),
    "floater": ("Floater wins! Gravity is filing a formal complaint.",
                "Floater drifts home first. Barely tried. Rude.",
                "Floater wins. A beach ball. On a castle death course."),
    "juggernaut": ("Juggernaut wins. He didn't race. He just happened to everyone.",
                   "Juggernaut takes it. Eight and a half kilos of zero apologies.",
                   "Juggernaut wins. The track is going to need counselling."),
}
SPICE: dict[str, tuple[str, ...]] = {
    "lead_self": ("And {W} climbs to the top of the table on {pts}.",
                  "And that puts {W} top of the whole table. Crown polish incoming."),
    "lead_other": ("Plot twist: {L} takes over top spot on {pts}.",
                   "And somehow that hands {L} first place in the table."),
    "streak": ("That's back-to-back wins. Somebody stop {W}.",
               "Two in a row for {W}. This is getting embarrassing for everyone else."),
    "betrayal": ("{K} knocked {V} into orbit along the way. No apology issued.",
                 "Also, {K} binned {V}. Friendship status: over."),
    "menace": ("{K} binned {n} rivals on the way. Absolute menace.",
               "{K} took out {n} balls. That's not racing, that's a crime spree."),
    "dummy": ("Meanwhile, {X} finished behind a crash test dummy. It doesn't even have a brain.",
              "And {X} lost to a crash dummy. A literal dummy."),
    "first_out": ("{X} was first out. Speedrun strats.",
                  "{X} went out first. Didn't even warm up."),
    "first_win": ("First win of the season for {W}. Only took {n} races.",
                  "{W}'s first win of the season. Better late than never."),
    "upset": ("From bottom of the table to the top step. Movie rights pending.",
              "The table's bottom dweller wins one. The castle is shook."),
}
LOST: tuple[str, ...] = (
    "We lost the footage for this one. A crash dummy ate the tape.",
    "No replay here. Juggernaut sat on the camera.",
    "The tape for this one's gone. Pip used it as a hammock.",
)


class Writer:
    def __init__(self, recap: SeasonRecap, seed: int | None = None, log=print) -> None:
        self.recap = recap
        self.log = log
        self.rng = random.Random(seed if seed is not None else recap.season * 100 + (recap.part or 0))
        self.used: dict[str, int] = {}
        self.stats = part_stats(recap)
        self.prev_spice = ""

    # ------------------------------------------------------------------ helpers
    def _pick(self, family: str, options: tuple[str, ...] | list[str]) -> str:
        i = self.used.get(family, self.rng.randrange(len(options)))
        self.used[family] = i + 1
        return options[i % len(options)]

    def _race_word(self, race: int) -> str:
        return f"Race {NUM.get(race, str(race)).lower()}".capitalize()

    # ------------------------------------------------------------------ cold open / title / roster
    def cold_open(self, victim: str) -> list[Line]:
        return [Line(f"Yep. That's {name(victim)}.", "deadpan", "FACEPALM", "cold"),
                Line(f"You're probably wondering how {name(victim)} ended up here.", "deadpan", "FACEPALM", "cold")]

    def title(self) -> Line:
        r, s = self.recap, self.recap.season
        if r.kind == "part1":
            t = "Welcome to the Tuno Report! The first ten races. Ten balls, one crown, zero brain cells between them."
        elif r.kind == "part2":
            t = "Welcome back to the Tuno Report! Races eleven to twenty. It got worse. Much worse."
        elif r.kind == "part3":
            t = f"The Tuno Report, Season {s} finale! The last league races, the playoffs, and one Grand Final."
        else:
            t = f"The Tuno Report! Races {r.start_race} to {r.end_race}. The story so far."
        return Line(t, "hype", "HYPED_TALKING", "title")

    def roster(self) -> Line:
        return Line("Quick introductions. A bowling ball, a ping-pong ball, a beach ball, an iron cube, "
                    "and six more bad decisions.", "normal", "LAUGHING_TEARS", "roster")

    def previously(self) -> Line:
        st = self.recap.stats_entering(self.recap.start_race)
        from src.state import league
        order = league.sorted_standings(st)
        lead, last = order[0], order[-1]
        excuse = self._pick("excuse", ("blamed the wind", "blamed the referee. There is no referee",
                                       "is pretending it's fine"))
        return Line(f"Previously on the Tuno Report: {name(lead[0])} led the table on {lead[1]['points']} points. "
                    f"{name(last[0])} was bottom, and {excuse}.", "normal", "HYPED_TALKING", "previously")

    def playoffs_card(self) -> Line:
        return Line("And now, the playoffs. Lose and you're out. Win and you're still in danger.", "hype",
                    "SWEATING_INTENSE", "playoffs")

    # ------------------------------------------------------------------ races
    def race_intro(self, r: RaceInfo) -> Line:
        from src.publish.metadata import arena_display_name

        if r.stage in STAGE_INTROS:
            return Line(STAGE_INTROS[r.stage], "hype", "SWEATING_INTENSE", "intro")
        quip = self._pick(f"arena.{r.arena}", ARENA_QUIPS.get(r.arena, ("Another arena. Another disaster.",)))
        if r.goal in GOAL_QUIPS and self.rng.random() < 0.5:
            quip = GOAL_QUIPS[r.goal]
        return Line(f"{self._race_word(r.race)}. {arena_display_name(r.arena)}. {quip}", "normal", "HYPED_TALKING",
                    "intro")

    def _spice_options(self, r: RaceInfo, prev: RaceInfo | None) -> list[tuple[str, dict[str, Any]]]:
        W = name(r.winner)
        opts: list[tuple[str, dict[str, Any]]] = []
        if prev is not None and prev.winner == r.winner and r.stage == "league":
            opts.append(("streak", {"W": W}))
        betrayals = [e for e in r.elims if e.get("hero") and e.get("by_hero") and len(e.get("actors") or []) > 1]
        if betrayals:
            e = betrayals[0]
            opts.append(("betrayal", {"K": name(e["actors"][1]), "V": name(e["actors"][0])}))
        if r.ko_counts:
            k, n = max(r.ko_counts.items(), key=lambda kv: (kv[1], kv[0] == r.ko_bonus))
            if n >= 2:
                opts.append(("menace", {"K": name(k), "n": n}))
        if r.behind_dummy:
            seen = self.used.get("dummy_hero", 0)
            x = r.behind_dummy[seen % len(r.behind_dummy)]
            opts.append(("dummy", {"X": name(x)}))
        if r.first_hero_out and r.first_hero_out != r.winner:
            opts.append(("first_out", {"X": name(r.first_hero_out)}))
        wins_before = int(r.stats_before.get(r.winner, {}).get("wins", 0))
        if r.stage == "league" and wins_before == 0 and r.race >= 4:
            opts.append(("first_win", {"W": W, "n": r.race}))
        before = [k for k, _ in r.standings_before]
        if r.stage == "league" and r.race >= 3 and before and before[-1] == r.winner:
            opts.append(("upset", {}))
        return opts

    def race_verdict(self, r: RaceInfo, prev: RaceInfo | None) -> list[Line]:
        W = name(r.winner)
        if r.stage == "grand_final":
            return [Line(f"{W} wins the Grand Final!", "hype", "TROPHY_CHEER", "winner"),
                    Line(f"{W} is your Season {r.season} champion!", "hype", "TROPHY_CHEER", "winner")]
        lines = [Line(self._pick(f"win.{r.winner}", WINNER.get(r.winner, (f"{W} wins!",))), "hype", "TROPHY_CHEER",
                      "winner")]
        if r.stage == "play_in":
            lines.append(Line(f"{W} grabs the last playoff seat. The other six are now spectators.", "normal",
                              "LAUGHING_TEARS", "stage"))
            return lines
        if r.stage == "qualifier_1":
            other = next((k for k in r.hero_ranking if k != r.winner), None)
            lines.append(Line(f"{W} goes straight to the Grand Final. {name(other)} gets one more life.", "normal",
                              "HYPED_TALKING", "stage"))
            return lines
        if r.stage == "qualifier_2":
            adv = [k for k in r.hero_ranking[:2]]
            out = [k for k in r.hero_ranking[2:3]]
            tail = f" {name(out[0])}'s season is over. Thoughts and prayers." if out else ""
            lines.append(Line(f"{name(adv[0])} and {name(adv[1])} make the Grand Final.{tail}", "normal",
                              "FACEPALM" if out else "HYPED_TALKING", "stage"))
            return lines
        if r.lead_changed:
            fam = "lead_self" if r.leader_after == r.winner else "lead_other"
            pts = int(r.stats_after[r.leader_after]["points"])
            txt = self._pick(fam, SPICE[fam]).format(W=W, L=name(r.leader_after), pts=f"{pts} points")
            lines.append(Line(txt, "hype", "SHOCKED_JAWDROP", "lead"))
            self.prev_spice = fam
            return lines
        opts = self._spice_options(r, prev)
        if opts:
            prio = {k: i for i, k in enumerate(("streak", "upset", "betrayal", "menace", "dummy", "first_out",
                                                "first_win"))}
            opts.sort(key=lambda o: (o[0] == self.prev_spice, self.used.get(f"spice.{o[0]}", 0), prio.get(o[0], 9)))
            fam, ctx = opts[0]
            self.used[f"spice.{fam}"] = self.used.get(f"spice.{fam}", 0) + 1
            if fam == "dummy":
                self.used["dummy_hero"] = self.used.get("dummy_hero", 0) + 1
            txt = self._pick(fam, SPICE[fam]).format(**ctx)
            mood = "FACEPALM" if fam in ("dummy", "first_out") else ("SHOCKED_JAWDROP" if fam in ("betrayal", "menace")
                                                                    else "LAUGHING_TEARS")
            lines.append(Line(txt, "deadpan" if fam in ("dummy", "first_out") else "normal", mood, fam))
            self.prev_spice = fam
        return lines

    def footage_lost(self, r: RaceInfo) -> Line:
        if r.winner == "glitch":
            return Line("No footage for this one. Glitch corrupted it. Of course he did.", "deadpan", "FACEPALM", "lost")
        return Line(self._pick("lost", LOST), "deadpan", "FACEPALM", "lost")

    def race_lines(self, r: RaceInfo, prev: RaceInfo | None, has_footage: bool) -> RaceLines:
        rl = RaceLines(intro=self.race_intro(r), verdict=self.race_verdict(r, prev))
        if not has_footage:
            rl.lost = self.footage_lost(r)
        return rl

    def table_check(self, r: RaceInfo) -> Line:
        order = r.standings_after
        lead, last = order[0], order[-1]
        tail = self._pick("bottom", ("has stopped answering my texts", "is bottom, and frankly, it's earned",
                                     "says it's a rebuilding year"))
        if tail.startswith("is bottom"):
            txt = f"Quick table check. {name(lead[0])} leads on {lead[1]} points. {name(last[0])} {tail}."
        else:
            txt = f"Quick table check. {name(lead[0])} leads on {lead[1]} points. {name(last[0])} is last, and {tail}."
        return Line(txt, "normal", "HYPED_TALKING", "table")

    # ------------------------------------------------------------------ awards (The Tunos)
    def awards_intro(self) -> Line:
        return Line("Time for the Tunos. The most prestigious awards in this castle. Also the only ones.", "hype",
                    "TROPHY_CHEER", "awards")

    def awards(self) -> list[Award]:
        st = self.stats
        out: list[Award] = []
        shamed: set[str] = set()

        def best(metric: str, minimum: int, low: bool = False) -> tuple[str, int] | None:
            pool = [(k, v[metric]) for k, v in st.items() if v["races"] > 0]
            if not pool:
                return None
            if low:
                k, n = min(pool, key=lambda kv: (kv[1], -st[kv[0]]["eliminated"], kv[0]))
            else:
                k, n = max(pool, key=lambda kv: (kv[1], st[kv[0]]["points"], kv[0]))
            return (k, n) if (low or n >= minimum) else None

        def again(k: str) -> str:
            return f"{name(k)} again! " if k in shamed else ""

        w = best("wins", 1)
        if w:
            out.append(Award("main_character", "MAIN CHARACTER", "MOST WINS", w[0], plural(w[1], "WIN").upper(),
                             Line(f"The Main Character award goes to {name(w[0])}. {plural(w[1], 'win')}. "
                                  "Everyone else is an extra.", "hype", "TROPHY_CHEER", "award"), True))
        k = best("kos", 2)
        if k:
            out.append(Award("menace", "CERTIFIED MENACE", "MOST KNOCKOUTS", k[0], plural(k[1], "KO").upper(),
                             Line(f"Certified Menace: {name(k[0])}. {plural(k[1], 'knockout')}. "
                                  "The castle's insurance premium has tripled.", "hype", "SHOCKED_JAWDROP", "award"),
                             True))
        s = best("seconds", 2)
        if s:
            out.append(Award("bridesmaid", "ALWAYS THE BRIDESMAID", "MOST SECOND PLACES", s[0],
                             f"2ND {times(s[1]).upper()}",
                             Line(f"Always the Bridesmaid: {name(s[0])}. Second place {times(s[1])}. So close. "
                                  "So, so close.", "deadpan", "FACEPALM", "award"), False))
        d = best("behind_dummy", 1)
        if d:
            shamed.add(d[0])
            out.append(Award("dummy", "BEATEN BY A DUMMY", "LOST TO A CRASH TEST DUMMY", d[0],
                             times(d[1]).upper(),
                             Line(f"The Beaten By A Dummy award. {name(d[0])} lost to a crash test dummy "
                                  f"{times(d[1])}. The dummy's family is very proud.", "deadpan", "LAUGHING_TEARS",
                                  "award"), False))
        f = best("first_out", 1)
        if f:
            pre = again(f[0])
            shamed.add(f[0])
            out.append(Award("speedrun", "SPEEDRUN EXIT", "FIRST HERO OUT", f[0], times(f[1]).upper(),
                             Line(f"{pre}The Speedrun award, for being first out. {name(f[0])}, {times(f[1])}. "
                                  "Efficient. Tragic, but efficient.", "deadpan", "FACEPALM", "award"), False))
        p = best("points", 0, low=True)
        if p:
            pre = again(p[0])
            if p[1] == 0:
                txt = (f"{pre}And the Participation Trophy goes to {name(p[0])}. Zero points. It's made of "
                       "cardboard, and honestly, it's too good for them.")
            else:
                txt = (f"{pre}And the Participation Trophy goes to {name(p[0])}, with {plural(p[1], 'point')}. "
                       "It's made of cardboard. So were the tactics.")
            out.append(Award("participation", "PARTICIPATION TROPHY", "FEWEST POINTS", p[0],
                             plural(p[1], "PT").upper(), Line(txt, "deadpan", "LAUGHING_TEARS", "award"), False))
        return out

    # ------------------------------------------------------------------ cold-open star
    def cold_open_pick(self, eligible_races: set[int]) -> tuple[str, RaceInfo, float] | None:
        """The part's biggest calamity (most first-outs / dummy defeats / eliminations) at a replayable moment."""
        st = self.stats
        ranked = sorted(st, key=lambda k: (3 * st[k]["first_out"] + 2 * st[k]["behind_dummy"] + st[k]["eliminated"]
                                           - st[k]["points"] / 10.0, k), reverse=True)
        for hero in ranked[:4]:
            best = None
            for r in self.recap.part_races:
                if r.race not in eligible_races:
                    continue
                for e in r.elims:
                    acts = e.get("actors") or []
                    if acts and acts[0] == hero and e.get("hero") and float(e.get("t") or 0) >= 2.0:
                        score = (2 if r.first_hero_out == hero else 0) + (1 if e.get("by_hero") else 0)
                        if best is None or score > best[0]:
                            best = (score, r, float(e["t"]))
                        break
            if best:
                return hero, best[1], best[2]
        return None

    # ------------------------------------------------------------------ closing
    def title_race(self) -> Line:
        if self.recap.end_race >= 30:
            return Line("Here's the whole season's title race. Thirty races of pain.", "normal", "HYPED_TALKING", "chart")
        return Line("Here's how the title race has gone, race by race.", "normal", "HYPED_TALKING", "chart")

    def standings(self) -> Line:
        r = self.recap
        order = [(k, int(v["points"])) for k, v in r.standings]
        if r.end_race >= 30:
            return Line(f"And your final Season {r.season} table.", "normal", "HYPED_TALKING", "table")
        (lk, lp), (rk, rp) = order[0], order[1]
        if lp == rp:
            return Line(f"The table after race {r.end_race}. {name(lk)} and {name(rk)} are level on {lp}. Tense.",
                        "normal", "SWEATING_INTENSE", "table")
        return Line(f"The table after race {r.end_race}. {name(lk)} leads by {plural(lp - rp, 'point')}.", "normal",
                    "HYPED_TALKING", "table")

    def champion(self) -> list[Line]:
        c, s = self.recap.champion, self.recap.season
        return [Line(f"Ladies and gentlemen, your Season {s} champion... {name(c)}!", "hype", "TROPHY_CHEER", "champ"),
                Line(f"{name(c)} survived a whole season in this castle. I'd like to see you try.", "normal",
                     "LAUGHING_TEARS", "champ")]

    def teaser(self) -> Line:
        r = self.recap
        if r.kind == "part1":
            t = "Part two lands after race twenty. Same balls, more violence. Comment who you're backing!"
        elif r.kind == "part2":
            t = ("Part three is the big one. Playoffs, a Grand Final, and somebody gets a crown. "
                 "Pick your champion in the comments!")
        elif r.kind == "part3":
            t = f"Season {r.season + 1} starts tomorrow. Brand new theme. Same idiots. Subscribe so you don't miss it."
        else:
            t = "New race every day at eight PM India time. Comment who you're backing!"
        return Line(t, "hype", "HYPED_TALKING", "teaser")

    def outro(self) -> Line:
        return Line("Subscribe, smash that like, and I'll see you in the castle. Probably on fire.", "normal",
                    "LAUGHING_TEARS", "outro")


# ---------------------------------------------------------------------------------------------- optional LLM punch-up
def _valid_winner_line(ln: str, winner: str, allowed: set[str]) -> bool:
    words = ln.split()
    if not (3 <= len(words) <= 16) or not _SAFE.match(ln):
        return False
    low = ln.lower()
    if winner.lower() not in low or "next season" in low:
        return False
    for h in HERO_BY_KEY.values():
        if re.search(rf"\b{re.escape(h.name.lower())}\b", low) and h.name not in allowed:
            return False
    return not any(b in low for b in ("i see", "i am", "lord tuno", "double wipeout", "zero room for error"))


def punch_up_winners(items: list[tuple[RaceInfo, Line]], log=print) -> int:
    """Rewrites per-race winner lines with Gemini when GOOGLE_API_KEY is set and RECAP_LLM != 0. Returns #changed."""
    if not items or os.environ.get("RECAP_LLM", "1") == "0":
        return 0
    key = (os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY") or "").strip()
    if not key:
        log("  [RECAP LLM] GOOGLE_API_KEY not set -> offline comedy bank")
        return 0
    from src.narration import script
    from src.publish.metadata import arena_display_name

    facts = [{"i": i, "winner": name(r.winner), "arena": arena_display_name(r.arena), "stage": r.stage,
              "runner_up": name(r.hero_ranking[1]) if len(r.hero_ranking) > 1 else "", "draft": ln.text}
             for i, (r, ln) in enumerate(items)]
    prompt = ("You are MC Tuno, an unhinged Takeshi's Castle / Ozzy Man Reviews style caster recapping a cartoon "
              "ball-race season on YouTube. Rewrite each draft winner line to be FUNNIER: cheeky, roasty, 6-14 words, "
              "pub-banter energy, must name facts.winner exactly. Only names from facts. Never describe a ball's "
              "material or colour literally. Plain ASCII, no emojis. Return ONLY a JSON array of strings, same "
              "order and length.\n\n" + json.dumps(facts))
    base = "https://generativelanguage.googleapis.com/v1beta"
    lines = None
    cands: list[str] = []
    st, body = script._gemini_http(f"{base}/models?pageSize=100", key, timeout=6.0)
    if st == 200:
        for item in body.get("models", []):
            mname = str(item.get("name", "")).replace("models/", "")
            lm = mname.lower()
            if "generateContent" in (item.get("supportedGenerationMethods") or []) and "flash" in lm and \
                    all(x not in lm for x in ("tts", "image", "audio", "live", "thinking", "8b")):
                cands.append(mname)
        cands.sort(key=lambda s: ("lite" in s, "preview" in s or "exp" in s, s))
    for model in (cands or ["gemini-2.5-flash", "gemini-2.5-flash-lite"])[:4]:
        cfg: dict = {"responseMimeType": "application/json", "temperature": 0.9}
        if model.startswith(("gemini-2.5", "gemini-3")):
            cfg["thinkingConfig"] = {"thinkingBudget": 0}
        payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": cfg}
        code, body = script._gemini_http(f"{base}/models/{model}:generateContent", key, payload, 15.0)
        if code != 200 and "thinkingConfig" in str(body):
            cfg.pop("thinkingConfig", None)
            code, body = script._gemini_http(f"{base}/models/{model}:generateContent", key, payload, 15.0)
        if code == 200:
            try:
                parts = body["candidates"][0]["content"]["parts"]
                lines = script._parse_lines("".join(p.get("text", "") for p in parts if not p.get("thought")))
            except (KeyError, IndexError, TypeError):
                lines = None
            if isinstance(lines, list) and len(lines) == len(items):
                break
        else:
            log(f"  [RECAP LLM] {model} HTTP {code}")
    if not isinstance(lines, list) or len(lines) != len(items):
        log("  [RECAP LLM] unavailable -> offline comedy bank")
        return 0
    n = 0
    for (r, ln), new in zip(items, lines):
        allowed = {name(r.winner)} | ({name(r.hero_ranking[1])} if len(r.hero_ranking) > 1 else set())
        if isinstance(new, str):
            new = " ".join(new.replace("\u2014", "-").replace("\u2019", "'").split())
            if _valid_winner_line(new, name(r.winner), allowed):
                ln.text = new
                n += 1
    log(f"  [RECAP LLM] punched up {n}/{len(items)} winner lines")
    return n
