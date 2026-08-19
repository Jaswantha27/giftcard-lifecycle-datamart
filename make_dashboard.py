"""
make_dashboard.py
------------------
Generates dashboard-style visuals from the gift card cohort data mart:
KPI summary cards, a cohort redemption heatmap (the classic "cohort
triangle"), a breakage trend line, and a currency breakdown.

Usage:
    python3 make_dashboard.py
"""

import os

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd

OUTPUT_DIR = "output"
COLOR_PRIMARY = "#2563EB"
COLOR_ACCENT = "#06B6D4"
COLOR_WARNING = "#F59E0B"
COLOR_SUCCESS = "#10B981"
COLOR_BG = "#F8FAFC"
COLOR_TEXT = "#0F172A"
COLOR_DIM = "#64748B"

plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["axes.edgecolor"] = "#E2E8F0"
plt.rcParams["axes.labelcolor"] = COLOR_TEXT
plt.rcParams["text.color"] = COLOR_TEXT
plt.rcParams["xtick.color"] = COLOR_DIM
plt.rcParams["ytick.color"] = COLOR_DIM


def load_data():
    mart = pd.read_csv("output/fact_giftcard_cohort_monthly.csv")
    issuance = pd.read_csv("data/giftcard_issuance.csv")
    return mart, issuance


def kpi_cards(mart, issuance):
    """A row of KPI summary cards, styled like dashboard tiles."""
    total_issued = mart[mart.months_since_issuance == 0].cohort_issued_amount.sum()
    total_redeemed = mart.groupby("cohort_month").cumulative_redeemed_amount.last().sum()
    total_breakage = mart.breakage_amount.sum()
    active_cards = (issuance.status == "ACTIVE").sum()
    breakage_rate = total_breakage / total_issued * 100

    kpis = [
        ("Total Issued", f"${total_issued:,.0f}", COLOR_PRIMARY),
        ("Total Redeemed", f"${total_redeemed:,.0f}", COLOR_SUCCESS),
        ("Total Breakage", f"${total_breakage:,.0f}", COLOR_WARNING),
        ("Breakage Rate", f"{breakage_rate:.1f}%", COLOR_ACCENT),
        ("Active Cards", f"{active_cards:,}", COLOR_PRIMARY),
    ]

    fig, axes = plt.subplots(1, 5, figsize=(15, 2.2))
    fig.patch.set_facecolor(COLOR_BG)
    for ax, (label, value, color) in zip(axes, kpis):
        ax.set_facecolor("white")
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(True)
            spine.set_color("#E2E8F0")
        ax.add_patch(mpatches.Rectangle((0, 0.88), 1, 0.06, transform=ax.transAxes,
                                         color=color, clip_on=False))
        ax.text(0.5, 0.55, value, ha="center", va="center", fontsize=20, fontweight="bold",
                color=COLOR_TEXT, transform=ax.transAxes)
        ax.text(0.5, 0.2, label, ha="center", va="center", fontsize=10.5,
                color=COLOR_DIM, transform=ax.transAxes)
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/dashboard_kpi_cards.png", dpi=150, facecolor=COLOR_BG, bbox_inches="tight")
    plt.close()


def cohort_heatmap(mart):
    """Classic cohort retention/redemption triangle: rows = issuance cohort,
    columns = months since issuance, values = % of cohort value redeemed."""
    pivot = mart.pivot_table(
        index="cohort_month", columns="months_since_issuance",
        values="cumulative_redeemed_amount", aggfunc="sum"
    )
    issued = mart[mart.months_since_issuance == 0].set_index("cohort_month")["cohort_issued_amount"]
    pct = pivot.div(issued, axis=0) * 100

    # limit to a readable number of cohorts and months for the visual
    pct = pct.sort_index().iloc[-14:, :13]

    fig, ax = plt.subplots(figsize=(11, 7))
    fig.patch.set_facecolor("white")
    im = ax.imshow(pct.values, cmap="Blues", aspect="auto", vmin=0, vmax=100)

    ax.set_xticks(range(pct.shape[1]))
    ax.set_xticklabels(pct.columns)
    ax.set_yticks(range(pct.shape[0]))
    ax.set_yticklabels([pd.Timestamp(c).strftime("%Y-%m") for c in pct.index])
    ax.set_xlabel("Months since issuance")
    ax.set_ylabel("Issuance cohort")
    ax.set_title("Cumulative redemption % by cohort", fontsize=13, fontweight="bold", pad=14)

    for i in range(pct.shape[0]):
        for j in range(pct.shape[1]):
            val = pct.values[i, j]
            if not np.isnan(val):
                color = "white" if val > 55 else COLOR_TEXT
                ax.text(j, i, f"{val:.0f}", ha="center", va="center", fontsize=7.5, color=color)

    cbar = fig.colorbar(im, ax=ax, shrink=0.8)
    cbar.set_label("% of cohort value redeemed")

    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/dashboard_cohort_heatmap.png", dpi=150, facecolor="white", bbox_inches="tight")
    plt.close()


def breakage_trend(mart):
    """Breakage recognized per cohort, trended by cohort month."""
    breakage_by_cohort = mart.groupby("cohort_month").breakage_amount.sum().reset_index()
    breakage_by_cohort["cohort_month"] = pd.to_datetime(breakage_by_cohort["cohort_month"])
    breakage_by_cohort = breakage_by_cohort.sort_values("cohort_month")

    fig, ax = plt.subplots(figsize=(11, 4.5))
    fig.patch.set_facecolor("white")
    ax.bar(breakage_by_cohort.cohort_month, breakage_by_cohort.breakage_amount,
           width=20, color=COLOR_WARNING, alpha=0.85)
    ax.set_title("Breakage recognized by issuance cohort", fontsize=13, fontweight="bold", pad=14)
    ax.set_ylabel("Breakage amount ($)")
    ax.set_xlabel("Issuance cohort month")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/dashboard_breakage_trend.png", dpi=150, facecolor="white", bbox_inches="tight")
    plt.close()


def currency_breakdown(issuance):
    """Issued amount by currency - a simple segment breakdown tile."""
    by_currency = issuance[issuance.status == "ACTIVE"].groupby("currency").issued_amount.sum().sort_values(ascending=False)

    fig, ax = plt.subplots(figsize=(6, 4.5))
    fig.patch.set_facecolor("white")
    colors = [COLOR_PRIMARY, COLOR_ACCENT, COLOR_SUCCESS]
    ax.bar(by_currency.index, by_currency.values, color=colors[:len(by_currency)])
    ax.set_title("Issued amount by currency", fontsize=13, fontweight="bold", pad=14)
    ax.set_ylabel("Issued amount")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for i, v in enumerate(by_currency.values):
        ax.text(i, v + max(by_currency.values) * 0.02, f"${v:,.0f}", ha="center", fontsize=9, color=COLOR_DIM)
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/dashboard_currency_breakdown.png", dpi=150, facecolor="white", bbox_inches="tight")
    plt.close()


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    mart, issuance = load_data()
    kpi_cards(mart, issuance)
    cohort_heatmap(mart)
    breakage_trend(mart)
    currency_breakdown(issuance)
    print(f"Dashboard visuals written to {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
