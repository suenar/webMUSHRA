#!/usr/bin/env python3
"""
Analyze objective trial-by-trial summary CSV and generate:
  - Descriptive statistics
  - Robust per-system statistics
  - Inferential tests (ANOVA, Kruskal-Wallis, paired tests vs anchor)
  - Effect sizes vs anchor
  - Trial winner summaries
  - Multiple charts

Usage:
  python3 scripts/analyze_objective_results.py \
    --input results/objective_trial_by_trial_summary.csv \
    --outdir results/analysis
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Iterable, List

import numpy as np
import pandas as pd
from scipy import stats
import matplotlib.pyplot as plt
import seaborn as sns


def cliffs_delta(x: Iterable[float], y: Iterable[float]) -> float:
    """Compute Cliff's delta effect size for two independent samples."""
    xv = np.asarray(list(x), dtype=float)
    yv = np.asarray(list(y), dtype=float)
    gt = sum(ix > iy for ix in xv for iy in yv)
    lt = sum(ix < iy for ix in xv for iy in yv)
    return (gt - lt) / (len(xv) * len(yv))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze objective trial-by-trial summary CSV."
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
        help="DPI for PNG charts.",
    )
    return parser.parse_args()


def ensure_numeric(df: pd.DataFrame, columns: List[str]) -> None:
    for col in columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")


def compute_global_tables(df: pd.DataFrame, metrics: List[str]) -> Dict[str, pd.DataFrame]:
    global_stats = df[metrics].agg(["count", "mean", "median", "std", "min", "max"]).T
    global_stats["cv"] = global_stats["std"] / global_stats["mean"]
    global_stats["skew"] = df[metrics].skew(numeric_only=True)
    global_stats["kurtosis"] = df[metrics].kurtosis(numeric_only=True)

    percentiles = df[metrics].quantile(
        [0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99]
    ).T

    per_system_stats = df.groupby("system")[metrics].agg(
        ["count", "mean", "median", "std", "min", "max"]
    )

    fad_ranking = (
        df.groupby("system")["fad"].mean().sort_values().reset_index()
    )
    fad_ranking["rank"] = np.arange(1, len(fad_ranking) + 1)

    pearson_corr = df[metrics].corr(method="pearson")
    spearman_corr = df[metrics].corr(method="spearman")

    q1, q3 = df["fad"].quantile([0.25, 0.75])
    iqr = q3 - q1
    lb, ub = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    fad_outliers = df[(df["fad"] < lb) | (df["fad"] > ub)].sort_values(
        "fad", ascending=False
    )

    return {
        "global_stats": global_stats,
        "percentiles": percentiles,
        "per_system_stats": per_system_stats,
        "fad_ranking": fad_ranking,
        "pearson_corr": pearson_corr,
        "spearman_corr": spearman_corr,
        "fad_outliers": fad_outliers,
    }


def compute_vs_anchor(df: pd.DataFrame) -> pd.DataFrame:
    pivot = df.pivot_table(index="trial_id", columns="system", values="fad", aggfunc="mean")
    if "anchor" not in pivot.columns:
        return pd.DataFrame()

    rows = {}
    for system in pivot.columns:
        if system == "anchor":
            continue
        paired = pivot[["anchor", system]].dropna()
        if len(paired) <= 2:
            continue
        improvement = (paired["anchor"] - paired[system]) / paired["anchor"] * 100.0
        t_res = stats.ttest_rel(paired["anchor"], paired[system], alternative="greater")
        w_res = stats.wilcoxon(
            paired["anchor"] - paired[system],
            alternative="greater",
            zero_method="wilcox",
        )
        rows[system] = {
            "n_pairs": len(paired),
            "mean_improvement_%": improvement.mean(),
            "median_improvement_%": improvement.median(),
            "t_stat": float(t_res.statistic),
            "t_pvalue_one_sided": float(t_res.pvalue),
            "wilcoxon_stat": float(w_res.statistic),
            "wilcoxon_pvalue_one_sided": float(w_res.pvalue),
        }
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).T.sort_values("mean_improvement_%", ascending=False)


def compute_inferential(df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    systems = sorted(df["system"].dropna().unique().tolist())
    groups = [df.loc[df["system"] == s, "fad"].dropna().values for s in systems]

    anova = stats.f_oneway(*groups)
    kruskal = stats.kruskal(*groups)

    all_vals = df["fad"].dropna().values
    grand_mean = all_vals.mean()
    ss_between = sum(len(g) * (g.mean() - grand_mean) ** 2 for g in groups)
    ss_total = sum((all_vals - grand_mean) ** 2)
    eta_sq = ss_between / ss_total

    overall = pd.DataFrame(
        [
            {"test": "one_way_anova", "statistic": anova.statistic, "pvalue": anova.pvalue},
            {"test": "kruskal_wallis", "statistic": kruskal.statistic, "pvalue": kruskal.pvalue},
            {"test": "eta_squared_from_anova", "statistic": eta_sq, "pvalue": np.nan},
        ]
    )

    robust_rows = []
    for system, grp in df.groupby("system"):
        x = grp["fad"].dropna().values
        q1, q3 = np.quantile(x, 0.25), np.quantile(x, 0.75)
        iqr = q3 - q1
        sem = x.std(ddof=1) / np.sqrt(len(x))
        ci95 = 1.96 * sem
        sh = stats.shapiro(x)
        robust_rows.append(
            {
                "system": system,
                "n": len(x),
                "mean": x.mean(),
                "median": np.median(x),
                "std": x.std(ddof=1),
                "cv": x.std(ddof=1) / x.mean(),
                "q1": q1,
                "q3": q3,
                "iqr": iqr,
                "ci95_low_mean": x.mean() - ci95,
                "ci95_high_mean": x.mean() + ci95,
                "shapiro_W": sh.statistic,
                "shapiro_p": sh.pvalue,
            }
        )
    per_system_robust = pd.DataFrame(robust_rows).sort_values("mean")

    effect_sizes_vs_anchor = pd.DataFrame()
    if "anchor" in df["system"].values:
        anchor = df.loc[df["system"] == "anchor", "fad"].values
        effect_rows = []
        for system in systems:
            if system == "anchor":
                continue
            x = df.loc[df["system"] == system, "fad"].values
            nx, ny = len(x), len(anchor)
            sx, sy = x.std(ddof=1), anchor.std(ddof=1)
            sp = np.sqrt(((nx - 1) * sx * sx + (ny - 1) * sy * sy) / (nx + ny - 2))
            d = (x.mean() - anchor.mean()) / sp
            u_res = stats.mannwhitneyu(x, anchor, alternative="two-sided")
            effect_rows.append(
                {
                    "system": system,
                    "mean_fad": x.mean(),
                    "delta_vs_anchor_mean": x.mean() - anchor.mean(),
                    "cohens_d_vs_anchor": d,
                    "cliffs_delta_vs_anchor": cliffs_delta(x, anchor),
                    "mannwhitney_u": u_res.statistic,
                    "mannwhitney_p_two_sided": u_res.pvalue,
                }
            )
        effect_sizes_vs_anchor = pd.DataFrame(effect_rows).sort_values("mean_fad")

    return {
        "overall_inferential_stats": overall,
        "per_system_robust_stats": per_system_robust,
        "effect_sizes_vs_anchor": effect_sizes_vs_anchor,
    }


def compute_trial_winners(df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    idx = df.groupby("trial_id")["fad"].idxmin()
    winners = df.loc[idx, ["trial_id", "system", "fad"]].sort_values("trial_id")
    winner_counts = (
        winners["system"].value_counts().rename_axis("system").reset_index(name="wins")
    )
    return {"trial_winners": winners, "trial_winner_counts": winner_counts}


def save_tables_as_csv(tables: Dict[str, pd.DataFrame], outdir: Path) -> None:
    for name, table in tables.items():
        table.to_csv(outdir / f"{name}.csv", index=(table.index.name is not None))


def save_excel(all_tables: Dict[str, pd.DataFrame], outpath: Path) -> None:
    with pd.ExcelWriter(outpath, engine="openpyxl") as writer:
        for name, table in all_tables.items():
            table.to_excel(writer, sheet_name=name[:31], index=True)


def make_charts(df: pd.DataFrame, pearson_corr: pd.DataFrame, outdir: Path, dpi: int) -> None:
    sns.set_theme(style="whitegrid", context="talk")

    # 01: FAD distribution
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    sns.histplot(df["fad"], bins=30, kde=True, ax=axes[0], color="#4C72B0")
    axes[0].set_title("FAD Distribution (Linear Scale)")
    axes[0].set_xlabel("FAD")
    sns.histplot(np.log10(df["fad"]), bins=30, kde=True, ax=axes[1], color="#55A868")
    axes[1].set_title("log10(FAD) Distribution")
    axes[1].set_xlabel("log10(FAD)")
    fig.tight_layout()
    fig.savefig(outdir / "chart_01_fad_distribution.png", dpi=dpi)
    plt.close(fig)

    # 02: FAD by system
    order = df.groupby("system")["fad"].mean().sort_values().index
    fig, ax = plt.subplots(figsize=(12, 7))
    sns.boxplot(data=df, x="system", y="fad", order=order, ax=ax, hue="system", dodge=False, legend=False)
    sns.stripplot(data=df, x="system", y="fad", order=order, ax=ax, color="black", size=3, alpha=0.45)
    ax.set_title("FAD by System (lower is better)")
    ax.set_xlabel("System (sorted by mean FAD)")
    ax.tick_params(axis="x", rotation=30)
    fig.tight_layout()
    fig.savefig(outdir / "chart_02_fad_by_system_box.png", dpi=dpi)
    plt.close(fig)

    # 03: Mean metrics by system
    metrics = ["fad", "chroma_mean", "midispec_mean"]
    sys_mean = df.groupby("system")[metrics].mean()
    fig, ax = plt.subplots(figsize=(12, 7))
    sys_mean.sort_values("fad").plot(kind="bar", ax=ax)
    ax.set_title("Mean Metrics by System")
    ax.set_ylabel("Metric value")
    ax.tick_params(axis="x", rotation=30)
    fig.tight_layout()
    fig.savefig(outdir / "chart_03_system_means.png", dpi=dpi)
    plt.close(fig)

    # 04: FAD across trials (log scale)
    trial_num = df["trial_id"].str.extract(r"(\d+)").astype(int)[0]
    df_plot = df.copy()
    df_plot["trial_num"] = trial_num
    fig, ax = plt.subplots(figsize=(14, 8))
    sns.lineplot(
        data=df_plot.sort_values("trial_num"),
        x="trial_num",
        y="fad",
        hue="system",
        marker="o",
        ax=ax,
    )
    ax.set_title("FAD Across Trials")
    ax.set_xlabel("Trial Number")
    ax.set_ylabel("FAD")
    ax.set_yscale("log")
    ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left")
    fig.tight_layout()
    fig.savefig(outdir / "chart_04_fad_trial_trends_log.png", dpi=dpi)
    plt.close(fig)

    # 05: Correlation heatmap
    fig, ax = plt.subplots(figsize=(7, 6))
    sns.heatmap(
        pearson_corr,
        annot=True,
        fmt=".2f",
        cmap="coolwarm",
        center=0,
        ax=ax,
        square=True,
    )
    ax.set_title("Pearson Correlation Heatmap")
    fig.tight_layout()
    fig.savefig(outdir / "chart_05_correlation_heatmap.png", dpi=dpi)
    plt.close(fig)

    # 06: FAD ranking + 95% CI
    rank_stats = df.groupby("system")["fad"].agg(["mean", "std", "count"]).sort_values("mean")
    rank_stats["sem"] = rank_stats["std"] / np.sqrt(rank_stats["count"])
    rank_stats["ci95"] = 1.96 * rank_stats["sem"]
    fig, ax = plt.subplots(figsize=(12, 7))
    ax.bar(
        rank_stats.index,
        rank_stats["mean"],
        yerr=rank_stats["ci95"],
        capsize=5,
        color=sns.color_palette("viridis", len(rank_stats)),
    )
    ax.set_title("Mean FAD by System with Approx. 95% CI")
    ax.set_ylabel("FAD (lower better)")
    ax.tick_params(axis="x", rotation=30)
    fig.tight_layout()
    fig.savefig(outdir / "chart_06_fad_ranking_ci.png", dpi=dpi)
    plt.close(fig)


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

    required = {"trial_id", "system", "fad", "chroma_mean", "midispec_mean"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    metrics = ["fad", "chroma_mean", "midispec_mean"]
    table_group_1 = compute_global_tables(df, metrics)
    table_group_2 = {"vs_anchor_tests": compute_vs_anchor(df)}
    table_group_3 = compute_inferential(df)
    table_group_4 = compute_trial_winners(df)

    all_tables: Dict[str, pd.DataFrame] = {}
    for group in [table_group_1, table_group_2, table_group_3, table_group_4]:
        for key, value in group.items():
            if isinstance(value, pd.DataFrame) and not value.empty:
                all_tables[key] = value

    for name, table in all_tables.items():
        table.to_csv(args.outdir / f"{name}.csv", index=True)

    save_excel(all_tables, args.outdir / "objective_stats_summary.xlsx")
    make_charts(df, table_group_1["pearson_corr"], args.outdir, args.dpi)

    print("Analysis complete.")
    print(f"Input: {args.input}")
    print(f"Output directory: {args.outdir}")
    print(f"Rows: {len(df)}, Systems: {df['system'].nunique()}, Trials: {df['trial_id'].nunique()}")
    print("\nTop systems by mean FAD (lower is better):")
    print(table_group_1["fad_ranking"].head(7).to_string(index=False))
    print("\nGenerated:")
    for p in sorted(args.outdir.glob("*.csv")):
        print(f"  - {p}")
    for p in sorted(args.outdir.glob("*.png")):
        print(f"  - {p}")
    print(f"  - {args.outdir / 'objective_stats_summary.xlsx'}")


if __name__ == "__main__":
    main()
