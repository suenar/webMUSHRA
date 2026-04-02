#!/usr/bin/env python3
"""
Compare 7 systems across trials on three objective metrics:
  - fad (lower is better)
  - chroma_mean (higher is better)
  - midispec_mean (higher is better)

Generates statistical tables and charts focused on system-to-system comparison.

Usage:
  python3 scripts/analyze_objective_results.py \
    --input results/objective_trial_by_trial_summary.csv \
    --outdir results/analysis
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Iterable, List
import warnings

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats


METRICS_INFO = {
    "fad": {"better": "lower", "label": "FAD"},
    "chroma_mean": {"better": "higher", "label": "Chroma Mean"},
    "midispec_mean": {"better": "higher", "label": "MIDISpec Mean"},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="System comparison analysis for objective trial summary CSV."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("results/objective_trial_by_trial_summary.csv"),
        help="Path to objective CSV input file.",
    )
    parser.add_argument(
        "--outdir",
        type=Path,
        default=Path("results/analysis"),
        help="Directory to write output tables/charts.",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=180,
        help="DPI for output PNG charts.",
    )
    return parser.parse_args()


def ensure_numeric(df: pd.DataFrame, columns: Iterable[str]) -> None:
    for col in columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")


def holm_adjust(pvals: List[float]) -> List[float]:
    """Holm-Bonferroni correction (returns adjusted p-values in original order)."""
    p = np.asarray(pvals, dtype=float)
    n = len(p)
    order = np.argsort(p)
    p_sorted = p[order]
    adjusted_sorted = np.empty(n, dtype=float)
    for i, val in enumerate(p_sorted):
        adjusted_sorted[i] = min(1.0, (n - i) * val)
    adjusted_sorted = np.maximum.accumulate(adjusted_sorted)
    adjusted = np.empty(n, dtype=float)
    adjusted[order] = adjusted_sorted
    return adjusted.tolist()


def cliffs_delta(x: Iterable[float], y: Iterable[float]) -> float:
    xv = np.asarray(list(x), dtype=float)
    yv = np.asarray(list(y), dtype=float)
    gt = sum(ix > iy for ix in xv for iy in yv)
    lt = sum(ix < iy for ix in xv for iy in yv)
    return (gt - lt) / (len(xv) * len(yv))


def metric_system_summary(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for metric, info in METRICS_INFO.items():
        for system, grp in df.groupby("system"):
            x = grp[metric].dropna().values
            if len(x) == 0:
                continue
            q1, q3 = np.quantile(x, 0.25), np.quantile(x, 0.75)
            iqr = q3 - q1
            std = x.std(ddof=1) if len(x) > 1 else 0.0
            sem = std / np.sqrt(len(x)) if len(x) > 1 else 0.0
            ci95 = 1.96 * sem
            rows.append(
                {
                    "metric": metric,
                    "better_direction": info["better"],
                    "system": system,
                    "n": len(x),
                    "mean": x.mean(),
                    "median": np.median(x),
                    "std": std,
                    "cv": std / x.mean() if x.mean() != 0 else np.nan,
                    "min": x.min(),
                    "q1": q1,
                    "q3": q3,
                    "max": x.max(),
                    "iqr": iqr,
                    "ci95_low_mean": x.mean() - ci95,
                    "ci95_high_mean": x.mean() + ci95,
                }
            )
    out = pd.DataFrame(rows)
    return out.sort_values(["metric", "mean"], ascending=[True, True])


def ranking_by_metric(summary_df: pd.DataFrame) -> pd.DataFrame:
    ranking_rows = []
    for metric, info in METRICS_INFO.items():
        m = summary_df[summary_df["metric"] == metric].copy()
        m = m.sort_values("mean", ascending=(info["better"] == "lower"))
        m["rank"] = np.arange(1, len(m) + 1)
        ranking_rows.append(
            m[["metric", "system", "mean", "median", "std", "ci95_low_mean", "ci95_high_mean", "rank"]]
        )
    return pd.concat(ranking_rows, ignore_index=True)


def inferential_by_metric(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for metric, info in METRICS_INFO.items():
        systems = sorted(df["system"].dropna().unique().tolist())
        groups = [df.loc[df["system"] == s, metric].dropna().values for s in systems]
        groups = [g for g in groups if len(g) > 0]

        anova_f = np.nan
        anova_p = np.nan
        if len(groups) >= 2:
            group_means = [g.mean() for g in groups]
            within_ss = sum(float(np.sum((g - g.mean()) ** 2)) for g in groups)
            if within_ss <= 1e-15:
                # Perfectly constant groups: ANOVA F is either inf (different means) or undefined.
                anova_f = np.inf if np.ptp(group_means) > 1e-15 else np.nan
                anova_p = 0.0 if np.isinf(anova_f) else np.nan
            else:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", category=RuntimeWarning)
                    a = stats.f_oneway(*groups)
                anova_f = float(a.statistic)
                anova_p = float(a.pvalue)

        kruskal = stats.kruskal(*groups) if len(groups) >= 2 else None

        all_vals = df[metric].dropna().values
        if len(all_vals) > 0 and len(groups) >= 2:
            grand_mean = all_vals.mean()
            ss_between = sum(len(g) * (g.mean() - grand_mean) ** 2 for g in groups)
            ss_total = sum((all_vals - grand_mean) ** 2)
            eta_sq = ss_between / ss_total if ss_total > 0 else np.nan
        else:
            eta_sq = np.nan

        pivot = df.pivot_table(index="trial_id", columns="system", values=metric, aggfunc="mean")
        complete = pivot.dropna()
        if complete.shape[0] > 1 and complete.shape[1] > 2:
            f_res = stats.friedmanchisquare(*[complete[c].values for c in complete.columns])
            kendall_w = f_res.statistic / (complete.shape[0] * (complete.shape[1] - 1))
            friedman_stat = float(f_res.statistic)
            friedman_p = float(f_res.pvalue)
        else:
            friedman_stat = np.nan
            friedman_p = np.nan
            kendall_w = np.nan

        rows.append(
            {
                "metric": metric,
                "better_direction": info["better"],
                "n_systems": len(systems),
                "n_trials_complete_for_friedman": complete.shape[0],
                "anova_f_stat": anova_f,
                "anova_pvalue": anova_p,
                "eta_squared_anova": eta_sq,
                "kruskal_h_stat": float(kruskal.statistic) if kruskal else np.nan,
                "kruskal_pvalue": float(kruskal.pvalue) if kruskal else np.nan,
                "friedman_chi2_stat": friedman_stat,
                "friedman_pvalue": friedman_p,
                "kendalls_w": kendall_w,
            }
        )
    return pd.DataFrame(rows)


def pairwise_vs_anchor_by_metric(df: pd.DataFrame) -> pd.DataFrame:
    if "anchor" not in set(df["system"].dropna().unique()):
        return pd.DataFrame()

    rows = []
    for metric, info in METRICS_INFO.items():
        pivot = df.pivot_table(index="trial_id", columns="system", values=metric, aggfunc="mean")
        if "anchor" not in pivot.columns:
            continue
        systems = [s for s in sorted(pivot.columns.tolist()) if s != "anchor"]
        metric_rows = []

        for system in systems:
            paired = pivot[["anchor", system]].dropna()
            if len(paired) <= 2:
                continue
            a = paired["anchor"].values
            b = paired[system].values

            if info["better"] == "lower":
                # Positive means tested system improved vs anchor
                delta = (a - b) / np.maximum(np.abs(a), 1e-12) * 100.0
                diff = a - b
            else:
                delta = (b - a) / np.maximum(np.abs(a), 1e-12) * 100.0
                diff = b - a

            # Robust paired one-sided t-test handling for near-zero variance differences.
            diff_std = float(np.std(diff, ddof=1)) if len(diff) > 1 else 0.0
            diff_mean = float(np.mean(diff))
            if diff_std <= 1e-15:
                if diff_mean > 0:
                    t_stat, t_p = np.inf, 0.0
                elif diff_mean < 0:
                    t_stat, t_p = -np.inf, 1.0
                else:
                    t_stat, t_p = np.nan, 1.0
            else:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", category=RuntimeWarning)
                    t_res = stats.ttest_rel(diff, np.zeros_like(diff), alternative="greater")
                t_stat, t_p = float(t_res.statistic), float(t_res.pvalue)

            try:
                w_res = stats.wilcoxon(diff, alternative="greater", zero_method="wilcox")
                w_stat, w_p = float(w_res.statistic), float(w_res.pvalue)
            except ValueError:
                w_stat, w_p = np.nan, np.nan

            metric_rows.append(
                {
                    "metric": metric,
                    "better_direction": info["better"],
                    "system": system,
                    "n_pairs": len(paired),
                    "mean_delta_vs_anchor_%": float(np.mean(delta)),
                    "median_delta_vs_anchor_%": float(np.median(delta)),
                    "cohens_d_paired": float(diff_mean / diff_std) if diff_std > 0 else np.nan,
                    "cliffs_delta_independent": cliffs_delta(b, a),
                    "ttest_stat_one_sided": t_stat,
                    "ttest_pvalue_one_sided": t_p,
                    "wilcoxon_stat_one_sided": w_stat,
                    "wilcoxon_pvalue_one_sided": w_p,
                }
            )

        if metric_rows:
            mdf = pd.DataFrame(metric_rows)
            mdf["ttest_p_holm"] = holm_adjust(mdf["ttest_pvalue_one_sided"].tolist())
            valid_w = mdf["wilcoxon_pvalue_one_sided"].notna()
            mdf["wilcoxon_p_holm"] = np.nan
            if valid_w.sum() > 0:
                adj = holm_adjust(mdf.loc[valid_w, "wilcoxon_pvalue_one_sided"].tolist())
                mdf.loc[valid_w, "wilcoxon_p_holm"] = adj
            rows.append(mdf)

    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True).sort_values(["metric", "mean_delta_vs_anchor_%"], ascending=[True, False])


def winners_by_metric(df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    winner_rows = []
    for metric, info in METRICS_INFO.items():
        grouped = df.groupby("trial_id")[metric]
        idx = grouped.idxmin() if info["better"] == "lower" else grouped.idxmax()
        winners = df.loc[idx, ["trial_id", "system", metric]].copy()
        winners = winners.rename(columns={metric: "value"})
        winners["metric"] = metric
        winner_rows.append(winners[["metric", "trial_id", "system", "value"]])

    trial_winners = pd.concat(winner_rows, ignore_index=True).sort_values(["metric", "trial_id"])
    winner_counts = (
        trial_winners.groupby(["metric", "system"])
        .size()
        .reset_index(name="wins")
        .sort_values(["metric", "wins"], ascending=[True, False])
    )
    return {"trial_winners_by_metric": trial_winners, "trial_winner_counts_by_metric": winner_counts}


def correlation_tables(df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    metrics = list(METRICS_INFO.keys())
    return {
        "pearson_corr": df[metrics].corr(method="pearson"),
        "spearman_corr": df[metrics].corr(method="spearman"),
    }


def make_charts(df: pd.DataFrame, summary_df: pd.DataFrame, outdir: Path, dpi: int) -> List[Path]:
    sns.set_theme(style="whitegrid", context="talk")
    metrics = list(METRICS_INFO.keys())
    created: List[Path] = []

    # 01: Three-metric boxplots by system
    fig, axes = plt.subplots(1, 3, figsize=(22, 6))
    for ax, metric in zip(axes, metrics):
        info = METRICS_INFO[metric]
        order = (
            df.groupby("system")[metric]
            .mean()
            .sort_values(ascending=(info["better"] == "lower"))
            .index
        )
        sns.boxplot(data=df, x="system", y=metric, order=order, ax=ax, hue="system", dodge=False, legend=False)
        sns.stripplot(data=df, x="system", y=metric, order=order, ax=ax, color="black", size=2.8, alpha=0.4)
        ax.set_title(f"{info['label']} by System")
        ax.set_xlabel("System")
        ax.tick_params(axis="x", rotation=30)
        if metric == "fad":
            ax.set_yscale("log")
            ax.set_ylabel(f"{info['label']} (log scale)")
    fig.tight_layout()
    p = outdir / "chart_01_system_comparison_boxplots.png"
    fig.savefig(p, dpi=dpi)
    created.append(p)
    plt.close(fig)

    # 02: Mean ranking with 95% CI for each metric
    fig, axes = plt.subplots(1, 3, figsize=(22, 6))
    for ax, metric in zip(axes, metrics):
        info = METRICS_INFO[metric]
        m = summary_df[summary_df["metric"] == metric].copy()
        m = m.sort_values("mean", ascending=(info["better"] == "lower"))
        ax.bar(
            m["system"],
            m["mean"],
            yerr=(m["ci95_high_mean"] - m["mean"]).values,
            capsize=4,
            color=sns.color_palette("viridis", len(m)),
        )
        ax.set_title(f"Mean {info['label']} ±95% CI")
        ax.tick_params(axis="x", rotation=30)
        if metric == "fad":
            ax.set_yscale("log")
    fig.tight_layout()
    p = outdir / "chart_02_metric_rankings_ci.png"
    fig.savefig(p, dpi=dpi)
    created.append(p)
    plt.close(fig)

    # 03: Trial trajectories for three metrics
    trial_num = df["trial_id"].str.extract(r"(\d+)").astype(int)[0]
    dplot = df.copy()
    dplot["trial_num"] = trial_num
    fig, axes = plt.subplots(1, 3, figsize=(22, 6))
    for ax, metric in zip(axes, metrics):
        info = METRICS_INFO[metric]
        sns.lineplot(
            data=dplot.sort_values("trial_num"),
            x="trial_num",
            y=metric,
            hue="system",
            marker="o",
            ax=ax,
        )
        ax.set_title(f"{info['label']} Across Trials")
        ax.set_xlabel("Trial")
        if metric == "fad":
            ax.set_yscale("log")
        if ax is not axes[-1]:
            ax.legend_.remove()
    axes[-1].legend(bbox_to_anchor=(1.02, 1), loc="upper left", title="System")
    fig.tight_layout()
    p = outdir / "chart_03_trial_trajectories.png"
    fig.savefig(p, dpi=dpi)
    created.append(p)
    plt.close(fig)

    # 04: Correlation heatmap among metrics
    corr = df[metrics].corr(method="pearson")
    fig, ax = plt.subplots(figsize=(7, 6))
    sns.heatmap(corr, annot=True, fmt=".2f", cmap="coolwarm", center=0, square=True, ax=ax)
    ax.set_title("Pearson Correlation (3 Metrics)")
    fig.tight_layout()
    p = outdir / "chart_04_metric_correlation_heatmap.png"
    fig.savefig(p, dpi=dpi)
    created.append(p)
    plt.close(fig)
    return created


def save_excel(tables: Dict[str, pd.DataFrame], outpath: Path) -> None:
    with pd.ExcelWriter(outpath, engine="openpyxl") as writer:
        for name, table in tables.items():
            table.to_excel(writer, sheet_name=name[:31], index=False)


def main() -> None:
    args = parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.input)
    ensure_numeric(
        df,
        [
            "fad",
            "chroma_mean",
            "chroma_ci_half_width",
            "midispec_mean",
            "midispec_ci_half_width",
            "n_trials",
        ],
    )

    required = {"trial_id", "system", *METRICS_INFO.keys()}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    summary = metric_system_summary(df)
    ranking = ranking_by_metric(summary)
    inferential = inferential_by_metric(df)
    pairwise_anchor = pairwise_vs_anchor_by_metric(df)
    winner_tables = winners_by_metric(df)
    corr_tables = correlation_tables(df)

    tables: Dict[str, pd.DataFrame] = {
        "system_metric_summary": summary,
        "system_metric_ranking": ranking,
        "inferential_tests_by_metric": inferential,
        "trial_winners_by_metric": winner_tables["trial_winners_by_metric"],
        "trial_winner_counts_by_metric": winner_tables["trial_winner_counts_by_metric"],
        "pearson_corr": corr_tables["pearson_corr"].reset_index(names="metric"),
        "spearman_corr": corr_tables["spearman_corr"].reset_index(names="metric"),
    }
    if not pairwise_anchor.empty:
        tables["pairwise_vs_anchor_by_metric"] = pairwise_anchor

    for name, table in tables.items():
        table.to_csv(args.outdir / f"{name}.csv", index=False)

    created_files: List[Path] = [args.outdir / f"{name}.csv" for name in tables]
    excel_path = args.outdir / "objective_system_comparison_stats.xlsx"
    save_excel(tables, excel_path)
    created_files.append(excel_path)
    created_files.extend(make_charts(df, summary, args.outdir, args.dpi))

    print("Analysis complete.")
    print(f"Input: {args.input}")
    print(f"Output directory: {args.outdir}")
    print(f"Rows: {len(df)}, Systems: {df['system'].nunique()}, Trials: {df['trial_id'].nunique()}")
    print("\nInferential tests (3 metrics):")
    print(inferential.to_string(index=False))
    print("\nSystem ranking by metric (top-3 each):")
    for metric, info in METRICS_INFO.items():
        top = ranking[ranking["metric"] == metric].head(3)
        print(f"  {metric} ({info['better']} is better):")
        print(top[["system", "mean", "rank"]].to_string(index=False))
    print("\nGenerated files:")
    for p in sorted(created_files):
        print(f"  - {p}")


if __name__ == "__main__":
    main()
