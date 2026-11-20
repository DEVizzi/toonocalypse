"""Renders the 5 v4.2 Production-Lock verification MP4s + runs an automated audit.

Usage (CI only — needs pygame/ffmpeg/edge-tts):  python tests/render_v42_verify.py [job_substring ...]
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

VERIFY_JOBS: list[tuple[str, list[str]]] = [
    (
        "v42_rotating_disc_classic.mp4",
        ["--seed", "101", "--season", "1", "--race", "12", "--arena", "rotating_disc", "--goal", "last_one_standing"],
    ),
    (
        "v42_crumbling_bridge_monsoon.mp4",
        ["--seed", "505", "--season", "5", "--race", "25", "--arena", "crumbling_bridge", "--goal", "reach_finish"],
    ),
    (
        "v42_crusher_gauntlet_desert_final.mp4",
        ["--seed", "712", "--season", "7", "--race", "30", "--arena", "crusher_gauntlet", "--goal", "reach_finish"],
    ),
    (
        "v42_collapse_tower_haunted.mp4",
        ["--seed", "606", "--season", "6", "--race", "27", "--arena", "collapse_tower", "--goal", "reach_finish"],
    ),
    (
        "v42_pachinko_drop_neon.mp4",
        ["--seed", "306", "--season", "4", "--race", "9", "--arena", "pachinko_drop", "--goal", "reach_finish"],
    ),
]

BANNED = ("i see", "i am ", "zero room for error", "pure chaos in the pack", "double wipeout!", "who blinks first")


def main(argv: list[str]) -> int:
    out_dir = Path("output")
    out_dir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["PYTHONPATH"] = "."
    jobs = [j for j in VERIFY_JOBS if not argv or any(s in j[0] for s in argv)]

    audit_rows: list[dict] = []
    failures = 0
    for fname, extra_args in jobs:
        mp4 = out_dir / fname
        log_path = mp4.with_suffix(".log")
        print(f"\n==================== RENDERING {fname} ====================", flush=True)
        cmd = [sys.executable, "-m", "src.main", "--dry-run", "--stills", "6", "--out", str(mp4)] + extra_args
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
        log = (proc.stdout or "") + (proc.stderr or "")
        log_path.write_text(log)
        print(log[-6000:], flush=True)
        if proc.returncode != 0:
            failures += 1
            audit_rows.append({"file": fname, "error": f"exit {proc.returncode}"})
            continue

        for wav in list(out_dir.glob("*.wav")) + list(out_dir.glob(".*.wav")):
            wav.unlink(missing_ok=True)

        meta = json.loads(mp4.with_suffix(".json").read_text())
        snd = meta.get("sound") or {}
        lines = snd.get("lines") or []
        outro_spoken = lines[-1] if lines else ""
        prompt_cta = meta.get("prompt_cta") or ""
        ids = snd.get("line_ids") or []
        lower = " ".join(lines).lower()
        rej = [c for c in (meta.get("candidates") or []) if isinstance(c, dict) and c.get("seed") == meta.get("best_seed")]
        audit_rows.append({
            "file": fname,
            "ribbon": meta.get("ribbon"),
            "stage": meta.get("stage"),
            "theme": meta["recipe"]["theme"],
            "twist": meta["recipe"].get("twist"),
            "winner": meta.get("winner"),
            "leader": meta.get("leader"),
            "lead_changed": meta.get("lead_changed"),
            "narrated_new_leader": "new leader" in lower or "top of the table" in lower,
            "duration_s": round(float(meta.get("duration", 0)), 2),
            "resolved_at": meta.get("resolved_at"),
            "voice": snd.get("voice"),
            "bgm_track": snd.get("bgm_track"),
            "card_hold_s": snd.get("card_hold_s"),
            "outro_dur_s": snd.get("outro_dur_s"),
            "card_ok": (snd.get("card_hold_s") or 0) >= (snd.get("outro_dur_s") or 0) + 0.6,
            "max_lag_s": snd.get("max_reaction_lag_s"),
            "fillers": snd.get("fillers_added"),
            "gemini": snd.get("gemini_lines"),
            "llm_live": "[LLM LIVE]" in log,
            "llm_warning": "[LLM WARNING]" in log,
            "line_ids_unique": len(ids) == len(set(ids)),
            "banned_hits": [b for b in BANNED if b in lower],
            "cta_exact_match": (outro_spoken == prompt_cta),
            "outro_words": len(outro_spoken.split()),
            "outro_text": outro_spoken,
            "best_candidate": rej[0] if rej else None,
            "lines": lines,
        })

    (out_dir / "v42_verify_audit.json").write_text(json.dumps(audit_rows, indent=2) + "\n")
    print("\n==================== v4.2 VERIFY AUDIT SUMMARY ====================")
    for row in audit_rows:
        print(json.dumps({k: v for k, v in row.items() if k != "lines"}), flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
