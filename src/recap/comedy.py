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
    mid: Line | None = None


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
                  "And that puts {W} top of the whole table. Crown polish incoming.",
                  "{W} wins it AND takes the league lead. Greedy.", "Top of the table now: {W}, on {pts}."),
    "lead_other": ("Plot twist: {L} takes over top spot on {pts}.",
                   "And somehow that hands {L} first place in the table.",
                   "New name at the top: {L}, on {pts}.", "And just like that, {L} is the league leader."),
    "streak": ("That's back-to-back wins. Somebody stop {W}.",
               "Two in a row for {W}. This is getting embarrassing for everyone else.",
               "{W} again! Is anyone else even trying?"),
    "betrayal": ("{K} knocked {V} into orbit along the way. No apology issued.",
                 "Also, {K} binned {V}. Friendship status: over.",
                 "Special mention to {K} for ending {V} mid-race."),
    "menace": ("{K} binned {n} rivals on the way. Absolute menace.",
               "{K} took out {n} balls. That's not racing, that's a crime spree.",
               "{n} knockouts for {K} in one race. Someone confiscate that ball."),
    "dummy": ("Meanwhile, {X} finished behind a crash test dummy. It doesn't even have a brain.",
              "And {X} lost to a crash dummy. A literal dummy.",
              "Shout out to the crash dummy that beat {X}. Career highlight."),
    "first_out": ("{X} was first out. Speedrun strats.",
                  "{X} went out first. Didn't even warm up.",
                  "First one gone? {X}. Of course."),
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



def skeleton(text: str) -> str:
    """Line 'shape' used by the zero-repeat ledger: hero names, dummies and numbers blanked, punctuation dropped,
    so 'K with zero remorse. Bye, V.' counts as ONE line no matter who it's about."""
    s = (text or "").lower()
    for h in HERO_BY_KEY.values():
        s = re.sub(rf"\b{re.escape(h.name.lower())}\b", "#", s)
    s = re.sub(r"\ba crash dummy\b|\bdummy #?\d+\b", "#", s)
    s = re.sub(r"\d+", "0", s)
    for w in NUM.values():
        s = re.sub(rf"\b{w.lower()}\b", "0", s)
    s = re.sub(r"[^a-z0# ]", " ", s)
    return " ".join(s.split())


def favour_of(r: RaceInfo) -> str | None:
    """Hero key an arena was built to favour (Season 2+ recipes carry `favour`), else None."""
    try:
        fav = ((r.record or {}).get("recipe") or {}).get("favour")
    except AttributeError:
        return None
    return fav if (fav in HERO_BY_KEY and fav in (r.heroes or [])) else None


BIOME_QUIPS: dict[str, tuple[str, ...]] = {
    "night": ("Night race. Nobody can see a thing, including the balls.", "Lights out. Brains were already out."),
    "storm": ("Storm's rolling in. Perfect weather for terrible decisions.", "Thunder, lightning, and ten idiots."),
    "lava": ("Lava hour. The floor is literally lava. Tell your friends.", "Everything is on fire. Business as usual."),
    "sunset": ("Sunset race. Romantic. Violent, but romantic.", "Golden hour. Golden carnage."),
    "dawn": ("Dawn raid. Way too early for this.", "Sunrise race. Nobody has had their coffee."),
    "day": ("Blue skies. A false sense of security.", "Lovely day for it. It won't stay lovely."),
}
GENERIC_ARENA_QUIPS: tuple[str, ...] = (
    "Same castle, fresh disaster.", "The architect has been fired. Again.", "Health and safety did not sign off.",
    "Somebody built this on purpose.", "Pray for the balls.")
FAVOUR_INTROS: tuple[str, ...] = (
    "Fair warning, this course was basically built for {X}.", "This one suits {X}. Everyone else, good luck.",
    "The castle has a favourite today, and it's {X}.")
WIN_GENERIC: tuple[str, ...] = (
    "{W} takes it! Somebody check the rule book.", "And {W} wins! I did not have that on my bingo card.",
    "{W} gets it done. Messy, loud, and first.", "Victory for {W}! The crowd goes mild.",
    "{W} wins it. Don't ask me how. I was watching and I still don't know.")
KO_BY_FLAVOUR: dict[str, tuple[str, ...]] = {
    "bonk": ("{K} didn't even move, and {V} bounced into the void!", "{V} ran into {K}. {K} won that argument."),
    "pip": ("Tiny {K} takes out {V}! Humiliating!", "{V} just got bullied off by a ping-pong ball!"),
    "boing": ("{K} boings straight through {V}!", "{V} got trampolined into oblivion by {K}!"),
    "sly": ("{K} saw that coming three moves ago. Bye, {V}.", "Textbook from {K}. {V} never saw the angle."),
    "grumble": ("{K} bins {V} and still looks furious about it!", "{K} hates everyone, and {V} just found out."),
    "dash": ("{K} hits {V} at full speed! No brakes, no mercy!", "{V} got run over by the {K} express!"),
    "magneto": ("{K} drags {V} in close, then spits him out!", "Magnet menace! {K} yanks {V} right off the track!"),
    "floater": ("{K} drifts over and nudges {V} off! So rude!", "Death by beach ball! {V} is out, courtesy of {K}!"),
    "juggernaut": ("{K} flattens {V}. Like a bus through a hedge.", "{V} met {K}. {V} is no longer with us."),
    "glitch": ("{K} lagged straight into {V}, and {V} just vanished!", "Glitch in the matrix! {K} deletes {V}!"),
}
KO_BY_GENERIC: tuple[str, ...] = (
    "Betrayal! {K} bins {V}!", "{K} sends {V} into orbit!", "{V} is gone, courtesy of {K}!",
    "{K} chose violence, and {V} paid for it!", "And {K} evicts {V}!", "Hit and run! {K} on {V}!",
    "Ooh, {K} on {V}! That'll leave a dent!", "{V} trusted {K}. Big mistake.", "{K} clears {V} off the map!",
    "Sorry {V}, {K} needed the space!", "{K} bowls {V} clean off the course!", "{V} gets the {K} special. Goodnight!")
KO_SOLO_FLAVOUR: dict[str, tuple[str, ...]] = {
    "bonk": ("The heaviest ball in the castle, gone! Bonk is out!",),
    "pip": ("Pip blows away like a crisp packet!",),
    "boing": ("Boing bounced the wrong way. Bye!",),
    "sly": ("So much for the big brain. Sly is out!",),
    "grumble": ("Grumble is out, and he's going to complain about this for weeks!",),
    "dash": ("Dash couldn't stop. Dash never stops. Dash is gone!",),
    "magneto": ("Even the grip couldn't save Magneto!",),
    "floater": ("Floater just drifts off into the abyss. Peaceful, honestly.",),
    "juggernaut": ("Juggernaut is down! The ground felt that one!",),
    "glitch": ("Glitch has disconnected. Permanently.",),
}
KO_SOLO_GENERIC: tuple[str, ...] = (
    "{V} is out!", "Down goes {V}!", "Bye bye, {V}!", "{V} has left the building!", "And {V} falls off the planet!",
    "{V}, no! Gone!", "That's the end of {V}!", "{V} takes the express lift down!", "Farewell, {V}. Nobody will miss you.",
    "{V} is history!")
EVENT_CALLS: dict[str, tuple[str, ...]] = {
    "ot": ("Overtime! Total chaos now!", "Overtime! The castle wants blood!", "Overtime, and it's getting silly!"),
    "shrink": ("The arena is shrinking! Nowhere to hide!", "It's shrinking! Squeeze time!"),
    "speed": ("Speed up! Hold onto something!", "Faster! Nobody asked for faster!", "The track just hit fast forward!"),
    "rev": ("Controls reversed! Pure panic!", "Reversed controls! Left is right now!"),
    "grav": ("Gravity just changed its mind!", "Gravity's gone weird!"),
    "any": ("Here comes a twist!", "Oh, the castle has a surprise!", "Plot twist incoming!"),
}
FINAL_CALLS: tuple[str, ...] = (
    "Final stretch! Here we go!", "Into the endgame now!", "It all comes down to this!", "Endgame! Don't blink!",
    "Last few seconds! Hold your breath!", "Here's your finish!", "Business end of the race!",
    "Moment of truth!", "The crown is right there!", "Somebody has to win this. Unfortunately.")
FILLERS: tuple[str, ...] = (
    "Absolute scenes in the castle.", "Nobody here is steering. Nobody.", "Physics is having a terrible day.",
    "This is beautiful, beautiful chaos.", "The crash dummies look more confident than the heroes.",
    "Somebody call the insurance company.", "I've seen better driving at a bumper car funeral.",
    "This is why we can't have nice things.", "My lawyer says I can't comment on this.",
    "Not a single brain cell on the track.", "Ten balls, zero plans.", "That's not a race, that's a pinball machine.",
    "If you're just joining us, I'm so sorry.", "Every single one of them is panicking. I love it.",
    "Pure carnage, and we're not even done.", "Hold on, the commentary box is shaking.",
    "Somebody pass me the popcorn.", "I genuinely can't tell who's winning.", "They're all trying. It's not working.",
    "The castle eats balls for breakfast.", "Do not try this at home. Or anywhere.",
    "The physics engine is screaming.", "Someone call a ref. Oh wait, we fired him.", "Rolling chaos, folks.")
FACT_LEADER: tuple[str, ...] = (
    "{X} came into this one top of the table on {n}.", "Remember, {X} leads the league on {n} points.",
    "{X} is the one to catch. {n} points and counting.")
FACT_DUMMY: tuple[str, ...] = (
    "Fun fact, {X} has already lost to a crash dummy {n}.", "{X} has been beaten by a dummy {n} this season. Watch.")
FACT_KOS: tuple[str, ...] = (
    "{X} has {n} knockouts this season. Keep your distance.", "Careful near {X}. {n} knockouts already.")
FACT_WINLESS: tuple[str, ...] = (
    "{X} is still hunting a first win this season.", "{X} needs a win. Badly.")
REPLAY_INTROS: dict[str, tuple[str, ...]] = {
    "tight": ("Closer. Closer. Look at the face on {W}.", "Let's zoom in on that finish.",
              "Up close and personal with the finish.", "Here it is, nice and close."),
    "wide": ("Wide angle. Watch the whole mess unfold.", "Pull back. Look at all of that.",
             "From up here you can see every bad decision.", "The full picture. It's not pretty."),
    "rewind": ("Rewind that! Rewind!", "Hang on, run it back!", "Again! Back it up!", "Wait, wait, wind it back."),
}
POST_TABLE: tuple[str, ...] = (
    "{X} sits top of the table on {n}.", "Table check: {X} leads on {n}.", "{X} still top of the pile on {n}.",
    "That leaves {X} leading on {n}.", "Top spot belongs to {X}, on {n}.")
POST_NEXT: tuple[str, ...] = (
    "Right. {R} next.", "Next race. Brace yourselves.", "Onwards. {R}.", "Moving on, before anyone sues.",
    "Deep breath. {R}.", "Okay. Next.")


class Writer:
    def __init__(self, recap: SeasonRecap, seed: int | None = None, log=print) -> None:
        self.recap = recap
        self.log = log
        self.rng = random.Random(seed if seed is not None else recap.season * 100 + (recap.part or 0))
        self.used: dict[str, int] = {}
        self.stats = part_stats(recap)
        self.prev_spice = ""
        self.said: set[str] = set()      # zero-repeat ledger of line skeletons (names/numbers blanked)

    # ------------------------------------------------------------------ helpers
    def _fresh(self, family: str, options: tuple[str, ...] | list[str]) -> str | None:
        """Next option (rotating per family) whose skeleton has NOT been spoken in this video, else None."""
        if not options:
            return None
        start = self.used.get(family, self.rng.randrange(len(options)))
        for j in range(len(options)):
            txt = options[(start + j) % len(options)]
            sk = skeleton(txt)
            if sk not in self.said:
                self.said.add(sk)
                self.used[family] = start + j + 1
                return txt
        return None

    def _pick(self, family: str, options: tuple[str, ...] | list[str]) -> str:
        txt = self._fresh(family, options)
        if txt is not None:
            return txt
        i = self.used.get(family, self.rng.randrange(len(options)))
        self.used[family] = i + 1
        return options[i % len(options)]

    def mark(self, text: str) -> None:
        self.said.add(skeleton(text))

    def is_fresh(self, text: str) -> bool:
        return skeleton(text) not in self.said

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
        from src.state import league
        new = [k for k in (self.recap.final_stats or {}) if k in HERO_BY_KEY and k not in league.BASE_ROSTER]
        if new:
            names = " and ".join(name(k) for k in new[:2])
            return Line(f"Quick introductions. The usual idiots, every one with a power, plus two rookies: {names}. "
                        "Welcome to the castle. Sorry in advance.", "normal", "LAUGHING_TEARS", "roster")
        return Line("Quick introductions. Every ball has a power. A wall, a trick shot, a magnet, a beach ball, "
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
        from src.rendering import biomes

        if r.stage in STAGE_INTROS:
            return Line(STAGE_INTROS[r.stage], "hype", "SWEATING_INTENSE", "intro")
        biome = biomes.biome_for(r.season, r.race)
        quip = None
        if r.goal in GOAL_QUIPS and self.rng.random() < 0.5:
            quip = self._fresh(f"goal.{r.goal}", (GOAL_QUIPS[r.goal],))
        if quip is None and biome != "day" and r.race % 2 == 0:
            quip = self._fresh(f"biome.{biome}", BIOME_QUIPS.get(biome, ()))
        if quip is None:
            quip = self._fresh(f"arena.{r.arena}", ARENA_QUIPS.get(r.arena, ()))
        if quip is None:
            quip = self._fresh(f"biome.{biome}", BIOME_QUIPS.get(biome, ()))
        if quip is None:
            quip = self._pick("arena.any", GENERIC_ARENA_QUIPS)
        fav = favour_of(r)
        if fav:
            fav_line = self._fresh("favour", tuple(t.format(X=name(fav)) for t in FAVOUR_INTROS))
            if fav_line:
                quip = f"{fav_line}"
        A = arena_display_name(r.arena)
        rw = self._race_word(r.race)
        forms = (f"{rw}. {A}.", f"Next up, {A}.", f"{rw} takes us to {A}.", f"Here's {rw.lower()}. {A}.",
                 f"On to {A} for {rw.lower()}.", f"{rw}, and it's {A}.")
        return Line(f"{forms[r.race % len(forms)]} {quip}", "normal", "HYPED_TALKING", "intro")

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
        win_txt = self._fresh(f"win.{r.winner}", WINNER.get(r.winner, ())) or \
            (self._fresh("win.any", tuple(t.format(W=W) for t in WIN_GENERIC)) or f"{W} wins!")
        lines = [Line(win_txt, "hype", "TROPHY_CHEER", "winner")]
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
            tpl = self._fresh(fam, SPICE[fam])
            if tpl:
                txt = tpl.format(W=W, L=name(r.leader_after), pts=f"{pts} points")
                lines.append(Line(txt, "hype", "SHOCKED_JAWDROP", "lead"))
                self.prev_spice = fam
                return lines
        opts = self._spice_options(r, prev)
        if opts:
            prio = {k: i for i, k in enumerate(("streak", "upset", "betrayal", "menace", "dummy", "first_out",
                                                "first_win"))}
            opts.sort(key=lambda o: (o[0] == self.prev_spice, self.used.get(f"spice.{o[0]}", 0), prio.get(o[0], 9)))
            for fam, ctx in opts:
                tpl = self._fresh(fam, SPICE[fam])
                if not tpl:
                    continue
                self.used[f"spice.{fam}"] = self.used.get(f"spice.{fam}", 0) + 1
                if fam == "dummy":
                    self.used["dummy_hero"] = self.used.get("dummy_hero", 0) + 1
                txt = tpl.format(**ctx)
                mood = "FACEPALM" if fam in ("dummy", "first_out") else ("SHOCKED_JAWDROP" if fam in ("betrayal", "menace")
                                                                        else "LAUGHING_TEARS")
                lines.append(Line(txt, "deadpan" if fam in ("dummy", "first_out") else "normal", mood, fam))
                self.prev_spice = fam
                break
        return lines

    def footage_lost(self, r: RaceInfo) -> Line:
        if r.winner == "glitch":
            return Line("No footage for this one. Glitch corrupted it. Of course he did.", "deadpan", "FACEPALM", "lost")
        return Line(self._pick("lost", LOST), "deadpan", "FACEPALM", "lost")

    def _peek(self, family: str, options: tuple[str, ...] | list[str], n: int = 1) -> list[str]:
        """Up to n not-yet-spoken options (rotating per family) WITHOUT claiming them. Live lines are only claimed
        when the scheduler actually places them, so unused candidates never burn the bank."""
        if not options:
            return []
        start = self.used.get(family, self.rng.randrange(len(options)))
        self.used.setdefault(family, start)
        out, seen = [], set()
        for j in range(len(options)):
            txt = options[(start + j) % len(options)]
            sk = skeleton(txt)
            if sk in self.said or sk in seen:
                continue
            seen.add(sk)
            out.append(txt)
            if len(out) >= n:
                break
        return out

    def claim(self, line: Line) -> bool:
        """Marks a line as spoken; False if its skeleton was already used in this video (caller must skip it)."""
        sk = skeleton(line.text)
        if sk in self.said:
            return False
        self.said.add(sk)
        return True

    def unclaim(self, line: Line) -> None:
        self.said.discard(skeleton(line.text))

    def race_mid(self, r: RaceInfo) -> Line | None:
        betrayals = [e for e in r.elims if e.get("hero") and e.get("by_hero") and len(e.get("actors") or []) > 1]
        if betrayals:
            e = betrayals[-1]
            k_nm, v_nm = name(e["actors"][1]), name(e["actors"][0])
            opts = self._peek("mid.betray", (
                f"Oh! {k_nm} just launched {v_nm} straight into next week!",
                f"Cold blooded from {k_nm}! {v_nm} never stood a chance.",
                f"Look at {k_nm} choosing violence on {v_nm} mid-race!",
            ))
            return Line(opts[0], "hype", "SHOCKED_JAWDROP", "mid") if opts else None
        if r.first_hero_out and r.first_hero_out != r.winner:
            fo = name(r.first_hero_out)
            opts = self._peek("mid.first", (
                f"{fo} is already in the pit, and we are barely halfway through!",
                f"Early exit for {fo}. Absolute disasterclass in progress.",
                f"Down goes {fo}! Now the survivors are getting desperate.",
            ))
            return Line(opts[0], "normal", "LAUGHING_TEARS", "mid") if opts else None
        runner = name(r.hero_ranking[1]) if len(r.hero_ranking) > 1 else name(r.winner)
        opts = self._peek("mid.pack", (
            f"Final stretch now, and {runner} is clinging on by pure panic!",
            f"Bodies flying everywhere! {runner} is fighting for dear life out there!",
            "Three left in the endgame! Zero grip, zero mercy, maximum panic!",
        ))
        return Line(opts[0], "hype", "SWEATING_INTENSE", "mid") if opts else None

    def race_lines(self, r: RaceInfo, prev: RaceInfo | None, has_footage: bool) -> RaceLines:
        rl = RaceLines(intro=self.race_intro(r), verdict=self.race_verdict(r, prev))
        if has_footage:
            rl.mid = self.race_mid(r)
        else:
            rl.lost = self.footage_lost(r)
        return rl

    # ------------------------------------------------------------------ live play-by-play (synced to footage)
    def ko_call(self, victim: str, killer: str | None) -> Line | None:
        """A never-repeated KO call. Personality flavour first (killer's style / victim's style), then generic."""
        V = name(victim)
        if killer and killer in HERO_BY_KEY and killer != victim:
            K = name(killer)
            opts = [t.format(K=K, V=V) for t in KO_BY_FLAVOUR.get(killer, ())] + \
                [t.format(K=K, V=V) for t in KO_BY_GENERIC]
            got = self._peek(f"ko.by.{killer}", opts)
            return Line(got[0], "hype", "SHOCKED_JAWDROP", "ko") if got else None
        opts = [t.format(V=V) for t in KO_SOLO_FLAVOUR.get(victim, ())] + [t.format(V=V) for t in KO_SOLO_GENERIC]
        got = self._peek(f"ko.solo.{victim}", opts)
        return Line(got[0], "hype", "LAUGHING_TEARS", "ko") if got else None

    def event_call(self, banner: str, overtime: bool = False) -> Line | None:
        b = (banner or "").upper()
        if overtime or "OVERTIME" in b:
            fam = "ot"
        elif "SHRINK" in b:
            fam = "shrink"
        elif "SPEED" in b:
            fam = "speed"
        elif "REVERS" in b:
            fam = "rev"
        elif "GRAVITY" in b:
            fam = "grav"
        elif b:
            fam = "any"
        else:
            return None
        got = self._peek(f"ev.{fam}", EVENT_CALLS[fam])
        return Line(got[0], "hype", "SWEATING_INTENSE", "event") if got else None

    def final_call(self) -> Line | None:
        got = self._peek("final", FINAL_CALLS)
        return Line(got[0], "hype", "SWEATING_INTENSE", "final") if got else None

    def fillers(self, r: RaceInfo) -> list[Line]:
        """Spoiler-free colour for quiet stretches: season facts about the runners first, then one-liners.
        Candidates only (claimed by the scheduler when used), so the whole video never repeats a filler."""
        out: list[Line] = []
        st = r.stats_before or {}
        facts: list[str] = []
        order = [k for k, _ in (r.standings_before or [])]
        if order and r.race > 1:
            lk = order[0]
            lp = int((st.get(lk) or {}).get("points", 0))
            facts += [t.format(X=name(lk), n=lp) for t in FACT_LEADER]
        for k in r.heroes:
            if k not in HERO_BY_KEY or k not in st:
                continue
            s = st[k]
            if int(s.get("behind_dummy", 0) or 0) >= 1:
                facts += [t.format(X=name(k), n=times(int(s["behind_dummy"]))) for t in FACT_DUMMY]
            if int(s.get("kos", 0) or 0) >= 3:
                facts += [t.format(X=name(k), n=int(s["kos"])) for t in FACT_KOS]
            if r.race >= 5 and int(s.get("wins", 0) or 0) == 0 and int(s.get("races", 0) or 0) >= 4:
                facts += [t.format(X=name(k)) for t in FACT_WINLESS]
        for txt in self._peek(f"fill.facts.{r.race}", facts, n=3):
            out.append(Line(txt, "normal", "HYPED_TALKING", "filler"))
        for txt in self._peek("fill.generic", FILLERS, n=3):
            out.append(Line(txt, "normal", "HYPED_TALKING", "filler"))
        return out

    def post_lines(self, r: RaceInfo, replay_style: str = "", fmt: str = "STANDARD") -> list[Line]:
        """Lines for the replay / results tail after the verdict (facts only, never repeated)."""
        out: list[Line] = []
        W = name(r.winner)
        if fmt != "QUICK":
            bank = REPLAY_INTROS.get(replay_style) or REPLAY_INTROS["tight"]
            got = self._peek(f"post.replay.{replay_style}", tuple(t.format(W=W) for t in bank))
            if got:
                out.append(Line(got[0], "normal", "LAUGHING_TEARS", "post"))
        if r.stage == "league" and r.leader_after in r.stats_after:
            pts = int(r.stats_after[r.leader_after]["points"])
            got = self._peek("post.table", tuple(t.format(X=name(r.leader_after), n=pts) for t in POST_TABLE))
            if got:
                out.append(Line(got[0], "normal", "HYPED_TALKING", "post"))
        if r.race < self.recap.end_race:
            got = self._peek("post.next", tuple(t.format(R=self._race_word(r.race + 1)) for t in POST_NEXT))
            if got:
                out.append(Line(got[0], "normal", "HYPED_TALKING", "post"))
        return out

    # ------------------------------------------------------------------ season storylines (desk segments)
    def storylines(self, max_n: int = 3) -> list[dict[str, Any]]:
        """2-3 season arcs told between races instead of narrating every KO. Each: after_race, title, hero, stat,
        expression, line. Built only from facts; placed after the race where the arc becomes true."""
        races = list(self.recap.part_races)
        if len(races) < 4:
            return []
        cands: list[tuple[float, dict[str, Any]]] = []
        # 1) title fight: leader changes inside this part
        flips = [ri for ri in races if ri.lead_changed and ri.stage == "league"]
        if len(flips) >= 2:
            ri = flips[1]
            a, b = name(flips[0].leader_after), name(ri.leader_after)
            cands.append((3.0 + len(flips), {
                "after_race": ri.race, "title": "THE TITLE FIGHT", "hero": ri.leader_after,
                "stat": f"{len(flips)} LEAD CHANGES", "expr": "angry",
                "line": self._pick("story.title", (
                    f"Storyline time. Top spot has changed hands {len(flips)} times already. {a} and {b} are trading punches.",
                    f"The title race is a mess. {len(flips)} lead changes. Nobody wants to stay on top, apparently.",
                ))}))
        # 2) the dummy curse: most losses to crash dummies in the part
        dummy: dict[str, list[int]] = {}
        for ri in races:
            for k in ri.behind_dummy:
                dummy.setdefault(k, []).append(ri.race)
        if dummy:
            k, rs = max(dummy.items(), key=lambda kv: (len(kv[1]), kv[0]))
            if len(rs) >= 2:
                cands.append((2.5 + len(rs), {
                    "after_race": rs[1], "title": "THE DUMMY CURSE", "hero": k, "stat": f"LOST TO DUMMIES x{len(rs)}",
                    "expr": "dizzy",
                    "line": self._pick("story.dummy", (
                        f"Running gag alert. {name(k)} has now lost to a crash test dummy {times(len(rs))}. "
                        "The dummies have started a fan club.",
                        f"{name(k)} versus the crash dummies. The dummies lead {len(rs)} nil. They don't even have legs.",
                    ))}))
        # 3) hot streak: back-to-back wins or 3+ wins in the part
        wins: dict[str, list[int]] = {}
        for ri in races:
            wins.setdefault(ri.winner, []).append(ri.race)
        streak = next(((races[i].winner, races[i].race) for i in range(1, len(races))
                       if races[i].winner == races[i - 1].winner), None)
        if streak:
            k, at = streak
            cands.append((4.0, {
                "after_race": at, "title": "ON FIRE", "hero": k, "stat": "BACK-TO-BACK WINS", "expr": "celebrating",
                "line": self._pick("story.streak", (
                    f"Back-to-back wins for {name(k)}. Everyone else, this is your cue to panic.",
                    f"{name(k)} has won two on the bounce. The castle has a problem.",
                ))}))
        else:
            k, rs = max(wins.items(), key=lambda kv: (len(kv[1]), kv[0]))
            if len(rs) >= 3:
                cands.append((3.5, {
                    "after_race": rs[2], "title": "THE FAVOURITE", "hero": k, "stat": f"{len(rs)} WINS",
                    "expr": "celebrating",
                    "line": f"That's win number {NUM.get(len(rs), str(len(rs))).lower()} for {name(k)}. "
                            "The rest of the league is playing for second."}))
        # 4) the slump: a contender (top 3 entering the part) with zero wins after 5+ races
        entering = self.recap.stats_entering(self.recap.start_race)
        from src.state import league
        top3 = [k for k, _ in league.sorted_standings(entering)[:3]] if self.recap.start_race > 1 else []
        for k in top3:
            if k not in wins and len(races) >= 6:
                cands.append((3.0, {
                    "after_race": races[5].race, "title": "THE SLUMP", "hero": k, "stat": "0 WINS THIS PART",
                    "expr": "scared",
                    "line": f"Meanwhile, {name(k)} came into this part as a contender. Six races later, zero wins. Yikes."}))
                break
        # 5) the menace: knockouts in the part
        kos: dict[str, int] = {}
        ko_at: dict[str, int] = {}
        for ri in races:
            for k2, n in ri.ko_counts.items():
                kos[k2] = kos.get(k2, 0) + int(n)
                if kos[k2] >= 3 and k2 not in ko_at:
                    ko_at[k2] = ri.race
        if ko_at:
            k = max(ko_at, key=lambda x: (kos[x], x))
            cands.append((2.0 + kos[k] * 0.4, {
                "after_race": ko_at[k], "title": "PUBLIC MENACE", "hero": k, "stat": f"{kos[k]} KOs",
                "expr": "angry",
                "line": self._pick("story.menace", (
                    f"A word about {name(k)}. {kos[k]} knockouts this part. Somebody call security.",
                    f"{name(k)} has binned {kos[k]} rivals already. That's not racing, that's a crime spree.",
                ))}))
        cands.sort(key=lambda c: -c[0])
        chosen: list[dict[str, Any]] = []
        last = races[-1].race
        for _, c in cands:
            if c["after_race"] >= last:
                continue
            if any(abs(c["after_race"] - o["after_race"]) < 2 for o in chosen):
                continue
            chosen.append(c)
            if len(chosen) >= max_n:
                break
        for c in chosen:
            self.mark(c["line"])
        return sorted(chosen, key=lambda c: c["after_race"])

    def chart_mid(self) -> Line | None:
        r = self.recap
        start = r.stats_entering(r.start_race)
        gains = {k: int(v["points"]) - int((start.get(k) or {}).get("points", 0)) for k, v in r.final_stats.items()}
        if not gains:
            return None
        k = max(gains, key=lambda x: (gains[x], x))
        return Line(f"Look at {name(k)} go. Plus {gains[k]} in this part alone.", "hype", "SHOCKED_JAWDROP", "chart")

    def chart_close(self) -> Line:
        r = self.recap
        from src.state import league
        order = league.sorted_standings(r.final_stats)
        (lk, lv), (bk, bv) = order[0], order[-1]
        return Line(f"{name(lk)} out in front on {lv['points']} points. {name(bk)} propping up the table on "
                    f"{bv['points']}.", "normal", "LAUGHING_TEARS", "chart")

    def standings_tail(self) -> Line:
        r = self.recap
        from src.state import league
        order = league.sorted_standings(r.final_stats)
        last = name(order[-1][0])
        txt = self._pick("st.tail", (f"And {last} is bottom. They're fine. They're not fine.",
                                     f"Spare a thought for {last}. Actually, don't.",
                                     f"{last} is last, and blaming the floor."))
        return Line(txt, "deadpan", "FACEPALM", "table")

    def end_extra(self) -> Line:
        return Line(self._pick("end.x", ("Pick a video on screen. I'll wait. Actually, no, I won't.",
                                         "Go on, click one. The balls need the views.")), "normal", "HYPED_TALKING", "outro")

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
            # ties on fewest points resolve exactly like the table/chart: the LOWEST-ranked of the tied heroes
            from src.state import league
            low_pts = p[1]
            tied = {k for k, v in st.items() if v["races"] > 0 and v["points"] == low_pts}
            table = [k for k, _ in league.sorted_standings(self.recap.final_stats)] if self.recap.final_stats else []
            ranked_tied = [k for k in table if k in tied]
            if ranked_tied:
                p = (ranked_tied[-1], low_pts)
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
              "material or colour literally. Plain ASCII, no emojis. EVERY line must use a different joke and "
              "sentence structure: never reuse a phrase, opener or punchline pattern across lines (no repeated "
              "'proving that', 'apparently', 'somehow'). Return ONLY a JSON array of strings, same "
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
        cands.sort(key=lambda s: ("lite" not in s, "preview" in s or "exp" in s, s))   # fast lite models first
    for model in (cands or ["gemini-2.5-flash", "gemini-2.5-flash-lite"])[:4]:
        cfg: dict = {"responseMimeType": "application/json", "temperature": 0.9}
        if model.startswith(("gemini-2.5", "gemini-3")):
            cfg["thinkingConfig"] = {"thinkingBudget": 0}
        payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": cfg}
        code, body = script._gemini_http(f"{base}/models/{model}:generateContent", key, payload, 25.0)
        if code != 200 and "thinkingConfig" in str(body):
            cfg.pop("thinkingConfig", None)
            code, body = script._gemini_http(f"{base}/models/{model}:generateContent", key, payload, 25.0)
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
    seen_grams: set[tuple[str, ...]] = set()

    def grams(txt: str) -> set[tuple[str, ...]]:
        w = [x for x in re.sub(r"[^a-z' ]", " ", skeleton(txt)).split() if x != "#"]
        return {tuple(w[i:i + 3]) for i in range(max(0, len(w) - 2))}

    for (r, ln), new in zip(items, lines):
        allowed = {name(r.winner)} | ({name(r.hero_ranking[1])} if len(r.hero_ranking) > 1 else set())
        if isinstance(new, str):
            new = " ".join(new.replace("\u2014", "-").replace("\u2019", "'").split())
            g = grams(new)
            if _valid_winner_line(new, name(r.winner), allowed) and not (g & seen_grams):
                ln.text = new
                seen_grams |= g
                n += 1
            else:
                seen_grams |= grams(ln.text)
    log(f"  [RECAP LLM] punched up {n}/{len(items)} winner lines")
    return n
