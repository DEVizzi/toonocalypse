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
        return max(w, h) / (2 if self.shape in ("oval", "square") else 1)


HEROES: tuple[Hero, ...] = (
    Hero("bonk", "Bonk", "🟠", "The Anchor", "circle", (34, 34), "#FF7A00", 8.0, 195, 0.92, 0.15,
         "anchor", "smug", "tuba", Behaviour(0.75, 0.3, 0.2, 0.5), stun_mult=0.45),
    Hero("pip", "Pip", "🟡", "The Speedster", "circle", (16, 16), "#FFD600", 1.1, 370, 0.55, 0.35,
         "featherweight", "nervous", "squeak", Behaviour(0.2, 0.25, 0.6, 0.35)),
    Hero("boing", "Boing", "🩷", "The Bouncer", "oval", (24, 32), "#FF4DA6", 2.8, 255, 0.40, 0.95,
         "auto_hop", "grinning", "spring", Behaviour(0.35, 0.15, 0.95, 0.3)),
    Hero("sly", "Sly", "🟢", "The Cornersniper", "circle", (24, 24), "#2ECC71", 3.1, 295, 0.62, 0.28,
         "lookahead", "smirking", "pizzicato", Behaviour(0.6, 0.7, 0.55, 0.9)),
    Hero("grumble", "Grumble", "🔵", "The Underdog", "circle", (25, 25), "#2980B9", 3.8, 245, 0.98, 0.10,
         "spite", "scowling", "kazoo", Behaviour(0.5, 0.5, 0.35, 0.8)),
    Hero("dash", "Dash", "🩵", "The Slider", "oval", (32, 20), "#00E5FF", 2.4, 420, 0.03, 0.22,
         "no_brakes", "focused", "screech", Behaviour(0.3, 0.05, 0.4, 0.15)),
    Hero("magneto", "Magneto", "🟣", "The Traction King", "hexagon", (25, 25), "#9B59B6", 4.2, 250, 1.00, 0.12,
         "traction", "visor", "clunk", Behaviour(0.45, 0.5, 0.3, 0.7)),
    Hero("floater", "Floater", "⚪", "The Glider", "cloud", (26, 26), "#F8F9FA", 1.6, 240, 0.45, 0.42,
         "glide", "chill", "whistle", Behaviour(0.15, 0.4, 0.5, 0.45), gravity_mult=0.38),
    Hero("juggernaut", "Juggernaut", "🩶", "The Demolition Ball", "square", (54, 54), "#5D6D7E", 16.0, 165, 0.85,
         0.10, "bowling", "furrowed", "horn", Behaviour(0.9, 0.2, 0.1, 0.4)),
    Hero("glitch", "Glitch", "⬛", "The Chaos Agent", "octagon", (24, 24), "#111111", 3.5, 280, 0.30, 0.72,
         "glitch", "dizzy", "modem", Behaviour(0.5, 0.2, 0.5, 0.3), mass_range=(1.5, 6.5), speed_range=(160, 400)),
)
HERO_BY_KEY = {h.key: h for h in HEROES}

# Extras are "bots": light cool-grey round robots with an antenna (owner decision 2026-11-20; overrides the original
# sand/khaki spec). They stay distinct from Juggernaut (dark slate square) and Floater (white cloud) by shape and antenna.
EXTRA_COLOURS = ("#C5CBD3", "#B9C0CA", "#CFD4DA", "#B1B9C4", "#C0C6CE")


@dataclass
class Extra:
    number: int                 # 1-based contestant number; cult extras keep theirs forever
    colour: str
    radius: float = 24
    mass: float = 2.4
    max_speed: float = 200
    friction: float = 0.6
    elasticity: float = 0.3
    behaviour: Behaviour = field(default_factory=lambda: Behaviour(0.3, 0.4, 0.4, 0.5))
    cult: bool = False

    @property
    def key(self) -> str:
        return f"extra{self.number}"


def make_extras(n: int, rng: random.Random, cult_numbers: set[int] | None = None) -> list[Extra]:
    cult_numbers = cult_numbers or set()
    out = []
    for i in range(1, n + 1):
        # extras are deliberately less competent than heroes (lower speed, worse jumping and edge sense)
        b = Behaviour(rng.uniform(0.05, 0.35), rng.uniform(0.0, 0.35), rng.uniform(0.1, 0.4), rng.uniform(0.0, 0.25))
        out.append(Extra(i, rng.choice(EXTRA_COLOURS), mass=rng.uniform(2.0, 2.8), max_speed=rng.uniform(110, 165),
                         behaviour=b, cult=i in cult_numbers))
    return out
