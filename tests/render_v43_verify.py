"""Renders the 3 v4.3 FINAL sign-off MP4s + automated audit (CI only — needs pygame/ffmpeg/edge-tts).

Usage:  python tests/render_v43_verify.py [job_substring ...]
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

VERIFY_JOBS: list[tuple[str, list[str]]] = [
    (
        "v43_crusher_gauntlet_grand_final.mp4",
        ["--seed", "712", "--season", "7", "--race", "30", "--arena", "crusher_gauntlet", "--goal", "reach_finish"],
    ),
    (
        "v43_collapse_tower_playin.mp4",
        ["--seed", "606", "--season", "6", "--race", "27", "--arena", "collapse_tower", "--goal", "reach_finish"],
    ),
    (
        "v43_crumbling_bridge_monsoon.mp4",
        ["--seed", "505", "--season", "5", "--race", "25", "--arena", "crumbling_bridge", "--goal", "reach_finish"],
    ),
]

BANNED = ("i see", "i am ", "zero room for error", "pure chaos in the pack", "double wipeout!", "who blinks first")
CLICHE_RX = re.compile(r"properly spicy|total carnage|prepare (for )?carnage|hunting (for )?blood", re.IGNORECASE)


def main(argv: list[str]) -> int:
    out_dir = Path("output")
    out_dir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["PYTHONPATH"] = "."
    jobs = [j for j in VERIFY_JOBS if not argv or any(s in j[0] for s in argv)]

    rows: list[dict] = []
    failures = 0
    for fname, extra_args in jobs:
        mp4 = out_dir / fname
        print(f"\n==================== RENDERING {fname} ====================", flush=True)
        cmd = [sys.executable, "-m", "src.main", "--dry-run", "--stills", "6", "--out", str(mp4)] + extra_args
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
        log = (proc.stdout or "") + (proc.stderr or "")
        mp4.with_suffix(".log").write_text(log)
        print(log[-6000:], flush=True)
        if proc.returncode != 0:
            failures += 1
            rows.append({"file": fname, "error": f"exit {proc.returncode}"})
            continue
        for wav in list(out_dir.glob("*.wav")) + list(out_dir.glob(".*.wav")):
            wav.unlink(missing_ok=True)

        meta = json.loads(mp4.with_suffix(".json").read_text())
        snd = meta.get("sound") or {}
        lines = snd.get("lines") or []
        low = " ".join(lines).lower()
        stage = meta.get("stage")
        outro = lines[-1] if lines else ""
        pts = [int(r[1]) for r in (meta.get("top4") or [])]
        finalists = [k for k in meta.get("cast", [])]
        intro = lines[0] if lines else ""
        rows.append({
            "file": fname,
            "ribbon": meta.get("ribbon"),
            "stage": stage,
            "theme": meta["recipe"]["theme"],
            "twist": meta["recipe"].get("twist"),
            "winner": meta.get("winner"),
            "lead_changed": meta.get("lead_changed"),
            "top4": meta.get("top4"),
            "standings_sorted": all(pts[i] >= pts[i + 1] for i in range(len(pts) - 1)),
            "duration_s": round(float(meta.get("duration", 0)), 2),
            "resolved_at": meta.get("resolved_at"),
            "voice": snd.get("voice"),
            "bgm_track": snd.get("bgm_track"),
            "card_hold_s": snd.get("card_hold_s"),
            "outro_dur_s": snd.get("outro_dur_s"),
            "llm_live": "[LLM LIVE]" in log,
            "guard_log": [ln.strip() for ln in log.splitlines() if "[GUARD]" in ln],
            "line_ids_unique": len(snd.get("line_ids") or []) == len(set(snd.get("line_ids") or [])),
            "banned_hits": [b for b in BANNED if b in low],
            "cliche_hits": CLICHE_RX.findall(low),
            "says_next_season": "next season" in low and stage != "grand_final",
            "says_league_n": bool(re.search(r"\bleague (one|two|three|four|five|six|seven|eight|nine|ten|eleven|"
                                            r"twelve|\w+teen|twenty\w*|\d+)\b", low)),
            "gf_intro_names_all_3": (all(n in intro.lower() for n in finalists) if stage == "grand_final" else None),
            "gf_outro_no_cta": (not re.search(r"comment|pick|below|vote", outro.lower()) if stage == "grand_final"
                                else None),
            "outro_text": outro,
            "intro_text": intro,
            "lines": lines,
        })

    (out_dir / "v43_verify_audit.json").write_text(json.dumps(rows, indent=2) + "\n")
    print("\n==================== v4.3 SIGN-OFF AUDIT SUMMARY ====================")
    for row in rows:
        print(json.dumps({k: v for k, v in row.items() if k != "lines"}), flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
