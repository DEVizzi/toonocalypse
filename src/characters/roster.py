"""The cast (§9.2): 10 recurring heroes with physics stats, comedy traits and micro-AI personalities, plus extras."""
from __future__ import annotations

import random
from dataclasses import dataclass, field

EXPRESSIONS = ("neutral", "happy", "scared", "dizzy", "angry", "celebrating", "eliminated")


@dataclass(frozen=True)
class Behaviour:
    aggression: float      # how often it tries to shove rivals
    caution: float         # slows down near hazards
    jumpiness: float       # probability of hopping at obstacles
    edge_awareness: float  # steering away from edges / kill zones


@dataclass(frozen=True)
class Hero:
    key: str
    name: str
    emoji: str
    archetype: str
    shape: str                 # circle | oval | hexagon | cloud | square | octagon
    size: tuple[float, float]  # circle/hex/oct/cloud: (r, r); oval/square: (w, h)
    colour: str
    mass: float
    max_speed: float
    friction: float
    elasticity: float
    trait: str
    face: str                  # default expression style
    sound: str
    behaviour: Behaviour
    stun_mult: float = 1.0
    gravity_mult: float = 1.0
    mass_range: tuple[float, float] | None = None
    speed_range: tuple[float, float] | None = None

    @property
    def initial(self) -> str:
        return self.name[0]

    @property
    def radius(self) -> float:
        """Bounding radius used for layout, pills and camera."""
        w, h = self.size
        if self.shape == "square":
            return w * 1.2
        return max(w, h)


# v3.0 elemental ball roster (owner spec 2026-11-20). size: circle (r, r); oval (w, h) half-axes; hexagon (r, r);
# square (half, half) with a heavy bevel so it tumbles. Trait keys are kept stable across versions.
HEROES: tuple[Hero, ...] = (
    Hero("bonk", "Bonk", "🟠", "Heavy Bowling Ball", "circle", (33, 33), "#FF7A00", 4.8, 230, 0.65, 0.32,
         "anchor", "smug", "tuba", Behaviour(0.75, 0.3, 0.25, 0.5), stun_mult=0.5),
    Hero("pip", "Pip", "🟡", "Ping-Pong Ball", "circle", (17, 17), "#FFD600", 0.50, 330, 0.28, 0.85,
         "featherweight", "nervous", "squeak", Behaviour(0.2, 0.25, 0.6, 0.4)),
    Hero("boing", "Boing", "🩷", "Rubber Superball", "circle", (23, 23), "#FF4DA6", 1.10, 280, 0.78, 0.98,
         "auto_hop", "grinning", "spring", Behaviour(0.35, 0.15, 0.7, 0.3)),
    Hero("sly", "Sly", "🟢", "Cue / Billiard Ball", "circle", (23, 23), "#2ECC71", 1.85, 290, 0.22, 0.80,
         "lookahead", "smirking", "pizzicato", Behaviour(0.6, 0.7, 0.55, 0.9)),
    Hero("grumble", "Grumble", "🔵", "Sticky Velcro Ball", "circle", (25, 25), "#2980B9", 2.40, 245, 1.80, 0.10,
         "spite", "scowling", "kazoo", Behaviour(0.5, 0.5, 0.35, 0.85)),
    Hero("dash", "Dash", "🩵", "Frictionless Ice Puck", "oval", (30, 19), "#00E5FF", 1.30, 360, 0.02, 0.65,
         "no_brakes", "focused", "screech", Behaviour(0.3, 0.05, 0.4, 0.2)),
    Hero("magneto", "Magneto", "🟣", "Magnetic Hex Bolt", "hexagon", (25, 25), "#9B59B6", 2.70, 250, 1.25, 0.42,
         "traction", "visor", "clunk", Behaviour(0.45, 0.5, 0.3, 0.75)),
    Hero("floater", "Floater", "⚪", "Helium Beach Ball", "circle", (29, 29), "#F8F9FA", 0.62, 240, 0.35, 0.92,
         "glide", "chill", "whistle", Behaviour(0.15, 0.4, 0.55, 0.5), gravity_mult=0.24),
    Hero("juggernaut", "Juggernaut", "🩶", "Cast-Iron Wrecking Cube", "square", (29, 29), "#5D6D7E", 8.50, 200, 0.95,
         0.20, "bowling", "furrowed", "horn", Behaviour(0.9, 0.2, 0.15, 0.45), stun_mult=0.35),
    Hero("glitch", "Glitch", "⬛", "Unstable Quantum Ball", "circle", (23, 23), "#111111", 2.0, 290, 0.45, 0.6,
         "glitch", "dizzy", "modem", Behaviour(0.5, 0.2, 0.5, 0.35), mass_range=(0.55, 4.4)),
)
HERO_BY_KEY = {h.key: h for h in HEROES}

# v5.1 Rookie pool: from Season 2, TWO new balls (new personality + power, see src/physics/powers.py) join every
# season; from Season 3 the bottom two of the previous season are relegated so the league stays at 12.
# `HEROES` (the Season 1 founding ten) is intentionally unchanged: live Season 1 state and fingerprints depend on it.
ROOKIES: tuple[Hero, ...] = (
    Hero("zap", "Zap", "⚡", "Electric Spark Ball", "circle", (22, 22), "#FACC15", 1.40, 300, 0.50, 0.70,
         "rookie", "grinning", "spring", Behaviour(0.6, 0.3, 0.45, 0.55)),
    Hero("goo", "Goo", "🟩", "Slime Blob", "circle", (26, 26), "#58D658", 1.60, 250, 1.40, 0.15,
         "rookie", "chill", "squeak", Behaviour(0.4, 0.4, 0.3, 0.6)),
    Hero("frosty", "Frosty", "❄", "Snowball", "circle", (25, 25), "#BFE9FF", 1.20, 270, 0.12, 0.50,
         "rookie", "smug", "whistle", Behaviour(0.35, 0.5, 0.4, 0.7)),
    Hero("blaze", "Blaze", "🔥", "Fireball", "circle", (23, 23), "#FF5722", 1.50, 320, 0.40, 0.60,
         "rookie", "focused", "screech", Behaviour(0.55, 0.15, 0.4, 0.35)),
    Hero("shadow", "Shadow", "🥷", "Ninja Ball", "circle", (23, 23), "#2D2A3E", 1.60, 300, 0.60, 0.55,
         "rookie", "smirking", "pizzicato", Behaviour(0.5, 0.6, 0.5, 0.85)),
    Hero("comet", "Comet", "☄", "Space Rock", "hexagon", (27, 27), "#8D6E63", 3.60, 240, 0.70, 0.30,
         "rookie", "furrowed", "horn", Behaviour(0.7, 0.25, 0.3, 0.5)),
)
ALL_HEROES: tuple[Hero, ...] = HEROES + ROOKIES
HERO_BY_KEY.update({h.key: h for h in ROOKIES})


def rookies_for_season(season: int) -> list[str]:
    """The two rookies debuting in `season` (none in Season 1). Cycles the pool deterministically."""
    s = int(season or 1)
    if s < 2:
        return []
    i = ((s - 2) * 2) % len(ROOKIES)
    return [ROOKIES[i].key, ROOKIES[(i + 1) % len(ROOKIES)].key]

# Crash Dummies (v3.0): 3-5 light-grey crash-test balls with a black/yellow quadrant decal. Comedic bumper pins: weaker
# propulsion (0.72x heroes), no name pills, never allowed to win (Best-of-N penalty). Class name kept as Extra.
EXTRA_COLOURS = ("#D5D9DE",)


@dataclass
class Extra:
    number: int
    colour: str = "#D5D9DE"
    radius: float = 20
    mass: float = 0.95
    max_speed: float = 230
    friction: float = 0.45
    elasticity: float = 0.60
    behaviour: Behaviour = field(default_factory=lambda: Behaviour(0.2, 0.2, 0.25, 0.25))
    cult: bool = False
    golden: bool = False

    @property
    def key(self) -> str:
        return f"extra{self.number}"


def make_extras(n: int, rng: random.Random, cult_numbers: set[int] | None = None, golden: bool = False) -> list[Extra]:
    cult_numbers = cult_numbers or set()
    col = "#FFD43B" if golden else "#D5D9DE"
    return [Extra(i, colour=col, behaviour=Behaviour(rng.uniform(0.05, 0.3), rng.uniform(0.0, 0.3), rng.uniform(0.1, 0.35),
                                                     rng.uniform(0.0, 0.3)), max_speed=rng.uniform(200, 250),
                  cult=i in cult_numbers, golden=golden)
            for i in range(1, n + 1)]
