"""Results table and figures for one grid run.

Reads only the CSVs a grid run already wrote (no model, no data) and writes
``<run>/report/``: ``results.md`` plus four PNG figures. The numbers come from the
pre-registered primary setting in ``grid_analysis.PRIMARY`` (matched 5% FAR,
recall drop of 0.15 from the validation baseline).

Usage::

    python -m src.service.report                      # latest grid run
    python -m src.service.report <run id or folder>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from src.config import settings  # noqa: E402
from src.service.grid_analysis import PRIMARY  # noqa: E402

MONITORS = ["M1", "M2", "M3", "M4"]
MONITOR_NAMES = {
    "M1": "M1 features",
    "M2": "M2 confidence",
    "M3": "M3 features + confidence",
    "M4": "M4 + SHAP explanations",
}
# Fixed categorical order (validated: adjacent CVD dE >= 11.8, normal-vision dE >= 23.8
# on white). Three slots sit below 3:1 contrast, so every figure has direct labels
# and results.md is the table view.
COLORS = {"M1": "#257de0", "M2": "#f47230", "M3": "#00b894", "M4": "#f2a600"}
TIE = "#b4b4b4"
TEXT = "#191919"
TEXT_2 = "#666666"
GRID = "#e6e6e6"
SHIFT_LABELS = {
    "attack_padding": "padding",
    "attack_mimicry": "mimicry",
    "attack_low_rate": "low rate",
    "benign_slowdown": "benign slowdown",
}
TIMELINE_RUN = ("PortScan", "attack_mimicry", 42)


def _style() -> None:
    plt.rcParams.update({
        "figure.dpi": 150, "savefig.dpi": 200, "font.size": 10,
        "axes.edgecolor": GRID, "axes.labelcolor": TEXT_2, "axes.titlecolor": TEXT,
        "axes.titlesize": 11, "axes.titleweight": "bold", "axes.titlelocation": "left",
        "axes.spines.top": False, "axes.spines.right": False,
        "xtick.color": TEXT_2, "ytick.color": TEXT_2, "text.color": TEXT,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
        "legend.frameon": False,
    })


def _resolve_run(arg: str | None) -> Path:
    root = settings.ARTIFACTS_DIR / "experiments"
    if arg:
        path = Path(arg)
        return path if path.is_dir() else root / arg
    runs = sorted(p for p in root.glob("*_grid_*") if p.is_dir())
    if not runs:
        raise SystemExit(f"no grid runs in {root}")
    return runs[-1]


def _primary(leads: pd.DataFrame) -> pd.DataFrame:
    return leads[(leads.threshold == PRIMARY["threshold"]) & (leads.criterion == PRIMARY["criterion"])]


def _pct(setting: str) -> str:
    """'far_0.05' -> '5%'."""
    return f"{round(float(setting.split('_')[1]) * 100, 2):g}%"


def _spread(ys: dict, gap: float) -> dict:
    """Nudge end-of-line label positions apart so they never overlap."""
    out, last = {}, None
    for k, y in sorted(ys.items(), key=lambda kv: kv[1]):
        y = y if last is None else max(y, last + gap)
        out[k] = last = y
    return out


def _fmt_lead(values: pd.Series) -> str:
    values = values.dropna()
    if values.empty:
        return "missed"
    if len(values) == 1:
        return f"{values.iloc[0]:.0f}"
    return f"{values.mean():.1f} ± {values.std(ddof=1):.1f}"


def results_table(leads: pd.DataFrame) -> pd.DataFrame:
    """Per attack x shift: runs, degraded runs and per-monitor lead time (windows)."""
    p = _primary(leads)
    p = p[p.shift_type != "none"]
    rows = []
    for (attack, shift), g in p.groupby(["attack", "shift_type"], sort=False):
        runs = g.seed.nunique()
        degraded = g[g.t_fail.notna()]
        row = {"attack": attack, "shift": SHIFT_LABELS.get(shift, shift), "runs": runs,
               "degraded": degraded.seed.nunique()}
        for m in MONITORS:
            d = degraded[degraded.monitor == m]
            row[m] = _fmt_lead(d.lead_time) if not d.empty else "–"
        rows.append(row)
    return pd.DataFrame(rows)


def _md(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(str(v) for v in r) + " |" for r in df.itertuples(index=False)]
    return "\n".join(lines)


def write_results_md(run: Path, out: Path, leads, stream_far, h2h, matched) -> None:
    cfg = json.loads((run / "config.json").read_text())
    table = results_table(leads)
    far = stream_far.rename(columns={
        "far_all_pct": "FAR all windows (%)", "far_benign_only_pct": "FAR benign-only (%)"})
    h = h2h[h2h.criterion == PRIMARY["criterion"]].drop(columns="criterion")
    m5 = matched[matched.threshold == PRIMARY["threshold"]][["monitor", "achieved_far_pct"]]
    text = f"""# Results: grid run `{run.name}`

- Code commit: `{cfg.get("git_commit", "?")}` (dirty tree: {cfg.get("git_dirty", "?")})
- Primary setting (pre-registered): alarm threshold at a matched
  {_pct(PRIMARY["threshold"])} false-alarm rate; degradation = recall drop of
  {PRIMARY["criterion"].split("_")[1]} (absolute) from the validation baseline recall.
- Lead time = degradation window - first alarm window caused by the shift (alarms
  that also fire in the unshifted control run do not count). Unit: replay windows.
- `missed` = recall degraded but the monitor never alarmed before it. `–` = recall
  never degraded, so there is nothing to warn about. Mimicry has 3 seeds (mean ± sd);
  the other shifts are deterministic (1 run).

## Table 1. Lead time before recall degrades (windows, higher is better)

{_md(table)}

## Table 2. Natural false-alarm rate on the unshifted test replay (calibrated thresholds, target 5%)

{_md(far)}

Achieved FAR at the matched {_pct(PRIMARY["threshold"])} thresholds:
{", ".join(f"{r.monitor} {r.achieved_far_pct}%" for r in m5.itertuples())}.

## Table 3. M4 vs M3 head-to-head over degraded runs ({PRIMARY["criterion"]})

{_md(h)}
"""
    (out / "results.md").write_text(text, encoding="utf-8")


def fig_timeline(windows, matched, baseline_recall, out: Path) -> None:
    attack, shift, seed = TIMELINE_RUN
    run = windows[(windows.attack == attack) & (windows.shift_type == shift) & (windows.seed == seed)]
    run = run.sort_values("window_id")
    start = int(run.shift_start_window.iloc[0])
    thr = matched[matched.threshold == PRIMARY["threshold"]].set_index("monitor").score_threshold
    drop = float(PRIMARY["criterion"].split("_")[1])
    x = run.window_id
    post = run[(run.window_id >= start) & run.target_recall.notna()]
    failed = post[(baseline_recall - post.target_recall) >= drop - 1e-12]
    t_fail = int(failed.window_id.iloc[0]) if not failed.empty else None

    fig, (a1, a2, a3) = plt.subplots(3, 1, figsize=(9, 7), sharex=True,
                                     gridspec_kw={"height_ratios": [1, 1.4, 2]})
    a1.plot(x, run.severity, color=TEXT_2, lw=2)
    a1.set_ylabel("shift severity")
    fig.suptitle(f"{attack} under {SHIFT_LABELS[shift]} (seed {seed}): monitors alarm before recall drops",
                 x=0.01, ha="left", fontsize=12, fontweight="bold", color=TEXT)

    r = run[run.target_recall.notna()]
    a2.plot(r.window_id, r.target_recall, color=TEXT, lw=2, marker="o", ms=3)
    a2.axhline(baseline_recall - drop, color=TEXT_2, lw=1, ls="--")
    a2.text(x.min(), baseline_recall - drop - 0.02, f"degraded: recall {baseline_recall - drop:.2f}",
            color=TEXT_2, va="top", fontsize=9)
    a2.set_ylabel(f"{attack} recall")
    a2.set_ylim(0, 1.05)

    last = run.iloc[-1]
    ends = {m: last[f"{m.lower()}_score"] / thr[m] for m in MONITORS}
    for m in MONITORS:
        a3.plot(x, run[f"{m.lower()}_score"] / thr[m], color=COLORS[m], lw=2, label=MONITOR_NAMES[m])
    for m, y in _spread(ends, gap=0.14).items():
        a3.text(last.window_id + 0.4, y, m, color=TEXT, fontsize=9, va="center")
    a3.axhline(1, color=TEXT, lw=1, ls="--")
    a3.text(x.min(), 1.03, f"alarm threshold (matched {_pct(PRIMARY['threshold'])} FAR)",
            color=TEXT_2, fontsize=9, va="bottom")
    a3.text(x.min(), -0.32, "M1 crosses before the shift starts, but it does the same in the unshifted "
            "control run, so those alarms do not count as warnings.", color=TEXT_2, fontsize=8.5,
            transform=a3.get_xaxis_transform())
    a3.set_ylabel("score / alarm threshold")
    a3.set_xlabel("replay window")
    a3.legend(loc="upper left", bbox_to_anchor=(0, -0.4), ncol=4, fontsize=9)

    for ax in (a1, a2, a3):
        ax.axvline(start, color=TEXT_2, lw=1)
        if t_fail is not None:
            ax.axvline(t_fail, color=TEXT, lw=1, ls=":")
    a1.text(start - 0.3, 0.6, "shift starts ", color=TEXT_2, fontsize=9, ha="right",
            transform=a1.get_xaxis_transform())
    if t_fail is not None:
        a1.text(t_fail - 0.3, 0.6, f"recall degraded\n(+{t_fail - start} windows) ", color=TEXT,
                fontsize=9, ha="right", transform=a1.get_xaxis_transform())
    fig.tight_layout()
    fig.savefig(out / "fig1_replay_timeline.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def fig_lead_times(leads: pd.DataFrame, out: Path) -> None:
    p = _primary(leads)
    p = p[p.t_fail.notna()]
    scenarios = list(dict.fromkeys(zip(p.attack, p.shift_type)))
    fig, ax = plt.subplots(figsize=(9, 4.2))
    width = 0.2
    for i, m in enumerate(MONITORS):
        for j, (attack, shift) in enumerate(scenarios):
            d = p[(p.attack == attack) & (p.shift_type == shift) & (p.monitor == m)]
            pos = j + (i - 1.5) * (width + 0.02)
            if d.lead_time.notna().sum() == 0:
                ax.text(pos, 0.3, "missed", rotation=90, ha="center", va="bottom", fontsize=8, color=TEXT_2)
                continue
            val = d.lead_time.mean()
            ax.bar(pos, val, width, color=COLORS[m], label=MONITOR_NAMES[m] if j == 0 else None,
                   edgecolor="white", linewidth=1)
            ax.text(pos, val + 0.2, f"{val:.0f}", ha="center", va="bottom", fontsize=8, color=TEXT)
    ax.set_xticks(range(len(scenarios)))
    ax.set_xticklabels([f"{a}\n{SHIFT_LABELS[s]}" + (" (3 seeds)" if s == "attack_mimicry" else "")
                        for a, s in scenarios])
    ax.set_ylabel("lead time (windows before degradation)")
    ax.grid(axis="x", visible=False)
    ax.set_title(f"Warning lead time at matched {_pct(PRIMARY['threshold'])} FAR: "
                 "M2, M3 and M4 nearly tie; M1 misses 4 of 5")
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(facecolor=COLORS[m], label=MONITOR_NAMES[m]) for m in MONITORS],
              loc="upper left", bbox_to_anchor=(0, -0.2), ncol=4, fontsize=9)
    fig.tight_layout()
    fig.savefig(out / "fig2_lead_times.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def fig_far(stream_far: pd.DataFrame, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(7, 3.8))
    width = 0.36
    for i, r in enumerate(stream_far.itertuples()):
        c = COLORS[r.monitor]
        ax.bar(i - width / 2 - 0.01, r.far_all_pct, width, color=c, edgecolor="white", linewidth=1)
        ax.bar(i + width / 2 + 0.01, r.far_benign_only_pct, width, color="white", edgecolor=c,
               hatch="////", linewidth=1.5)
        ax.text(i - width / 2, r.far_all_pct + 0.2, f"{r.far_all_pct:.1f}", ha="center", fontsize=8)
        ax.text(i + width / 2, r.far_benign_only_pct + 0.2, f"{r.far_benign_only_pct:.1f}", ha="center", fontsize=8)
    ax.axhline(5, color=TEXT, lw=1, ls="--")
    ax.text(len(stream_far) - 0.5, 5.15, "5% target", ha="right", va="bottom", fontsize=9, color=TEXT_2)
    ax.set_xticks(range(len(stream_far)))
    two_line = {"M1": "M1\nfeatures", "M2": "M2\nconfidence", "M3": "M3\nfeatures +\nconfidence",
                "M4": "M4\n+ SHAP\nexplanations"}
    ax.set_xticklabels([two_line[m] for m in stream_far.monitor])
    ax.set_ylabel("false-alarm rate (%)")
    ax.grid(axis="x", visible=False)
    ax.set_title("Natural false-alarm rate on the unshifted test replay")
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(facecolor=TEXT_2, label=f"all windows (n={stream_far.windows.iloc[0]})"),
                       Patch(facecolor="white", edgecolor=TEXT_2, hatch="////",
                             label=f"benign-only windows (n={stream_far.benign_only_windows.iloc[0]})")],
              loc="upper right", fontsize=9)
    fig.tight_layout()
    fig.savefig(out / "fig3_false_alarm_rate.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def fig_head_to_head(h2h: pd.DataFrame, out: Path) -> None:
    h = h2h[h2h.criterion == PRIMARY["criterion"]].copy()
    label = {"calibrated": "calibrated", "far_0.01": "1% FAR", "far_0.02": "2% FAR",
             "far_0.05": "5% FAR (primary)", "far_0.10": "10% FAR"}
    order = ["far_0.01", "far_0.02", "far_0.05", "far_0.10", "calibrated"]
    h = h.set_index("threshold").loc[order]
    fig, ax = plt.subplots(figsize=(8, 3.4))
    ax.set_axisbelow(True)
    parts =[("M3 earlier", COLORS["M3"]), ("tie", TIE), ("M4 earlier", COLORS["M4"])]
    for k, t in enumerate(h.index):
        left = 0
        for col, c in parts:
            v = int(h.loc[t, col])
            if v:
                ax.barh(k, v, left=left, color=c, edgecolor="white", linewidth=2, height=0.6)
                ax.text(left + v / 2, k, f"{col}: {v}" if v >= 2 else str(v), ha="center", va="center",
                        fontsize=8, color=TEXT)
            left += v
    ax.set_yticks(range(len(h)))
    ax.set_yticklabels([label[t] for t in h.index])
    ax.invert_yaxis()
    ax.set_xlabel(f"degraded runs (n={int(h.degraded_runs.iloc[0])})")
    ax.grid(axis="y", visible=False)
    ax.set_title("Which monitor warned first? M4 never beats M3 at the primary setting")
    fig.tight_layout()
    fig.savefig(out / "fig4_m4_vs_m3.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main(argv: list[str]) -> Path:
    run = _resolve_run(argv[0] if argv else None)
    out = run / "report"
    out.mkdir(exist_ok=True)
    leads = pd.read_csv(run / "lead_times.csv")
    windows = pd.read_csv(run / "windows.csv")
    stream_far = pd.read_csv(run / "stream_far.csv")
    matched = pd.read_csv(run / "matched_far.csv")
    h2h = pd.read_csv(run / "head_to_head.csv")
    baseline = json.loads((settings.ARTIFACTS_DIR / "baseline_metrics.json").read_text())
    _style()
    write_results_md(run, out, leads, stream_far, h2h, matched)
    fig_timeline(windows, matched, baseline[TIMELINE_RUN[0]]["recall"], out)
    fig_lead_times(leads, out)
    fig_far(stream_far, out)
    fig_head_to_head(h2h, out)
    print(f"report written to {out}")
    return out


if __name__ == "__main__":
    main(sys.argv[1:])
