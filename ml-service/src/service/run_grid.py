"""Runs the frozen M1-M4 experiment grid and writes evidence files.

The grid below was fixed on 2026-11-25 BEFORE any grid result was looked at.
Do not edit it to make results look better. If the design must change, add a
new GRID_VERSION and report both versions.

Seeds only change the random part of stochastic shifts (attack_mimicry donors).
Deterministic shifts are run once, so their numbers are not repeated copies.

Usage (from ml-service/):
    python -m src.service.run_grid
"""

from datetime import datetime, timezone
import itertools
import json
from pathlib import Path
import subprocess
from typing import Dict, List, Optional, Sequence
import pandas as pd
from src.config import settings
from src.logger import get_logger, setup_logging
from src.service import grid_analysis as ga
from src.service.model_engine import IDSEngine
from src.service.monitors import DriftMonitorSuite
from src.service.shift_simulator import run_controlled_experiment
from src.service.shifts import STOCHASTIC_REALISTIC_SHIFTS, ShiftContext, build_shift_context

logger = get_logger(__name__)

# v1-2026-11-25: original monitors (median scaling, misaligned SHAP buckets, 512-flow SHAP reference).
# v2-2026-11-25: same grid; monitors fixed (aligned SHAP buckets, class-stratified SHAP reference,
#                conformal surprisal scoring for M1-M4). Report v1 and v2 side by side.
# v3-2026-11-25: same grid and v2 monitors; split changed to grouped_day_label (every day and label
#                in train / val / test). v1 and v2 used per_class_temporal.
# v4-2026-11-25: v3 split and monitors; shifts replaced by physically consistent, model-agnostic
#                shifts (src/service/shifts.py), fixed before any v4 result was seen.
# v5-2026-11-25: v4 shifts; geometric 20-window severity ramp (from 1 byte of padding), evaluation by
#                src/service/grid_analysis.py: FAR on the whole unshifted test stream, M3 vs M4 at matched
#                FAR, degradation = recall drop from the clean-validation baseline, alarms attributable to
#                the shift only. Fixed before any v5 result was seen.
GRID_VERSION = "v5-2026-11-25"
ATTACKS: List[str] = ["DDoS", "DoS", "PortScan"]
SHIFT_TYPES: List[str] = [
    "none",
    "benign_slowdown",
    "attack_low_rate",
    "attack_padding",
    "attack_mimicry",
]
STOCHASTIC_SHIFTS = {"concept_proxy", *STOCHASTIC_REALISTIC_SHIFTS}
SEEDS: List[int] = [42, 43, 44]
MAX_WINDOWS = 40
RECALL_CUTOFF = 0.80  # legacy per-run metric in results.csv; v5 evaluation uses grid_analysis criteria
RAMP = "geometric"
RAMP_WINDOWS = 20  # fits every attack: DDoS, the shortest, has 21 windows with >= 10 flows after the shift start
MONITORS = ["M1", "M2", "M3", "M4"]


def plan_runs(
    attacks: Sequence[str], shift_types: Sequence[str], seeds: Sequence[int]
) -> List[Dict[str, object]]:
    """Lists (attack, shift_type, seed) runs; deterministic shifts get only the first seed."""
    runs: List[Dict[str, object]] = []
    for attack, shift in itertools.product(attacks, shift_types):
        run_seeds = list(seeds) if shift in STOCHASTIC_SHIFTS else [seeds[0]]
        for seed in run_seeds:
            runs.append({"attack": attack, "shift_type": shift, "seed": seed})
    return runs


def _fmt_mean_sd(values: pd.Series) -> str:
    vals = values.dropna()
    if vals.empty:
        return "n/a"
    if len(vals) == 1:
        return f"{vals.iloc[0]:.1f}"
    return f"{vals.mean():.1f} ± {vals.std(ddof=1):.1f}"


def summarise(results: pd.DataFrame) -> pd.DataFrame:
    """Aggregates per-run rows into one row per (attack, shift_type, monitor)."""
    rows = []
    for (attack, shift, monitor), grp in results.groupby(
        ["attack", "shift_type", "monitor"], sort=False
    ):
        rows.append(
            {
                "attack": attack,
                "shift_type": shift,
                "monitor": monitor,
                "runs": len(grp),
                "recall_failed_runs": int(grp["t_fail"].notna().sum()),
                "alarmed_runs": int(grp["t_alarm"].notna().sum()),
                "missed_runs": int(grp["missed_degradation"].sum()),
                "lead_time": _fmt_mean_sd(grp["lead_time_delta_t"]),
                "detection_delay": _fmt_mean_sd(grp["detection_delay"]),
                "pre_shift_far_pct": round(float(grp["empirical_far_pct"].mean()), 2),
            }
        )
    return pd.DataFrame(rows)


def _md_table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(map(str, cols)) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join("" if pd.isna(r[c]) else str(r[c]) for c in cols) + " |")
    return "\n".join(lines) + "\n"


def _primary_table(leads: pd.DataFrame) -> pd.DataFrame:
    """Pre-registered primary view: matched 5% stream FAR, degradation = 0.15 recall drop."""
    sel = leads[
        (leads["threshold"] == ga.PRIMARY["threshold"]) & (leads["criterion"] == ga.PRIMARY["criterion"])
    ]
    rows = []
    for (attack, shift, monitor), grp in sel.groupby(["attack", "shift_type", "monitor"], sort=False):
        rows.append(
            {
                "attack": attack,
                "shift_type": shift,
                "monitor": monitor,
                "runs": len(grp),
                "degraded_runs": int(grp["t_fail"].notna().sum()),
                "warned_runs": int(grp["lead_time"].notna().sum()),
                "missed_runs": int(grp["missed"].sum()),
                "lead_time": _fmt_mean_sd(grp["lead_time"]),
                "t_fail_after_start": _fmt_mean_sd(grp["t_fail"] - grp["shift_start"]),
            }
        )
    return pd.DataFrame(rows)


def _summary_markdown(
    config: dict,
    far: pd.DataFrame,
    achieved: pd.DataFrame,
    primary: pd.DataFrame,
    h2h: pd.DataFrame,
    legacy: pd.DataFrame,
) -> str:
    return (
        f"# M1-M4 experiment grid {config['grid_version']}\n\n"
        f"- Run id: `{config['run_id']}`\n"
        f"- Code commit: `{config['git_commit']}` (dirty working tree: {config['git_dirty']})\n"
        f"- Split: {config.get('split_mode', 'unknown')}; window size: {config['window_size']} flows; "
        f"ramp: {config['ramp']} over {config['ramp_windows']} windows\n"
        "- Shifts are controlled synthetic shifts injected into the chronological test stream.\n"
        "- Definitions: see `src/service/grid_analysis.py` (fixed before any v5 result was seen).\n\n"
        "## False alarms on the whole unshifted test stream (calibrated thresholds, target 5%)\n\n"
        + _md_table(far)
        + "\n## Primary result (pre-registered)\n\n"
        "Matched 5% stream FAR per monitor; degradation = target recall at least 0.15 below its\n"
        "clean-validation recall; only alarms the control run does not also raise count.\n"
        "lead_time = t_fail - t_alarm in windows (missed if no warning at or before t_fail);\n"
        "t_fail_after_start = windows from shift start to degradation.\n\n"
        + _md_table(primary)
        + "\n## M4 vs M3 over all threshold sources and degradation criteria (degraded runs only)\n\n"
        + _md_table(h2h)
        + "\n## Matched-FAR thresholds and the FAR they actually give on the stream\n\n"
        + _md_table(achieved)
        + "\n## Legacy per-run metrics (calibrated thresholds, recall < 0.80, 16 pre-shift windows)\n\n"
        + _md_table(legacy)
    )


def run_grid(
    test_df: pd.DataFrame,
    feature_cols: List[str],
    engine: IDSEngine,
    monitor: DriftMonitorSuite,
    out_dir: Path,
    attacks: Sequence[str] = ATTACKS,
    shift_types: Sequence[str] = SHIFT_TYPES,
    seeds: Sequence[int] = SEEDS,
    max_windows: int = MAX_WINDOWS,
    recall_cutoff: float = RECALL_CUTOFF,
    config: Optional[dict] = None,
    shift_context: Optional[ShiftContext] = None,
    baseline_recalls: Optional[Dict[str, float]] = None,
    ramp: str = RAMP,
    ramp_windows: int = RAMP_WINDOWS,
) -> pd.DataFrame:
    """
    Runs every planned experiment, scores the whole unshifted test stream, evaluates lead times and
    writes results.csv, windows.csv, stream_scores.csv, stream_far.csv, matched_far.csv,
    lead_times.csv, head_to_head.csv, summary.csv, summary.md and config.json.
    """
    if "none" not in shift_types:
        raise ValueError("The grid needs the 'none' control shift to attribute alarms to a shift.")
    out_dir.mkdir(parents=True, exist_ok=True)
    runs = plan_runs(attacks, shift_types, seeds)
    result_rows: List[dict] = []
    window_rows: List[dict] = []

    for i, run in enumerate(runs, start=1):
        logger.info("Grid run %d/%d | %s", i, len(runs), run)
        res = run_controlled_experiment(
            test_df=test_df,
            feature_cols=feature_cols,
            engine=engine,
            monitor=monitor,
            target_attack=str(run["attack"]),
            shift_type=run["shift_type"],  # type: ignore[arg-type]
            max_windows=max_windows,
            recall_cutoff=recall_cutoff,
            seed=int(run["seed"]),  # type: ignore[call-overload]
            shift_context=shift_context,
            ramp=ramp,
            ramp_windows=ramp_windows,
        )
        for comp in res["monitor_comparison"]:
            result_rows.append({**run, "shift_start_window": res["shift_start_window"], **comp})
        for w in res["windows"]:
            window_rows.append({**run, "shift_start_window": res["shift_start_window"], **w})

    results = pd.DataFrame(result_rows)
    results.to_csv(out_dir / "results.csv", index=False)
    windows = pd.DataFrame(window_rows)
    windows.to_csv(out_dir / "windows.csv", index=False)

    logger.info("Scoring the whole unshifted test stream for false-alarm rates...")
    stream = ga.score_stream(test_df, feature_cols, engine, monitor)
    stream.to_csv(out_dir / "stream_scores.csv", index=False)
    far = ga.stream_false_alarm_rates(stream)
    far.to_csv(out_dir / "stream_far.csv", index=False)
    thresholds = ga.matched_far_thresholds(stream)
    achieved = ga.achieved_far(stream, thresholds)
    achieved.to_csv(out_dir / "matched_far.csv", index=False)

    shift_starts = {
        (r["attack"], r["shift_type"], r["seed"]): int(r["shift_start_window"]) for r in result_rows
    }
    leads = ga.lead_time_table(windows, shift_starts, baseline_recalls or {}, thresholds)
    leads.to_csv(out_dir / "lead_times.csv", index=False)
    h2h = ga.head_to_head(leads)
    h2h.to_csv(out_dir / "head_to_head.csv", index=False)

    cfg = dict(config or {})
    cfg.update(
        {
            "grid_version": GRID_VERSION,
            "attacks": list(attacks),
            "shift_types": list(shift_types),
            "seeds": list(seeds),
            "stochastic_shifts": sorted(STOCHASTIC_SHIFTS),
            "max_windows": max_windows,
            "recall_cutoff": recall_cutoff,
            "ramp": ramp,
            "ramp_windows": ramp_windows,
            "baseline_recalls": baseline_recalls,
            "analysis": {
                "primary": ga.PRIMARY,
                "matched_fars": ga.MATCHED_FARS,
                "recall_drops": ga.RECALL_DROPS,
                "legacy_abs_cutoff": ga.LEGACY_ABS_CUTOFF,
            },
            "window_size": settings.WINDOW_SIZE,
            "num_runs": len(runs),
            "shift_spec": shift_context.describe() if shift_context else None,
        }
    )
    cfg.setdefault("run_id", out_dir.name)
    cfg.setdefault("git_commit", "unknown")
    cfg.setdefault("git_dirty", "unknown")
    with open(out_dir / "config.json", "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

    summary = summarise(results)
    summary.to_csv(out_dir / "summary.csv", index=False)
    md = _summary_markdown(cfg, far, achieved, _primary_table(leads), h2h, summary)
    (out_dir / "summary.md").write_text(md, encoding="utf-8")
    logger.info("Grid finished: %d runs -> %s", len(runs), out_dir)
    return results


def _git_state() -> tuple[str, bool]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain", "--", "src"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        )
        return commit, dirty
    except (OSError, subprocess.CalledProcessError):
        return "unknown", True


def main() -> None:
    meta_path = settings.SPLITS_DIR / "split_metadata.json"
    test_path = settings.SPLITS_DIR / "test_stream.parquet"
    with open(meta_path, encoding="utf-8") as f:
        split_meta = json.load(f)
    feature_cols: List[str] = split_meta["feature_cols"]

    engine = IDSEngine.load(settings.ARTIFACTS_DIR / "xgb_ids.joblib")
    monitor = DriftMonitorSuite.load(
        settings.ARTIFACTS_DIR / "reference_profile.joblib",
        settings.ARTIFACTS_DIR / "thresholds.json",
        min_bucket_samples=settings.MIN_BUCKET_SAMPLES,
    )
    test_df = pd.read_parquet(test_path)
    # Shift context from the clean validation split (precedes the test part of every group).
    val_df = pd.read_parquet(settings.SPLITS_DIR / "val_clean.parquet", columns=feature_cols + ["target"])
    shift_context = build_shift_context(val_df, feature_cols, ATTACKS, seed=settings.RANDOM_SEED)
    # Clean-validation recall per class (written by train_and_calibrate) is the degradation baseline.
    with open(settings.ARTIFACTS_DIR / "baseline_metrics.json", encoding="utf-8") as f:
        report = json.load(f)
    baseline_recalls = {a: float(report[a]["recall"]) for a in ATTACKS}

    commit, dirty = _git_state()
    run_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}_grid_{commit}"
    out_dir = settings.ARTIFACTS_DIR / "experiments" / run_id
    config = {
        "run_id": run_id,
        "split_mode": split_meta.get("split_mode", "unknown"),
        "split_fracs": [split_meta.get("train_frac"), split_meta.get("val_frac")],
        "git_commit": commit,
        "git_dirty": dirty,
        "thresholds": monitor.thresholds.__dict__ if monitor.thresholds else None,
    }
    run_grid(
        test_df,
        feature_cols,
        engine,
        monitor,
        out_dir,
        config=config,
        shift_context=shift_context,
        baseline_recalls=baseline_recalls,
    )
    print((out_dir / "summary.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    setup_logging()
    main()
