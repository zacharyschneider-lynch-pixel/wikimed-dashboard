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
import time
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



def save(fig, name, attempts=6):
    """Write a figure, retrying through transient OneDrive sync locks."""
    path = f"{OUT}/{name}"
    for i in range(attempts):
        try:
            fig.savefig(path, dpi=300, bbox_inches="tight")
            return
        except OSError:
            if i == attempts - 1:
                raise
            time.sleep(0.75)

REF_W = 7.2   # width most poster figures are drawn at


def fig_title(fig, num, text):
    """Numbered title, flush left, sized relative to the figure's width.

    A fixed point size looks smaller on a wider figure once both are scaled to
    the same column width on the poster, so scale against REF_W instead.
    """
    k = fig.get_size_inches()[0] / REF_W
    fig.text(0.0, 1.015, f"Figure {num}: {text}", ha="left", va="bottom",
             fontsize=14 * k, weight="bold", color=INK)


def fig_mesh_cascade():
    """Figure 1 - the seven-layer MeSH descriptor assignment cascade.

    Drawn as a figure-table rather than a stack of UI cards: hairline rules,
    unfilled rows and small tier swatches read as a journal figure, where heavy
    rounded fills read as a dashboard screenshot. Layer descriptions follow
    pages/Methodology.py, the authoritative account of the deployed pipeline.
    """
    from matplotlib.patches import Rectangle

    # Tier palette validated for CVD: 0 FAIL, worst adjacent separation 14.7.
    TIER = {"Exact": "#08306B", "High": "#2171B5",
            "Medium": "#6BAED6", "Lower": "#C6DBEF"}
    LAYERS = [
        (1, "Wikidata structured data", "Wikidata SPARQL", "Exact",
         "Property P486 (MeSH Descriptor ID); human-curated and verified"),
        (2, "Wikipedia infobox wikitext", "Article wikitext", "Exact",
         "Parse MeshID=, mesh_heading= and mesh= fields from medical infoboxes"),
        (3, "MeSH full synonym matching", "NLM MeSH 2026 XML", "High",
         "Title matched against every entry term across all descriptors"),
        (4, "PubMed citation consensus", "PubMed efetch", "High",
         "MeSH tags from cited papers, weighted major topic 2 points, minor 1"),
        (5, "BioPortal NLP annotator", "NCBO BioPortal", "Medium",
         "Lead paragraph annotated; accepted above 30% token similarity to title"),
        (6, "NCBI MeSH eSearch", "NCBI E-utilities", "Medium",
         "Title queried against the NCBI MeSH index, validated against local XML"),
        (7, "NLM Medical Text Indexer", "NLM MTI", "Lower",
         "Two passes: title alone, then title plus first sentence if uncertain"),
    ]

    W = 14.0
    fig, ax = plt.subplots(figsize=(W, 5.0))
    ax.set_xlim(0, W)
    ax.set_ylim(1.35, 9.0)
    ax.axis("off")

    X_NUM, X_METHOD, X_SRC, X_APPR, X_CONF = 0.30, 0.78, 4.30, 6.50, 12.30

    ax.text(0, 8.72, "Figure 1: MeSH descriptor assignment cascade",
            fontsize=15.5, weight="bold", color=INK, va="top")
    ax.text(0, 8.32,
            "Seven layers applied in order of data reliability. Each layer processes only the "
            "articles the layers above it could not resolve.",
            fontsize=10.3, color=INK_MUTED, va="top")

    # column header
    yh = 7.62
    for x, lab in [(X_NUM, ""), (X_METHOD, "METHOD"), (X_SRC, "SOURCE"),
                   (X_APPR, "APPROACH"), (X_CONF, "CONFIDENCE")]:
        if lab:
            ax.text(x, yh, lab, fontsize=8.6, weight="bold", color=INK_MUTED,
                    va="bottom", ha="left")
    ax.plot([0, W], [yh - 0.12, yh - 0.12], color=INK, lw=1.1,
            solid_capstyle="butt", zorder=3)

    rowh = 0.86
    top = yh - 0.12
    for i, (num, method, source, tier, approach) in enumerate(LAYERS):
        yc = top - i * rowh - rowh / 2
        accent = TIER[tier]

        # cascade spine
        if i < len(LAYERS) - 1:
            ax.plot([X_NUM + 0.09, X_NUM + 0.09], [yc - 0.17, yc - rowh + 0.17],
                    color="#C4CCD4", lw=1.0, zorder=2)
        ax.add_patch(plt.Circle((X_NUM + 0.09, yc), 0.145, facecolor=accent,
                                edgecolor="none", zorder=4))
        ax.text(X_NUM + 0.09, yc, str(num), ha="center", va="center",
                fontsize=9.2, weight="bold", zorder=5,
                color=("white" if tier in ("Exact", "High") else INK))

        ax.text(X_METHOD, yc, method, fontsize=11.4, weight="bold",
                color=INK, va="center", ha="left")
        ax.text(X_SRC, yc, source, fontsize=10.2, color=INK_MUTED,
                va="center", ha="left")
        ax.text(X_APPR, yc, approach, fontsize=10.2, color=INK_MUTED,
                va="center", ha="left")

        ax.add_patch(Rectangle((X_CONF, yc - 0.085), 0.17, 0.17,
                               facecolor=accent, edgecolor="none", zorder=4))
        ax.text(X_CONF + 0.30, yc, tier, fontsize=10.4, color=INK,
                va="center", ha="left")

        ax.plot([0, W], [yc - rowh / 2, yc - rowh / 2],
                color=GRID, lw=0.7, solid_capstyle="butt", zorder=1)

    fig.tight_layout(pad=0.35)
    save(fig, "fig1_mesh_cascade.png")
    plt.close(fig)
    print(f"  fig1_mesh_cascade.png     7 layers, {W}in wide")


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
    fig_title(fig, 2, f"Cancer-related articles identified (n = {total:,})")
    fig.tight_layout()
    save(fig, "fig2_identification.png")
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
    fig_title(fig, 4, "Priority matrix of cancer articles by quality and importance")
    fig.tight_layout()
    save(fig, "fig4_priority_matrix.png")
    plt.close(fig)
    print(f"  fig4_priority_matrix.png  max cell={vmax:,}")


def fig_scatter(can):
    """Impact-Need against current attention, identity = collapsed quality."""
    s = can.dropna(subset=["wiki_attention_score", "impact_need_score", "q3"])
    # Landscape rather than near-square. Both axes are 0-100 but they measure
    # different things, so equal aspect buys nothing and a wider frame spreads
    # the dense 40-80 band enough to read at poster distance.
    FIG_W = 10.2
    K = FIG_W / REF_W          # keeps type matched to the 7.2in figures
    fig, ax = plt.subplots(figsize=(FIG_W, 5.4))
    ax.tick_params(labelsize=11 * K)
    ax.axvline(50, color="#AAAAAA", ls=(0, (2, 3)), lw=1.2, zorder=1)
    ax.axhline(50, color="#AAAAAA", ls=(0, (2, 3)), lw=1.2, zorder=1)
    for lab in ["GA / FA", "C / B", "Stub / Start"]:
        sub = s[s["q3"] == lab]
        ax.scatter(sub["wiki_attention_score"], sub["impact_need_score"],
                   s=26 * K, c=Q3[lab], label=f"{lab}  (n={len(sub):,})",
                   alpha=0.72, linewidths=0.6, edgecolors=SURFACE, zorder=3)
    ax.set_xlim(0, 100); ax.set_ylim(0, 100)
    ax.set_xlabel("Wiki Attention Score (0–100)", fontsize=12.5 * K, color=INK_MUTED)
    ax.set_ylabel("Impact-Need Score (0–100)", fontsize=12.5 * K, color=INK_MUTED)
    ax.grid(True, color=GRID, lw=0.7, zorder=0)
    ax.set_axisbelow(True)
    despine(ax)
    ax.text(98, 97, "high reach, large gap", ha="right", va="top",
            fontsize=11.5 * K, color=INK_MUTED, style="italic")
    leg = ax.legend(loc="lower left", frameon=True, fontsize=11.5 * K,
                    framealpha=0.95, edgecolor=GRID, title="Quality class")
    leg.get_title().set_fontsize(11.5 * K)
    leg.get_title().set_color(INK_MUTED)
    fig_title(fig, 3, "Editorial need against current readership")
    fig.tight_layout()
    save(fig, "fig3_impact_vs_attention.png")
    plt.close(fig)
    print(f"  fig3_impact_vs_attention.png  n={len(s):,}")


def fig_readability(can):
    """Reading-grade distribution against comprehension benchmarks."""
    rl = can["reading_level"].dropna()
    rl = rl[(rl >= 0) & (rl <= 30)]
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    counts, _, _ = ax.hist(rl, bins=np.arange(0, 31, 1), color=SEQ_HUE,
                           alpha=0.9, zorder=3)

    # Reserve headroom above the tallest bar so both reference labels sit on
    # clean surface. Placed over the bars they were grey-on-dark-blue and
    # effectively unreadable; staggering them vertically only moved the problem.
    peak = counts.max()
    ax.set_ylim(0, peak * 1.30)
    label_y = peak * 1.26
    for g, lab, col, ha, dx in [
        (8, "avg US adult\n(grade 8)", "#B2182B", "right", -0.45),
        (12, "high school graduate\n(grade 12)", "#8A4B08", "left", 0.45),
    ]:
        ax.axvline(g, color=col, ls="--", lw=1.6, zorder=4)
        ax.text(g + dx, label_y, lab, fontsize=11,
                color=col, va="top", ha=ha, linespacing=1.35, zorder=6,
                bbox=dict(facecolor=SURFACE, edgecolor="none",
                          boxstyle="round,pad=0.25", alpha=0.92))
    pct = (rl > 12).mean() * 100
    ax.set_xlabel("Flesch-Kincaid grade level", fontsize=12.5, color=INK_MUTED)
    ax.set_ylabel("Articles", fontsize=12.5, color=INK_MUTED)
    ax.yaxis.grid(True, color=GRID, lw=0.7, zorder=0)
    ax.set_axisbelow(True)
    despine(ax)
    ax.set_xlim(0, 30)
    fig_title(fig, 5, f"Reading grade distribution, {pct:.0f}% of cancer articles above grade 12")
    fig.tight_layout()
    save(fig, "fig5_readability.png")
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
    fig_mesh_cascade()
    fig_identification(can)
    fig_scatter(can)
    fig_priority_matrix(can)
    fig_readability(can)
    table_top(can)
    print(f"\nWrote figures to {OUT}/")


if __name__ == "__main__":
    main()
