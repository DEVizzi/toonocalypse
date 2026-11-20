"""Renders the 7 v4.0 Showcase MP4s (Part E) + runs an automated audio/caption/Winner-Card audit."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SHOWCASE_JOBS: list[tuple[str, list[str]]] = [
    (
        "v4_01_rotating_disc_classic.mp4",
        ["--seed", "101", "--season", "1", "--race", "12", "--arena", "rotating_disc", "--goal", "last_one_standing"],
    ),
    (
        "v4_02_ramp_descent_frost.mp4",
        ["--seed", "202", "--season", "2", "--race", "18", "--arena", "ramp_descent", "--goal", "reach_finish"],
    ),
    (
        "v4_03_pachinko_drop_neon.mp4",
        ["--seed", "306", "--season", "4", "--race", "9", "--arena", "pachinko_drop", "--goal", "reach_finish"],
    ),
    (
        "v4_04_sumo_pool_volcanic.mp4",
        ["--seed", "404", "--season", "3", "--race", "21", "--arena", "sumo_pool_pit", "--goal", "last_one_standing"],
    ),
    (
        "v4_05_crumbling_bridge_monsoon.mp4",
        ["--seed", "505", "--season", "5", "--race", "25", "--arena", "crumbling_bridge", "--goal", "reach_finish"],
    ),
    (
        "v4_06_collapse_tower_haunted.mp4",
        ["--seed", "606", "--season", "6", "--race", "27", "--arena", "collapse_tower", "--goal", "reach_finish"],
    ),
    (
        "v4_07_crusher_gauntlet_desert.mp4",
        ["--seed", "712", "--season", "7", "--race", "30", "--arena", "crusher_gauntlet", "--goal", "reach_finish"],
    ),
]


def main() -> int:
    out_dir = Path("output")
    out_dir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["PYTHONPATH"] = "."

    audit_rows: list[dict] = []
    for fname, extra_args in SHOWCASE_JOBS:
        mp4 = out_dir / fname
        print(f"\n==================== RENDERING {fname} ====================", flush=True)
        cmd = [sys.executable, "-m", "src.main", "--dry-run", "--stills", "4", "--out", str(mp4)] + extra_args
        subprocess.run(cmd, check=True, env=env)

        # Clean up large intermediate .wav files so release upload stays crisp and fast
        for wav in out_dir.glob("*.wav"):
            wav.unlink(missing_ok=True)
        for hidden_wav in out_dir.glob(".*.wav"):
            hidden_wav.unlink(missing_ok=True)

        meta = json.loads(mp4.with_suffix(".json").read_text())
        snd = meta.get("sound") or {}
        lines = snd.get("lines") or []
        outro_spoken = lines[-1] if lines else ""
        prompt_cta = meta.get("prompt_cta") or ""
        audit_rows.append({
            "file": fname,
            "ribbon": meta.get("ribbon"),
            "theme": meta["recipe"]["theme"],
            "winner": meta.get("winner"),
            "duration_s": round(float(meta.get("duration", 0)), 2),
            "card_hold_s": snd.get("card_hold_s"),
            "max_lag_s": snd.get("max_reaction_lag_s"),
            "fillers": snd.get("fillers_added"),
            "gemini": snd.get("gemini_lines"),
            "cta_exact_match": (outro_spoken == prompt_cta),
            "outro_words": len(outro_spoken.split()),
            "outro_text": outro_spoken,
        })

    (out_dir / "v4_showcase_audit.json").write_text(json.dumps(audit_rows, indent=2) + "\n")
    print("\n==================== v4.0 SHOWCASE AUDIT SUMMARY ====================")
    for row in audit_rows:
        print(json.dumps(row), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
