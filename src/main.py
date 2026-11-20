"""ToonToonCastle v4.4 Autonomous Season League CLI (§22.4).

Examples:
    # Preview / Showcase dry-run (synthesizes realistic season standings, never mutates state/):
    python -m src.main --dry-run --seed 101 --season 1 --race 12 --arena rotating_disc --goal last_one_standing

    # Autonomous daily Season League production run (YT Shorts + IG Reels + atomic state/*.json commit):
    python -m src.main --publish --commit-state
"""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import time
from pathlib import Path

from src.characters.roster import HERO_BY_KEY, HEROES, make_extras
from src.config import settings
from src.games import recipe_generator
from src.games.base import Recipe
from src.games.themes import for_season
from src.physics import scorer
from src.physics.engine import Sim
from src.physics.trace import Event, Trace
from src.state import league

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state"


def _load(name: str, default):
    return league.load_json(STATE / name, default)


def pick_cast(kind: str, rng: random.Random) -> tuple[list, list]:
    """Legacy fallback cast helper."""
    cast = settings()["cast"]
    if kind == "rumble":
        return list(HEROES), make_extras(cast["mega_extras"], rng)
    heroes = rng.sample(list(HEROES), cast["spotlight_heroes"])
    return heroes, make_extras(rng.randint(*cast["extras_range"]), rng)


def simulate_best(recipe: Recipe, heroes: list, extras: list, seed: int, history: dict | None = None,
                  log=print) -> tuple[Trace, scorer.Score, list[dict]]:
    """Best-of-N (§12): 8 seeds, 8 more if none reaches min_score (max 16). Outcomes are 100% real physics."""
    sc = settings()["scorer"]
    results: list[tuple[float, int, Trace, scorer.Score]] = []
    report = []
    t_all = time.time()
    for i in range(sc["max_seeds"]):
        if i == sc["seeds_per_batch"] and any(r[0] >= scorer.min_score() and not scorer.rejected(r[3]) for r in results):
            break
        s = seed * 1000 + i
        t0 = time.time()
        tr = Sim(recipe, heroes, extras, s).run()
        res = scorer.score(tr, history)
        dt = time.time() - t0
        results.append((res.total, s, tr, res))
        report.append({
            "seed": s,
            "score": res.total,
            "rejected": scorer.rejected(res),
            "winner": tr.meta["winner"],
            "resolved_at": tr.meta["resolved_at"],
            "sim_s": round(dt, 2),
        })
        log(f"  seed {s}: score={res.total:+.0f} rej={scorer.rejected(res)} winner={tr.meta['winner']} "
            f"t={tr.meta['resolved_at']:.1f}s sim={dt:.1f}s")
    log(f"  {len(results)} sims in {time.time() - t_all:.1f}s")
    # Rank non-rejected runs first, then prefer Hero winners if all runs had minor duration edge cases
    results.sort(
        key=lambda r: (
            not scorer.rejected(r[3]),
            not str(r[2].meta.get("winner") or "").startswith("extra"),
            16.0 <= float(r[2].meta.get("resolved_at") or 0) <= 28.0,
            r[0],
        ),
        reverse=True,
    )
    best = results[0]
    return best[2], best[3], report


def flash_event(tr: Trace) -> Event | None:
    """The episode's biggest disaster for the flash-forward cold open (needs >= 2 s of lead-in)."""
    def rank(e: Event) -> float:
        if e.kind == "elimination" and e.data.get("hero"):
            return 3 + (1 if e.data.get("by_hero") else 0)
        if e.kind == "trait":
            return 2
        if e.kind == "impact" and e.data.get("hero_pair"):
            return 1 + min(1.0, e.data.get("impulse", 0) / 4000)
        return 0
    end = tr.meta.get("resolved_at") or 0
    cands = [e for e in tr.events if 2.0 <= e.t <= end - 2.0 and e.actors and rank(e) > 0]
    return max(cands, key=rank) if cands else None


def comment_prompt(heroes: list, winner: str | None, rng: random.Random) -> str:
    pool = [h for h in heroes if h.key != winner] or list(HEROES)
    a, b = rng.sample(pool, 2) if len(pool) >= 2 else (pool[0], pool[0])
    return f"{a.name} or {b.name} tomorrow? Drop your pick!"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ToonToonCastle v4.4 IPL Season League pipeline")
    ap.add_argument("--dry-run", action="store_true", help="render only: no uploads, no state/ mutation")
    ap.add_argument("--commit-state", action="store_true", help="git pull --rebase + commit + push state/ after run")
    ap.add_argument("--commit-state-dry-run", action="store_true",
                    help="pull --rebase + local commit + `git push --dry-run` (verifies the state step, remote untouched)")
    ap.add_argument("--publish", action="store_true", help="dual upload to YouTube Shorts + Instagram Reels after gates pass")
    ap.add_argument("--skip-yt", action="store_true", help="skip YouTube Shorts upload during --publish")
    ap.add_argument("--skip-ig", action="store_true", help="skip Instagram Reels upload during --publish")
    ap.add_argument("--privacy", choices=["public", "unlisted", "private"], default="public")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--season", type=int, default=None, help="override season number (synthesizes mock table in --dry-run)")
    ap.add_argument("--race", type=int, default=None, help="override race number 1..30 (synthesizes mock table in --dry-run)")
    ap.add_argument("--arena", default=None)
    ap.add_argument("--goal", default=None)
    ap.add_argument("--mode", choices=["SIDE_VIEW", "TOP_DOWN"], default=None)
    ap.add_argument("--kind", choices=["spotlight", "rumble"], default="spotlight")
    ap.add_argument("--hazards", default=None, help="comma-separated hazard override (test renders)")
    ap.add_argument("--twist", default=None, help="twist override, or 'none'")
    ap.add_argument("--theme", default=None)
    ap.add_argument("--flash-forward", choices=["auto", "on", "off"], default="auto")
    ap.add_argument("--episode", type=int, default=None, help="legacy alias for --race")
    ap.add_argument("--out", default="output/episode.mp4")
    ap.add_argument("--no-render", action="store_true", help="simulate and score only")
    ap.add_argument("--stills", type=int, default=0, help="also save N half-size PNG stills for review")
    ap.add_argument("--brand-stills", action="store_true",
                    help="export verify_gameplay_brand.png (t=5.0s) and verify_winner_brand.png (Winner Card)")
    ap.add_argument("--stage-only", action="store_true",
                    help="Step A transactional mode: simulate, render, validate gates, write pending_state to .json without touching state/")
    ap.add_argument("--no-audio", action="store_true", help="silent render (skip narration, SFX and music)")
    a = ap.parse_args(argv)

    seed = a.seed if a.seed is not None else int(time.time()) % 100000
    rng = random.Random(seed)
    history = _load("episode_history.json", {"entries": []})
    entries = list(history.get("entries", []) if isinstance(history, dict) else history)
    hof = _load("hall_of_fame.json", {"seasons": []})

    race_override = a.race or a.episode
    if a.dry_run and (a.season is not None or race_override is not None):
        s_num = max(1, int(a.season or 1))
        r_num = max(1, min(league.SEASON_LEN, int(race_override or 1)))
        season_state = league.mock_season_state(s_num, r_num, seed=seed)
    else:
        season_state = league.load_season_state(STATE)
        if a.season is not None:
            season_state["season_number"] = max(1, int(a.season))
            season_state["theme"] = for_season(season_state["season_number"]).key
        if race_override is not None:
            season_state["race_number"] = max(1, min(league.SEASON_LEN, int(race_override)))

    season_num = int(season_state["season_number"])
    race_num = int(season_state["race_number"])
    day = int(season_state.get("total_day") or ((entries[-1]["day"] + 1) if entries else 1))

    heroes, extras, is_grand_final = league.select_cast_for_race(season_state, rng)
    pre_table = [k for k, _ in league.sorted_standings(season_state["stats"])]
    pre_rank = {k: i + 1 for i, k in enumerate(pre_table)}
    cast_sorted = sorted([h.key for h in heroes], key=lambda k: pre_rank.get(k, 99))
    prev_winner = next((e.get("winner") for e in reversed(entries) if isinstance(e, dict) and e.get("winner")), None)
    wild_pool = [k for k in cast_sorted[2:]]
    wildcard = prev_winner if prev_winner in wild_pool else (rng.choice(wild_pool) if wild_pool else None)
    spotlights = []
    if cast_sorted:
        spotlights.append({"key": cast_sorted[0], "kind": "leader",
                           "label": f"#{pre_rank.get(cast_sorted[0], 1)} {HERO_BY_KEY[cast_sorted[0]].name.upper()}"})
    if len(cast_sorted) > 1:
        spotlights.append({"key": cast_sorted[1], "kind": "rival",
                           "label": f"#{pre_rank.get(cast_sorted[1], 2)} {HERO_BY_KEY[cast_sorted[1]].name.upper()}"})
    if wildcard:
        spotlights.append({"key": wildcard, "kind": "wildcard", "label": f"WILDCARD: {HERO_BY_KEY[wildcard].name.upper()}"})
    recent_ids: set[str] = set()
    for e in entries:
        if isinstance(e, dict) and int(e.get("day", -999)) > day - 7:
            recent_ids.update(e.get("line_ids") or [])
    recent_cliches: set[str] = set()
    for e in [x for x in entries if isinstance(x, dict)][-7:]:      # v4.3: each cliché max once every 7 episodes
        recent_cliches.update(e.get("cliches") or [])
    recipe, relaxed = recipe_generator.generate(
        entries,
        day,
        seed,
        mode=a.mode,
        arena=a.arena,
        goal=a.goal,
        season_theme=for_season(season_num).key,
    )
    if a.hazards:
        recipe.hazards = sorted(a.hazards.split(","))
    if a.twist:
        recipe.twist = None if a.twist == "none" else a.twist
    if a.theme:
        recipe.theme = a.theme
    if a.flash_forward != "auto":
        recipe.flash_forward = a.flash_forward == "on"
    recipe.finale = is_grand_final
    recipe.episode_kind = "rumble_final" if is_grand_final else "spotlight"

    recent_winners = [e.get("winner") for e in entries[-6:] if isinstance(e, dict) and e.get("winner")]
    sim_hist = {"recent_winners": recent_winners}

    print(
        f"season: S{season_num} Race {race_num}/30 ({league.stage_for_race(race_num)}) | "
        f"theme={recipe.theme} finale={recipe.finale}"
    )
    print(
        f"recipe: {recipe.mode} {recipe.arena} / {recipe.goal} / {recipe.hazards} / "
        f"twist={recipe.twist} relaxed={relaxed}"
    )
    print(f"cast ({len(heroes)}H+{len(extras)}D): {[h.key for h in heroes]} + {'GOLDEN' if is_grand_final else 'std'} dummies")

    trace, best, report = simulate_best(recipe, heroes, extras, seed, history=sim_hist)
    outcome, next_state, next_hof = league.evaluate_and_advance(
        season_state, trace, hall_of_fame=hof, mutate=not a.dry_run
    )
    print(
        f"best: seed={trace.meta['seed']} score={best.total:+.0f} winner={outcome.winner_key} "
        f"leader={outcome.leader_key}({outcome.leader_pts}pts) lead_changed={outcome.lead_changed}"
    )

    league_ctx = {
        "season_number": outcome.season_number,
        "episode_number": outcome.race_number,
        "stage": outcome.stage,
        "current_leader": outcome.leader_key,
        "current_leader_name": outcome.leader_name,
        "points_gap": outcome.points_gap,
        "races_remaining": outcome.races_remaining,
        "lead_changed": outcome.lead_changed,
        "pre_leader": cast_sorted[0] if cast_sorted else None,
        "pre_leader_name": HERO_BY_KEY[cast_sorted[0]].name if cast_sorted else "",
        "rival_name": HERO_BY_KEY[cast_sorted[1]].name if len(cast_sorted) > 1 else "",
        "spotlights": spotlights,
        "finalists": [h.key for h in heroes] if is_grand_final else [],
        "recent_line_ids": sorted(recent_ids),
        "recent_cliches": sorted(recent_cliches),
    }
    # v4.3.1 bracket-aware playoff CTA (Ep 27 -> Q1 pair, Ep 28 -> Q2 pair, Ep 29 -> 3 Grand Finalists)
    cta_keys = league.cta_heroes(next_state, outcome.stage)
    cta_names = [HERO_BY_KEY[k].name for k in cta_keys]
    league_ctx["cta_heroes"] = cta_names
    if len(cta_names) == 3:
        cta_prompt = f"{cta_names[0]}, {cta_names[1]}, or {cta_names[2]} for the crown tomorrow?"
    elif len(cta_names) == 2:
        cta_prompt = f"{cta_names[0]} or {cta_names[1]} tomorrow? Drop your pick!"
    else:
        cta_prompt = comment_prompt(list(HEROES), outcome.winner_key, rng)

    from src.publish import metadata as pub_meta

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    meta_bundle = pub_meta.build_upload_metadata(recipe.arena, outcome, cta_prompt)
    summary = {
        "season": outcome.season_number,
        "race": outcome.race_number,
        "stage": outcome.stage,
        "ribbon": outcome.ribbon_text,
        "recipe": recipe.to_dict(),
        "cast": [h.key for h in heroes],
        "extras": len(extras),
        "golden_extras": is_grand_final,
        "best_seed": trace.meta["seed"],
        "score": best.total,
        "score_parts": best.parts,
        "winner": outcome.winner_key,
        "leader": outcome.leader_key,
        "leader_pts": outcome.leader_pts,
        "top3": outcome.top3,
        "top4": outcome.top4,
        "ko_bonus": outcome.ko_bonus_key,
        "lead_changed": outcome.lead_changed,
        "cta_heroes": cta_keys,
        "resolved_at": trace.meta["resolved_at"],
        "upload_metadata": meta_bundle,
        "candidates": report,
    }
    line_ids: list[str] = []
    cliches: list[str] = []
    if not a.no_render:
        from src.rendering import pipeline

        arena_short = recipe.arena.replace("_", " ").upper()
        ep_label = league.header_label(outcome.season_number, outcome.race_number, arena_short)
        ep = pipeline.Episode(
            trace,
            ep_label,
            season_line=outcome.winner_points_pill,
            prompt=cta_prompt,
            flash_event=flash_event(trace),
            outcome=outcome,
            league_ctx=league_ctx,
        )
        t0 = time.time()
        info = pipeline.encode(ep, out, stills=a.stills, sound=not a.no_audio, brand_stills=a.brand_stills)
        info["render_s"] = round(time.time() - t0, 1)
        print(f"rendered {out} frames={info['frames']} duration={info['duration']:.1f}s in {info['render_s']}s")
        if info.get("sound"):
            line_ids = list(info["sound"].get("line_ids") or [])
            cliches = list(info["sound"].get("cliches") or [])
            print(f"sound: {info['sound']}")
        meta_bundle = pub_meta.build_upload_metadata(recipe.arena, outcome, ep.prompt)
        summary.update(
            video=str(out),
            duration=info["duration"],
            frames=info["frames"],
            render_s=info["render_s"],
            prompt_cta=ep.prompt,
            upload_metadata=meta_bundle,
            cam_zoom_min=info.get("cam_zoom_min"),
            cam_zoom_max=info.get("cam_zoom_max"),
            cam_rescues=info.get("cam_rescues"),
            sound=info.get("sound"),
        )
        out.with_suffix(".json").write_text(json.dumps(summary, indent=2, default=str))

    if not a.dry_run:
        pub_errors: list[str] = []
        if not a.no_render:
            # v4.4/v4.5 ffprobe + loudness + camera zoom sanity gate — FAIL CLOSED (no upload, no league advance)
            from src.publish import validate as gate

            try:
                fails = gate.validate(str(out))
            except (ValueError, FileNotFoundError, RuntimeError, subprocess.TimeoutExpired) as exc:
                fails = [str(exc)]
            summary["ffprobe_gate"] = "PASS" if not fails else fails
            summary["camera_gate"] = "PASS" if not any("camera zoom" in f for f in fails) else "FAIL"
            if fails:
                for f in fails:
                    print(f"[VALIDATION GATE FAIL] {f}")
                out.with_suffix(".json").write_text(json.dumps(summary, indent=2, default=str))
                return 3
            print(f"[VALIDATION GATES PASS] ffprobe=OK zoom=[{summary.get('cam_zoom_min')}..{summary.get('cam_zoom_max')}]")

        entry = recipe_generator.history_entry(recipe, day)
        entry.update({
            "season": outcome.season_number,
            "race": outcome.race_number,
            "stage": outcome.stage,
            "winner": outcome.winner_key,
            "line_ids": list(line_ids),
            "cliches": list(cliches),
        })

        if a.stage_only:
            # Transactional Step A: store pending_state in summary .json without modifying state/*.json on disk
            summary["pending_state"] = {
                "next_state": next_state,
                "next_hof": next_hof,
                "history_entry": entry,
            }
            out.with_suffix(".json").write_text(json.dumps(summary, indent=2, default=str))
            return 0

        if not a.no_render and a.publish:
            from src.publish import alerts, instagram, youtube

            attempted = 0
            succeeded = 0
            if not a.skip_yt:
                attempted += 1
                try:
                    vid = youtube.upload_short(
                        out,
                        meta_bundle["title"],
                        meta_bundle["description"],
                        meta_bundle["tags"],
                        privacy=a.privacy,
                    )
                    summary["youtube_id"] = vid
                    succeeded += 1
                    print(f"[PUBLISHED YT SHORTS] https://youtube.com/shorts/{vid}")
                except Exception as exc:          # noqa: BLE001 - redacted generic log, never leak tokens
                    msg = alerts.redact(f"{type(exc).__name__}: {str(exc)[:180]}")
                    summary["youtube_error"] = msg
                    pub_errors.append(f"YouTube Shorts: {msg}")
                    print(f"[YT PUBLISH FAIL] {msg}")

            if not a.skip_ig:
                attempted += 1
                try:
                    ig_id = instagram.upload_reel(out, meta_bundle["ig_caption"])
                    summary["instagram_id"] = ig_id
                    succeeded += 1
                    print(f"[PUBLISHED IG REELS] media_id={ig_id}")
                except Exception as exc:          # noqa: BLE001 - redacted generic log, never leak tokens
                    msg = alerts.redact(f"{type(exc).__name__}: {str(exc)[:180]}")
                    summary["instagram_error"] = msg
                    pub_errors.append(f"Instagram Reels: {msg}")
                    print(f"[IG PUBLISH FAIL] {msg}")

            if pub_errors:
                alerts.open_alert_issue(
                    f"[ToonToonCastle Alert] S{outcome.season_number} E{outcome.race_number} Publish Error",
                    f"Episode `S{outcome.season_number} E{outcome.race_number}` ({meta_bundle['title']}) encountered "
                    f"upload error(s) ({succeeded}/{attempted} platforms succeeded):\n\n- "
                    + "\n- ".join(pub_errors),
                )
            if attempted > 0 and succeeded == 0:
                # Both platforms failed -> do NOT advance season_state.json so the race is preserved for retry
                out.with_suffix(".json").write_text(json.dumps(summary, indent=2, default=str))
                return 4

        if summary.get("youtube_id"):
            entry["youtube_id"] = summary["youtube_id"]
        if summary.get("instagram_id"):
            entry["instagram_id"] = summary["instagram_id"]
        entry.update(
            utc_date=time.strftime("%Y-%m-%d", time.gmtime()),
            published=bool(summary.get("youtube_id") or summary.get("instagram_id")),
        )
        entries.append(entry)
        league.save_all_state(next_state, next_hof, entries, state_dir=STATE)
        if a.commit_state or a.commit_state_dry_run:
            ok = league.git_commit_state_safe(
                f"chore(league): S{outcome.season_number} R{outcome.race_number}/30 ({outcome.winner_key} wins)",
                ROOT, dry_run=a.commit_state_dry_run,
            )
            print(f"git_commit_state_safe: {ok}")
            if not ok:
                out.with_suffix(".json").write_text(json.dumps(summary, indent=2, default=str))
                return 5
        if pub_errors:
            out.with_suffix(".json").write_text(json.dumps(summary, indent=2, default=str))
            return 4

    out.with_suffix(".json").write_text(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
