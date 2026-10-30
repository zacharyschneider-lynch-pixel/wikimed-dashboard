"""
Generate NCI Data to Discovery poster figures for the Cancer Dashboard.

Palettes were validated for colour-vision deficiency before use (OKLab delta-E,
Machado 2009 CVD simulation). The dashboard's 6-class quality ramp fails
adjacent-pair separation on two pairs under normal vision (Start/C = 12.8,
GA/FA = 13.5, both below the 15 floor), and six near-blues are unreadable at
poster viewing distance, so quality is collapsed to three validated classes
here: #B2182B / #E08214 / #2166AC, worst-case CVD separation 18.7.

Outputs 300 dpi PNGs to poster_figures/.
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

OUT = "poster_figures"
os.makedirs(OUT, exist_ok=True)

# ── Design tokens ─────────────────────────────────────────────────────────────
INK        = "#1A1A1A"   # primary text
INK_MUTED  = "#5A5A5A"   # secondary text / axis labels
GRID       = "#D8D8D8"
SURFACE    = "#FFFFFF"

# Validated 3-class quality palette (0 FAIL, worst CVD dE 18.7)
Q3 = {"Stub / Start": "#B2182B", "C / B": "#E08214", "GA / FA": "#2166AC"}
# Validated confidence-ordered Blues (0 FAIL)
BLUES3 = ["#08519C", "#6BAED6", "#BDD7E7"]
SEQ_HUE = "#08519C"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 13,
    "text.color": INK,
    "axes.labelcolor": INK,
    "axes.edgecolor": GRID,
    "axes.linewidth": 0.8,
    "xtick.color": INK_MUTED,
    "ytick.color": INK_MUTED,
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
})

CANCER_KW = ["cancer", "carcinoma", "tumor", "tumour", "malignant", "malignancy",
             "leukemia", "leukaemia", "lymphoma", "sarcoma", "melanoma", "neoplasm",
             "oncology", "glioma", "blastoma", "adenoma", "mesothelioma", "myeloma",
             "metastasis", "metastatic"]
QORDER = ["Stub", "Start", "C", "B", "GA", "FA"]
IORDER = ["Top", "High", "Mid", "Low"]


def q3(q):
    if q in ("Stub", "Start"):
        return "Stub / Start"
    if q in ("C", "B"):
        return "C / B"
    if q in ("GA", "FA"):
        return "GA / FA"
    return None


def load():
    df = pd.read_csv("data/scored_articles.csv")
    for c in ["impact_need_score", "wiki_attention_score", "reading_level",
              "pageviews_12mo", "unique_editors"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    c04 = set(pd.read_csv("data/cancer_mesh_ids.csv")["mesh_id"].dropna())
    tx = pd.read_csv("data/cancer_treatment_mesh_ids.csv")
    txmap = dict(zip(tx["mesh_id"].astype(str), tx["category"].astype(str)))
    m = df["mesh_id"].astype(str)
    c04m, txm = m.isin(c04), m.isin(txmap)
    meshm = c04m | txm
    kwm = df["title"].str.lower().str.contains("|".join(CANCER_KW), regex=True, na=False)
    mask = meshm | (~meshm & kwm)
    can = df[mask].copy()
    can["match_type"] = "Title keyword"
    can.loc[txm[mask.values], "match_type"] = "Antineoplastic drug MeSH"
    can.loc[c04m[mask.values], "match_type"] = "MeSH C04 (Neoplasms)"
    can["q3"] = can["quality_class"].map(q3)
    return df, can


def despine(ax, keep=("left", "bottom")):
    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(side in keep)


def fig_pipeline():
    """Figure 1 - data pipeline schematic, drawn to match the other poster figures."""
    from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

    COLW, GAP = 2.45, 0.55
    STAGES = [
        ("DATA SOURCES", BLUES3[0], [
            ("Wikipedia API", "category, talk, info,\nrevision namespaces"),
            ("Wikimedia REST API", "12-month and 3-month\npageview totals"),
            ("Wikimedia Clickstream", "May 2026 referral dataset"),
            ("NLM MeSH 2026", "descriptor file, C04 subtree,\nPharmacologicalAction links"),
        ]),
        ("SIGNAL PIPELINES", "#2171B5", [
            ("Article metadata", "quality class, importance,\nwatchers, length, editors"),
            ("Attention signals", "inbound links, traffic velocity"),
            ("Search intent", "external search vs\ninternal navigation"),
            ("TF-IDF × MeSH", "top 25 terms per lead section"),
            ("MeSH cascade", "seven layers, ordered by\ndata reliability"),
        ]),
        ("SCORING", "#4292C6", [
            ("Impact-Need Score", "0–100: reach 30%, importance 25%,\nquality deficit 25%,\nscarcity 10%, search intent 10%"),
            ("Wiki Attention Score", "0–100: current momentum"),
            ("Medical Relevance", "1–10: TF-IDF × MeSH overlap"),
        ]),
        ("APPLICATION", "#08519C", [
            ("Cancer filter", "MeSH C04 + antineoplastic\nPharmacologicalAction + keyword\n→ 1,859 articles"),
            ("Cancer Dashboard", "Streamlit Community Cloud\nwikimed-dashboard.com"),
            ("Monthly refresh", "GitHub Actions re-fetches\nand recomputes all scores"),
        ]),
    ]

    fig, ax = plt.subplots(figsize=(13.2, 5.6))
    ax.set_xlim(0, len(STAGES) * (COLW + GAP))
    ax.set_ylim(0, 10)
    ax.axis("off")

    for si, (stage, accent, boxes) in enumerate(STAGES):
        x = si * (COLW + GAP)
        ax.text(x + COLW / 2, 9.55, stage, ha="center", va="center",
                fontsize=12, weight="bold", color=accent)
        ax.plot([x + 0.05, x + COLW - 0.05], [9.22, 9.22], color=accent, lw=2.2,
                solid_capstyle="round")

        n = len(boxes)
        top, bottom = 8.85, 0.35
        bh = (top - bottom) / n - 0.3
        for bi, (title, detail) in enumerate(boxes):
            y = top - bi * (bh + 0.3) - bh
            ax.add_patch(FancyBboxPatch(
                (x + 0.05, y), COLW - 0.1, bh,
                boxstyle="round,pad=0.015,rounding_size=0.09",
                facecolor="#F6F8FA", edgecolor=GRID, linewidth=1.0, zorder=2))
            ax.add_patch(FancyBboxPatch(
                (x + 0.05, y), 0.075, bh,
                boxstyle="round,pad=0,rounding_size=0.02",
                facecolor=accent, edgecolor="none", zorder=3))
            ax.text(x + 0.22, y + bh - 0.26, title, ha="left", va="top",
                    fontsize=11.2, weight="bold", color=INK, zorder=4)
            ax.text(x + 0.22, y + bh - 0.55, detail, ha="left", va="top",
                    fontsize=8.9, color=INK_MUTED, linespacing=1.45, zorder=4)

        if si < len(STAGES) - 1:
            ax.add_patch(FancyArrowPatch(
                (x + COLW + 0.06, 4.6), (x + COLW + GAP - 0.06, 4.6),
                arrowstyle="-|>", mutation_scale=17,
                color="#9AA5B1", lw=1.8, zorder=5))

    fig.tight_layout(pad=0.4)
    fig.savefig(f"{OUT}/fig1_pipeline.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print("  fig1_pipeline.png         4 stages")


def fig_identification(can):
    """Composition of the cancer corpus by identification method."""
    counts = can["match_type"].value_counts().reindex(
        ["MeSH C04 (Neoplasms)", "Antineoplastic drug MeSH", "Title keyword"]).fillna(0).astype(int)
    total = int(counts.sum())

    fig, ax = plt.subplots(figsize=(7.2, 2.9))
    ypos = np.arange(len(counts))[::-1]
    for y, (lab, v), col in zip(ypos, counts.items(), BLUES3):
        ax.barh(y, v, height=0.62, color=col, zorder=3)
        ax.text(v + counts.max() * 0.022, y, f"{v:,}  ({v/total*100:.0f}%)",
                va="center", ha="left", fontsize=12.5, color=INK)
    ax.set_yticks(ypos)
    ax.set_yticklabels(counts.index, fontsize=12.5, color=INK)
    # Headroom is set off the longest bar, not the corpus total, so the direct
    # labels have room; otherwise "1,266 (68%)" runs off the right edge.
    ax.set_xlim(0, counts.max() * 1.45)
    ax.set_xlabel("Articles", fontsize=12, color=INK_MUTED)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{int(x):,}"))
    ax.xaxis.grid(True, color=GRID, lw=0.7, zorder=0)
    ax.set_axisbelow(True)
    despine(ax, keep=("bottom",))
    ax.tick_params(axis="y", length=0)
    ax.set_title(f"Cancer-related articles identified (n = {total:,})",
                 fontsize=14, color=INK, pad=10, loc="left", weight="bold")
    fig.tight_layout()
    fig.savefig(f"{OUT}/fig2_identification.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  fig2_identification.png   n={total:,}")


def fig_priority_matrix(can):
    """Quality x importance counts - where the editorial gap sits."""
    h = (can.dropna(subset=["importance_label", "quality_class"])
         .groupby(["importance_label", "quality_class"]).size()
         .unstack(fill_value=0).reindex(index=IORDER, columns=QORDER, fill_value=0))

    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    im = ax.imshow(h.values, cmap="OrRd", aspect="auto")
    ax.set_xticks(range(len(QORDER)), QORDER, fontsize=12.5, color=INK)
    ax.set_yticks(range(len(IORDER)), IORDER, fontsize=12.5, color=INK)
    ax.set_xlabel("Editorial quality class", fontsize=12, color=INK_MUTED, labelpad=8)
    ax.set_ylabel("Clinical importance", fontsize=12, color=INK_MUTED, labelpad=8)
    vmax = h.values.max()
    for i in range(h.shape[0]):
        for j in range(h.shape[1]):
            v = h.values[i, j]
            ax.text(j, i, f"{v:,}", ha="center", va="center", fontsize=12,
                    color=("white" if v > vmax * 0.55 else INK))
    # separate cells with a surface gap
    ax.set_xticks(np.arange(-.5, len(QORDER), 1), minor=True)
    ax.set_yticks(np.arange(-.5, len(IORDER), 1), minor=True)
    ax.grid(which="minor", color=SURFACE, linewidth=2)
    ax.tick_params(which="minor", length=0)
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_title("Priority matrix: cancer articles by quality and importance",
                 fontsize=14, color=INK, pad=10, loc="left", weight="bold")
    fig.tight_layout()
    fig.savefig(f"{OUT}/fig3_priority_matrix.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  fig3_priority_matrix.png  max cell={vmax:,}")


def fig_scatter(can):
    """Impact-Need against current attention, identity = collapsed quality."""
    s = can.dropna(subset=["wiki_attention_score", "impact_need_score", "q3"])
    fig, ax = plt.subplots(figsize=(7.2, 5.4))
    ax.axvline(50, color="#AAAAAA", ls=(0, (2, 3)), lw=1.2, zorder=1)
    ax.axhline(50, color="#AAAAAA", ls=(0, (2, 3)), lw=1.2, zorder=1)
    for lab in ["GA / FA", "C / B", "Stub / Start"]:
        sub = s[s["q3"] == lab]
        ax.scatter(sub["wiki_attention_score"], sub["impact_need_score"],
                   s=26, c=Q3[lab], label=f"{lab}  (n={len(sub):,})",
                   alpha=0.72, linewidths=0.6, edgecolors=SURFACE, zorder=3)
    ax.set_xlim(0, 100); ax.set_ylim(0, 100)
    ax.set_xlabel("Wiki Attention Score (0–100)", fontsize=12.5, color=INK_MUTED)
    ax.set_ylabel("Impact-Need Score (0–100)", fontsize=12.5, color=INK_MUTED)
    ax.grid(True, color=GRID, lw=0.7, zorder=0)
    ax.set_axisbelow(True)
    despine(ax)
    ax.text(98, 97, "high reach, large gap", ha="right", va="top",
            fontsize=11.5, color=INK_MUTED, style="italic")
    leg = ax.legend(loc="lower left", frameon=True, fontsize=11.5,
                    framealpha=0.95, edgecolor=GRID, title="Quality class")
    leg.get_title().set_fontsize(11.5)
    leg.get_title().set_color(INK_MUTED)
    ax.set_title("Editorial need against current readership",
                 fontsize=14, color=INK, pad=10, loc="left", weight="bold")
    fig.tight_layout()
    fig.savefig(f"{OUT}/fig4_impact_vs_attention.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  fig4_impact_vs_attention.png  n={len(s):,}")


def fig_readability(can):
    """Reading-grade distribution against comprehension benchmarks."""
    rl = can["reading_level"].dropna()
    rl = rl[(rl >= 0) & (rl <= 30)]
    fig, ax = plt.subplots(figsize=(7.2, 3.9))
    ax.hist(rl, bins=np.arange(0, 31, 1), color=SEQ_HUE, alpha=0.9, zorder=3)
    # Stagger the two reference labels; at grade 8 vs 12 they collide otherwise.
    ymax = ax.get_ylim()[1]
    for g, lab, col, ha, dx, yfrac in [
        (8, "avg US adult\n(grade 8)", "#B2182B", "right", -0.4, 0.97),
        (12, "high school graduate\n(grade 12)", INK_MUTED, "left", 0.4, 0.70),
    ]:
        ax.axvline(g, color=col, ls="--", lw=1.6, zorder=4)
        ax.text(g + dx, ymax * yfrac, lab, fontsize=11,
                color=col, va="top", ha=ha, linespacing=1.35)
    pct = (rl > 12).mean() * 100
    ax.set_xlabel("Flesch-Kincaid grade level", fontsize=12.5, color=INK_MUTED)
    ax.set_ylabel("Articles", fontsize=12.5, color=INK_MUTED)
    ax.yaxis.grid(True, color=GRID, lw=0.7, zorder=0)
    ax.set_axisbelow(True)
    despine(ax)
    ax.set_xlim(0, 30)
    ax.set_title(f"Readability: {pct:.0f}% of cancer articles exceed grade 12",
                 fontsize=14, color=INK, pad=10, loc="left", weight="bold")
    fig.tight_layout()
    fig.savefig(f"{OUT}/fig5_readability.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  fig5_readability.png   median={rl.median():.1f}  >grade12={pct:.1f}%")


def table_top(can):
    """Showcase table, restricted to High/Top importance so it reads as oncology."""
    hi = can[can["importance_label"].isin(["High", "Top"])]
    t = hi.nlargest(10, "impact_need_score")[
        ["title", "quality_class", "importance_label", "impact_need_score",
         "pageviews_12mo", "reading_level"]].copy()
    t["impact_need_score"] = t["impact_need_score"].round(1)
    t["pageviews_12mo"] = t["pageviews_12mo"].map(lambda v: f"{int(v):,}")
    t["reading_level"] = t["reading_level"].round(1)
    t.columns = ["Article", "Quality", "Importance", "Impact-Need",
                 "Pageviews (12 mo)", "FK grade"]
    t.to_csv(f"{OUT}/table1_top_articles.csv", index=False)
    print("\n  table1_top_articles.csv")
    print(t.to_string(index=False))


def main():
    df, can = load()
    print(f"Corpus {len(df):,} | cancer subset {len(can):,}\n")
    fig_pipeline()
    fig_identification(can)
    fig_priority_matrix(can)
    fig_scatter(can)
    fig_readability(can)
    table_top(can)
    print(f"\nWrote figures to {OUT}/")


if __name__ == "__main__":
    main()
