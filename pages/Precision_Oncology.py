"""
WikiMed Precision Oncology Article Recommender
Filters the WikiProject Medicine corpus to precision oncology content — tumor
biomarkers, targeted and immunological antineoplastic agents, biomarker-directed
endocrine therapy, molecular diagnostics, and hereditary cancer predisposition.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import re
import os

st.markdown("""
    <style>
    section[data-testid="stSidebar"] > div:first-child { padding-top: 0.5rem !important; }
    [data-testid="stSidebarCollapseButton"] button { width: 1.4rem !important; height: 1.4rem !important; padding: 0.1rem !important; }
    [data-testid="stSidebarCollapseButton"] svg { width: 0.75rem !important; height: 0.75rem !important; }
    </style>
""", unsafe_allow_html=True)

QUALITY_COLORS = {
    "Stub": "#08306B", "Start": "#08519C", "C": "#2171B5",
    "B": "#6BAED6", "GA": "#9ECAE1", "FA": "#DEEBF7",
}
QUALITY_ORDER = ["Stub", "Start", "C", "B", "GA", "FA"]
QUALITY_SCATTER_COLORS = {
    "Stub": "#B2182B", "Start": "#EF8A62", "C": "#FDBF93",
    "B": "#92C5DE", "GA": "#4393C3", "FA": "#2166AC",
}
IMPORTANCE_COLORS = {
    "Low": "#EDF8E9", "Mid": "#74C476", "High": "#238B45", "Top": "#00441B",
}
PILLAR_COLORS = {
    "Tumor biomarkers & molecular diagnostics": "#6A51A3",
    "Targeted & immunological agents":          "#9E9AC8",
    "Biomarker-directed endocrine therapy":     "#CBC9E2",
    "Precision therapy modalities":             "#807DBA",
    "Hereditary cancer predisposition":         "#54278F",
    "Title keyword (no MeSH)":                  "#BCBDDC",
}
PILLAR_LABELS = {
    "biomarker_diagnostic": "Tumor biomarkers & molecular diagnostics",
    "targeted_agent":       "Targeted & immunological agents",
    "endocrine_targeted":   "Biomarker-directed endocrine therapy",
    "precision_therapy":    "Precision therapy modalities",
    "hereditary_risk":      "Hereditary cancer predisposition",
    "title_keyword":        "Title keyword (no MeSH)",
}
_QUALITY_TABLE_STYLES = {
    "Stub":  "background-color:#B2182B; color:white",
    "Start": "background-color:#EF8A62; color:#4D0000",
    "C":     "background-color:#FDBF93; color:#4D0000",
    "B":     "background-color:#92C5DE; color:#003366",
    "GA":    "background-color:#4393C3; color:white",
    "FA":    "background-color:#2166AC; color:white",
}
_IMPORTANCE_TABLE_STYLES = {
    "Top":  "background-color:#005A32; color:white; font-weight:600",
    "High": "background-color:#238B45; color:white",
    "Mid":  "background-color:#74C476; color:#003300",
    "Low":  "background-color:#E5F5E0; color:#005A32",
}
_SCORE_BUCKETS = [
    (98, "#7F2704", "white"), (95, "#D94801", "white"), (90, "#F16913", "white"),
    (75, "#FDAE6B", "#333"),  (50, "#FDD0A2", "#333"),  (0, "#FFF5EB", "#555"),
]
_READING_LEVEL_STYLES = {
    "≤6 Elementary":    "background-color:#D4EDDA; color:#155724",
    "7–8 Middle":       "background-color:#D1ECF1; color:#0C5460",
    "9–12 High School": "background-color:#FFF3CD; color:#856404",
    "13–16 College":    "background-color:#FFE5D0; color:#7D3C00",
    "17+ Graduate":     "background-color:#F8D7DA; color:#721C24",
}

CANCER_KW = [
    "cancer", "carcinoma", "tumor", "tumour", "malignant", "malignancy",
    "leukemia", "leukaemia", "lymphoma", "sarcoma", "melanoma", "neoplasm",
    "oncology", "glioma", "blastoma", "adenoma", "mesothelioma", "myeloma",
    "metastasis", "metastatic",
]
PO_DRUG_STEMS = re.compile(
    r"\b\w{3,}(?:tinib|nib|mab|parib|ciclib|lisib|zomib|degib|rafenib)\b", re.I)
PO_BIOMARKERS = re.compile(
    r"\b(?:brca[12]?|egfr|alk|ros1|kras|nras|braf|her2|erbb2|pd-?l?1|ctla-?4|"
    r"ntrk|pik3ca|idh[12]|flt3|jak2|bcr-?abl|vegf|mtor|parp|tp53|pten|"
    r"msi-?h|tmb|alk-?positive)\b", re.I)
PO_CONCEPTS = [
    "targeted therapy", "targeted therapies", "immunotherapy", "checkpoint inhibitor",
    "car-t", "car t-cell", "chimeric antigen receptor", "tumor marker", "tumour marker",
    "biomarker", "molecular profiling", "genomic profiling", "liquid biopsy",
    "circulating tumor", "circulating tumour", "companion diagnostic",
    "precision medicine", "personalized medicine", "personalised medicine",
    "precision oncology", "pharmacogenom", "pharmacogenetic",
    "next-generation sequencing", "tumor mutational burden", "microsatellite instability",
    "oncogene", "tumor suppressor", "tumour suppressor", "monoclonal antibody",
    "molecular targeted", "tyrosine kinase inhibitor",
]
PEDS_KW = re.compile(
    r"\b(?:pediatric|paediatric|childhood|juvenile|infantile|neuroblastoma|"
    r"wilms|retinoblastoma|medulloblastoma|rhabdomyosarcoma|hepatoblastoma|"
    r"ewing|nephroblastoma|germinoma)\b", re.I)


def _score_style(v):
    if v is None or (isinstance(v, float) and v != v):
        return ""
    for threshold, bg, fg in _SCORE_BUCKETS:
        if v >= threshold:
            return f"background-color:{bg}; color:{fg}"
    return ""

def _quality_table_style(col):
    return [_QUALITY_TABLE_STYLES.get(str(v), "") for v in col]

def _importance_table_style(col):
    return [_IMPORTANCE_TABLE_STYLES.get(str(v), "") for v in col]

def _reading_level_bucket(v):
    if pd.isna(v): return "Too short"
    v = float(v)
    if v <= 6:  return "≤6 Elementary"
    if v <= 8:  return "7–8 Middle"
    if v <= 12: return "9–12 High School"
    if v <= 16: return "13–16 College"
    return "17+ Graduate"

def _reading_level_style(col):
    return [_READING_LEVEL_STYLES.get(str(v), "") for v in col]


@st.cache_data
def load_po_df():
    df = pd.read_csv("data/scored_articles.csv")
    df["wiki_url"] = "https://en.wikipedia.org/wiki/" + df["title"]
    df["hemonc_url"] = "https://hemonc.org/wiki/" + df["title"].str.replace(" ", "_", regex=False)
    df["edit_url"] = (
        "https://en.wikipedia.org/w/index.php?title="
        + df["title"].str.replace(" ", "_", regex=False) + "&action=edit"
    )
    df["pageviews_12mo"] = pd.to_numeric(df["pageviews_12mo"], errors="coerce").fillna(0).astype(int)
    df["unique_editors"] = pd.to_numeric(df["unique_editors"], errors="coerce").fillna(0).astype(int)
    df["impact_need_score"] = pd.to_numeric(df["impact_need_score"], errors="coerce")
    for col in ["wiki_attention_score", "reading_level", "medical_relevance"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "is_rare_disease" in df.columns:
        df["is_rare_disease"] = (
            df["is_rare_disease"].astype(str).str.lower()
            .map({"true": True, "false": False, "1": True, "0": False}).fillna(False)
        )
        df["rare_icon"] = df["is_rare_disease"].map({True: "🦓", False: ""})

    # Cancer mask (shared with the Cancer Dashboard)
    c04, tx = set(), set()
    if os.path.exists("data/cancer_mesh_ids.csv"):
        c04 = set(pd.read_csv("data/cancer_mesh_ids.csv")["mesh_id"].dropna())
    if os.path.exists("data/cancer_treatment_mesh_ids.csv"):
        tx = set(pd.read_csv("data/cancer_treatment_mesh_ids.csv")["mesh_id"].astype(str))
    mesh = df["mesh_id"].astype(str)
    cancer_mesh = mesh.isin(c04) | mesh.isin(tx)
    cancer_kw = df["title"].str.lower().str.contains("|".join(CANCER_KW), regex=True, na=False)
    is_cancer = cancer_mesh | (~cancer_mesh & cancer_kw)

    # Precision oncology mask
    po_ids = pd.read_csv("data/precision_oncology_mesh_ids.csv")
    pillar_map = dict(zip(po_ids["mesh_id"].astype(str), po_ids["pillar"].astype(str)))
    onc_ids  = set(po_ids.loc[po_ids["scope"] == "oncologic", "mesh_id"].astype(str))
    cond_ids = set(po_ids.loc[po_ids["scope"] == "conditional", "mesh_id"].astype(str))
    # Generic molecular-methods descriptors (Genomics, Genetic Testing,
    # Pharmacogenetics) count only when the article is itself cancer-related.
    mesh_hit = mesh.isin(onc_ids) | (mesh.isin(cond_ids) & is_cancer)

    title_lower = df["title"].str.lower().fillna("")
    kw_raw = (
        df["title"].str.contains(PO_DRUG_STEMS, na=False)
        | df["title"].str.contains(PO_BIOMARKERS, na=False)
        | title_lower.apply(lambda s: any(k in s for k in PO_CONCEPTS))
    )
    # Gated on cancer-relatedness: the -mab / -nib stems otherwise sweep in every
    # monoclonal and kinase inhibitor regardless of indication.
    kw_hit = kw_raw & is_cancer & ~mesh_hit

    df["is_po"] = mesh_hit | kw_hit
    # Drop biographies: the MeSH pipeline matches titles against descriptor names,
    # so surnames collide with eponymous syndromes (seven people surnamed Li were
    # assigned Li-Fraumeni Syndrome). Run fetch_is_biography.py to populate.
    if "is_biography" in df.columns:
        df["is_po"] &= ~df["is_biography"].fillna(False).astype(bool)
    pillar = mesh.map(pillar_map)
    df["po_pillar"] = pillar.where(mesh_hit, other=np.where(kw_hit, "title_keyword", None))
    df["pillar_label"] = df["po_pillar"].map(PILLAR_LABELS)
    df["is_peds"] = (df["title"].str.contains(PEDS_KW, na=False)) & is_cancer

    n_total, n_cancer = len(df), int(is_cancer.sum())
    return df[df["is_po"]].copy(), n_total, n_cancer


if not os.path.exists("data/scored_articles.csv"):
    st.error("scored_articles.csv not found. Run the pipeline first.")
    st.stop()
if not os.path.exists("data/precision_oncology_mesh_ids.csv"):
    st.error("precision_oncology_mesh_ids.csv not found. Run `python build_precision_oncology_ids.py` first.")
    st.stop()

df, n_total, n_cancer = load_po_df()
has_attention = "wiki_attention_score" in df.columns
has_equity    = "reading_level" in df.columns

n_po         = len(df)
n_stub_start = int(df["quality_class"].isin(["Stub", "Start"]).sum())
pct_low      = n_stub_start / n_po * 100 if n_po else 0
_rl          = df["reading_level"].dropna()
pct_above12  = (_rl > 12).mean() * 100 if len(_rl) else 0
n_fa_ga      = int(df["quality_class"].isin(["FA", "GA"]).sum())

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
    <h1 style="font-size:2.6rem;font-weight:800;margin-top:-1rem;margin-bottom:0.15rem;line-height:1.1;">
        🧬 Precision Oncology Article Recommender
    </h1>
    <p style="font-size:1.05rem;color:#444;margin-bottom:1.2rem;">
        Wikipedia is a primary free source of cancer information worldwide, reaching patients and
        clinicians who lack access to subscription resources or academic cancer centres. This view
        isolates the <strong>precision oncology</strong> corpus — tumour biomarkers, targeted and
        immunological antineoplastic agents, biomarker-directed endocrine therapy, molecular
        diagnostics, and hereditary cancer predisposition syndromes — and ranks it by the gap between
        public demand and article quality.
    </p>
""", unsafe_allow_html=True)

# ── Metric cards ──────────────────────────────────────────────────────────────
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric(
    "Precision oncology articles", f"{n_po:,}",
    help=f"Identified from {n_cancer:,} cancer-related articles within {n_total:,} WikiProject "
         "Medicine articles, using NLM MeSH tree membership and PharmacologicalAction links.",
)
m2.metric(
    "Stub or Start quality", f"{n_stub_start:,} ({pct_low:.0f}%)",
    help="The two lowest Wikipedia editorial tiers — minimal or developing content.",
)
m3.metric(
    "Median Impact-Need Score",
    f"{df['impact_need_score'].median():.1f} / 100" if n_po else "—",
    help="Weighted composite of pageviews, importance, quality deficit, editor scarcity and search intent.",
)
m4.metric(
    "Median reading level",
    f"Grade {_rl.median():.1f}" if len(_rl) else "—",
    help="Flesch-Kincaid Grade Level from the article lead section. The average U.S. adult reads at "
         "approximately 8th-grade level, so a median above grade 12 indicates a substantial "
         "accessibility barrier.",
)
m5.metric(
    "Annual pageviews", f"{df['pageviews_12mo'].sum():,}",
    help="Total views across the precision oncology subset over the past 12 months.",
)

# ── The equity headline ───────────────────────────────────────────────────────
st.info(
    f"**{pct_above12:.0f}%** of precision oncology articles are written above a 12th-grade reading "
    f"level, and **{n_fa_ga}** of {n_po:,} have reached Good or Featured Article status. "
    "The molecular concepts that increasingly drive treatment selection are among the least "
    "accessible cancer content on Wikipedia."
)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")
    if st.button("Refresh data"):
        st.cache_data.clear()
        st.rerun()

    all_pillars = [PILLAR_LABELS[p] for p in
                   ["biomarker_diagnostic", "targeted_agent", "endocrine_targeted",
                    "precision_therapy", "hereditary_risk", "title_keyword"]
                   if p in set(df["po_pillar"].dropna())]
    sel_pillar = st.multiselect(
        "Precision oncology domain", all_pillars, default=[],
        help="Which pillar of precision oncology the article belongs to. Leave blank to show all.",
    )
    sel_q = st.multiselect(
        "Quality class", [q for q in QUALITY_ORDER if q in df["quality_class"].unique()], default=[],
        help="Wikipedia's editorial rating: Stub → Start → C → B → GA → FA.",
    )
    sel_imp = st.multiselect(
        "Importance", [i for i in ["Top", "High", "Mid", "Low"]
                       if i in df["importance_label"].dropna().unique()], default=[],
        help="WikiProject Medicine's clinical significance rating.",
    )

    st.divider()
    st.subheader("Equity Filters")
    sel_rare = st.checkbox("Rare cancers only", value=False,
                           help="Articles flagged as rare diseases — conditions affecting fewer than 1 in 2,000 people.")
    sel_peds = st.checkbox("Paediatric cancers only", value=False,
                           help="Articles covering paediatric malignancies, identified by title and MeSH descriptor.")
    if has_equity and df["reading_level"].notna().any():
        max_rl = int(df["reading_level"].dropna().max()) + 1
        sel_reading = st.slider(
            "Max reading level (FK grade)", 1, max_rl, max_rl,
            help="Flesch-Kincaid Grade Level: 8 ≈ average U.S. adult, 12 ≈ high school graduate, "
                 "16 ≈ college graduate. Slide left to isolate the articles a general audience can read.",
        )
    else:
        sel_reading = None

    top_n = st.slider("Show top N articles", 10, 500, 100, 10)

    st.divider()
    st.caption(f"**{n_po:,}** precision oncology articles")
    for p_key, p_lab in PILLAR_LABELS.items():
        c = int((df["po_pillar"] == p_key).sum())
        if c:
            st.caption(f"**{c:,}** {p_lab.lower()}")
    st.divider()
    st.page_link("pages/Cancer_Dashboard.py", label="← Full Cancer Dashboard")
    st.page_link("pages/Home.py", label="← Full WikiMed Dashboard")

# ── Apply filters ─────────────────────────────────────────────────────────────
filtered = df.copy()
if sel_pillar:
    filtered = filtered[filtered["pillar_label"].isin(sel_pillar)]
if sel_q:
    filtered = filtered[filtered["quality_class"].isin(sel_q)]
if sel_imp:
    filtered = filtered[filtered["importance_label"].isin(sel_imp)]
if sel_rare and "is_rare_disease" in filtered.columns:
    filtered = filtered[filtered["is_rare_disease"].astype(bool)]
if sel_peds:
    filtered = filtered[filtered["is_peds"].astype(bool)]
if sel_reading is not None and "reading_level" in filtered.columns:
    filtered = filtered[filtered["reading_level"].isna() | (filtered["reading_level"] <= sel_reading)]
if "is_fully_protected" in filtered.columns:
    n_excl = int(filtered["is_fully_protected"].astype(bool).sum())
    filtered = filtered[~filtered["is_fully_protected"].astype(bool)]
    if n_excl:
        st.sidebar.caption(f"🔒 {n_excl:,} fully protected article{'s' if n_excl != 1 else ''} hidden")

filtered = filtered.head(top_n).copy()
n = len(filtered)

st.divider()

# ── Article table ─────────────────────────────────────────────────────────────
if n == 0:
    st.warning("No articles match the current filters.")
else:
    st.subheader(f"Top {n} Precision Oncology Articles by Impact-Need Score")
    st.caption(
        "Ranked by the gap between public reach and current article quality — the articles where "
        "editorial effort would reach the most readers."
    )

    if "is_semi_protected" in filtered.columns:
        filtered["protection"] = filtered["is_semi_protected"].astype(bool).map({True: "🔒 Semi", False: ""})

    cols = ["rank", "wiki_url", "hemonc_url", "impact_need_score"]
    if has_attention:
        cols.append("wiki_attention_score")
    cols += ["quality_class", "importance_label", "pageviews_12mo", "unique_editors"]
    if "reading_level" in filtered.columns:
        cols.append("reading_level")
    cols.append("pillar_label")
    for opt in ["mesh_id", "mesh_preferred_name", "rare_icon", "protection"]:
        if opt in filtered.columns:
            cols.append(opt)
    cols.append("edit_url")

    table_df = filtered[[c for c in cols if c in filtered.columns]].copy()

    impact_gmap    = table_df["impact_need_score"].to_numpy() if "impact_need_score" in table_df else None
    attention_gmap = table_df["wiki_attention_score"].to_numpy() if "wiki_attention_score" in table_df else None
    pageviews_gmap = pd.to_numeric(table_df["pageviews_12mo"], errors="coerce").to_numpy() if "pageviews_12mo" in table_df else None
    editors_gmap   = pd.to_numeric(table_df["unique_editors"], errors="coerce").to_numpy() if "unique_editors" in table_df else None

    for c, f in [("impact_need_score", "{:.2f}"), ("wiki_attention_score", "{:.2f}"),
                 ("pageviews_12mo", "{:,.0f}"), ("unique_editors", "{:.0f}")]:
        if c in table_df.columns:
            table_df[c] = table_df[c].map(lambda x, f=f: f.format(x) if pd.notna(x) else "")
    if "reading_level" in table_df.columns:
        table_df["reading_level"] = table_df["reading_level"].map(_reading_level_bucket)

    styler = table_df.style
    if impact_gmap is not None:
        styler = styler.apply(lambda col, a=impact_gmap: [_score_style(v) for v in a],
                              subset=["impact_need_score"])
    if attention_gmap is not None:
        styler = styler.background_gradient(subset=["wiki_attention_score"], cmap="PuBu",
                                            vmin=0, vmax=100, gmap=attention_gmap)
    if "quality_class" in table_df.columns:
        styler = styler.apply(_quality_table_style, subset=["quality_class"])
    if "importance_label" in table_df.columns:
        styler = styler.apply(_importance_table_style, subset=["importance_label"])
    if pageviews_gmap is not None:
        styler = styler.background_gradient(subset=["pageviews_12mo"], cmap="Blues", gmap=pageviews_gmap)
    if editors_gmap is not None:
        styler = styler.background_gradient(subset=["unique_editors"], cmap="Greens", gmap=editors_gmap)
    if "reading_level" in table_df.columns:
        styler = styler.apply(_reading_level_style, subset=["reading_level"])

    st.dataframe(styler, hide_index=True, height=480, width="stretch", column_config={
        "rank":               st.column_config.NumberColumn("Rank", width="small",
            help="Position when the full WikiProject Medicine corpus is ranked by Impact-Need Score."),
        "wiki_url":           st.column_config.LinkColumn("Article", display_text=r"wiki/(.+)", width="large",
            help="Title of the Wikipedia article. Click to open and read it."),
        "hemonc_url":         st.column_config.LinkColumn("HemOnc.org", display_text="↗", width="small",
            help="Open this topic on HemOnc.org. Best coverage for drugs and regimens. Requires a free account."),
        "impact_need_score":  st.column_config.TextColumn("Impact-Need Score (0-100)", width="medium",
            help="Weighted composite of pageviews (30%), importance (25%), quality deficit (25%), editor scarcity (10%), and search intent (10%)."),
        "wiki_attention_score": st.column_config.TextColumn("Attention Score (0-100)", width="medium",
            help="Current public momentum: pageviews, traffic velocity, inbound links, watchers, active editors."),
        "quality_class":      st.column_config.TextColumn("Quality", width="small",
            help="Wikipedia editorial rating: Stub → Start → C → B → GA → FA."),
        "importance_label":   st.column_config.TextColumn("Importance", width="small",
            help="WikiProject Medicine clinical significance rating: Low → Mid → High → Top."),
        "pageviews_12mo":     st.column_config.TextColumn("Pageviews (12mo)", width="medium",
            help="Total views over the past 12 months, from the Wikimedia pageview API."),
        "unique_editors":     st.column_config.TextColumn("Editors", width="small",
            help="Unique registered editors who edited this article in the past 12 months."),
        "reading_level":      st.column_config.TextColumn("Reading Level", width="medium",
            help="Flesch-Kincaid Grade Level from the lead section. Average U.S. adult reads at ~8th grade."),
        "pillar_label":       st.column_config.TextColumn("PO Domain", width="medium",
            help="Which pillar of precision oncology this article belongs to, assigned from its MeSH descriptor."),
        "mesh_id":            st.column_config.TextColumn("MeSH ID", width="small",
            help="NLM Medical Subject Headings descriptor ID."),
        "mesh_preferred_name": st.column_config.TextColumn("MeSH Term", width="medium"),
        "rare_icon":          st.column_config.TextColumn("Rare", width="small",
            help="🦓 = rare disease, affecting fewer than 1 in 2,000 people."),
        "protection":         st.column_config.TextColumn("Protection", width="small",
            help="🔒 Semi = requires an autoconfirmed account. Fully protected articles are excluded."),
        "edit_url":           st.column_config.LinkColumn("Edit", width="small"),
    })

    st.download_button(
        "Download precision oncology articles as CSV",
        data=filtered.drop(columns=["edit_url"], errors="ignore").to_csv(index=False).encode(),
        file_name="wikimed_precision_oncology.csv", mime="text/csv",
    )

# ── Charts ────────────────────────────────────────────────────────────────────
st.divider()
tab_equity, tab_domains, tab_quality, tab_attention = st.tabs([
    "🌍 Access & Equity", "🧬 PO Domains", "📊 Quality Gap", "⚡ Attention",
])

with tab_equity:
    st.markdown(
        "Precision oncology content is read heavily but written at a level most readers cannot follow. "
        "Points in the **upper right** are the sharpest equity gaps: heavily read articles that require "
        "a college or graduate reading level. The average U.S. adult reads at approximately 8th grade."
    )
    if has_equity:
        p = df[df["reading_level"].notna() & (df["pageviews_12mo"] > 0)].copy()
        p["pv_log"] = np.log10(p["pageviews_12mo"] + 1)
        fig = px.scatter(
            p, x="reading_level", y="pv_log", color="quality_class",
            color_discrete_map=QUALITY_SCATTER_COLORS,
            category_orders={"quality_class": QUALITY_ORDER[::-1]},
            labels={"reading_level": "Flesch-Kincaid Grade Level",
                    "pv_log": "Annual pageviews (log₁₀)", "quality_class": "Quality"},
            hover_name="title", custom_data=["title", "pageviews_12mo", "pillar_label"], opacity=0.75,
        )
        fig.update_traces(marker=dict(size=9), hovertemplate=(
            "<b>%{customdata[0]}</b><br>%{customdata[2]}<br>"
            "Grade level: %{x:.1f}<br>Pageviews: %{customdata[1]:,}<extra></extra>"))
        for g, lab, col, yp in [(8, "avg US adult", "#B2182B", 0.98),
                                (12, "high school grad", "#666666", 0.86),
                                (16, "college grad", "#2166AC", 0.74)]:
            fig.add_vline(x=g, line_dash="dash", line_color=col, line_width=1.5)
            fig.add_annotation(x=g, y=yp, yref="paper", text=lab, showarrow=False,
                               xanchor="left", yanchor="top", font=dict(size=10, color=col),
                               bgcolor="rgba(255,255,255,0.85)", borderpad=2)
        fig.update_layout(margin=dict(t=10, b=40), plot_bgcolor="#F0F0F0",
                          xaxis=dict(gridcolor="#E0E0E0"), yaxis=dict(gridcolor="#E0E0E0"))
        st.plotly_chart(fig, width='stretch')

        eq1, eq2 = st.columns(2)
        with eq1:
            st.subheader("Reading level distribution")
            bands = pd.DataFrame({
                "Band": ["≤8 (avg US adult)", "9–12 (high school)", "13–16 (college)", "17+ (graduate)"],
                "Articles": [
                    int((_rl <= 8).sum()),
                    int(((_rl > 8) & (_rl <= 12)).sum()),
                    int(((_rl > 12) & (_rl <= 16)).sum()),
                    int((_rl > 16).sum()),
                ],
            })
            figb = px.bar(bands, x="Band", y="Articles", color="Band",
                          color_discrete_sequence=["#D4EDDA", "#FFF3CD", "#FFE5D0", "#F8D7DA"])
            figb.update_layout(margin=dict(t=10, b=40), showlegend=False,
                               plot_bgcolor="#F0F0F0", yaxis=dict(gridcolor="#E0E0E0"))
            st.plotly_chart(figb, width='stretch')
            st.caption(f"Only {int((_rl <= 8).sum())} of {len(_rl)} articles are readable by the average U.S. adult.")
        with eq2:
            st.subheader("Rare and paediatric subsets")
            sub = pd.DataFrame({
                "Subset": ["All PO", "Rare cancers", "Paediatric cancers"],
                "Median FK grade": [
                    _rl.median(),
                    df[df["is_rare_disease"].astype(bool)]["reading_level"].median() if "is_rare_disease" in df else np.nan,
                    df[df["is_peds"].astype(bool)]["reading_level"].median(),
                ],
            })
            figs = px.bar(sub, x="Subset", y="Median FK grade", color="Subset",
                          color_discrete_sequence=["#6A51A3", "#9E9AC8", "#CBC9E2"])
            figs.add_hline(y=8, line_dash="dash", line_color="#B2182B", line_width=1.5)
            figs.add_annotation(y=8, x=0.5, yref="y", text="avg US adult (grade 8)", showarrow=False,
                                yanchor="bottom", font=dict(size=10, color="#B2182B"))
            figs.update_layout(margin=dict(t=10, b=40), showlegend=False,
                               plot_bgcolor="#F0F0F0", yaxis=dict(gridcolor="#E0E0E0"))
            st.plotly_chart(figs, width='stretch')
            st.caption("Populations named in the WIN needs assessment as having the least access to precision oncology.")
    else:
        st.info("Reading level data not available. Run `enrich_public_health.py`.")

with tab_domains:
    st.markdown(
        "How the precision oncology corpus divides across its constituent domains, and how article "
        "quality varies between them."
    )
    d1, d2 = st.columns(2)
    with d1:
        st.subheader("Articles by domain")
        pc = df["pillar_label"].value_counts().reset_index()
        pc.columns = ["Domain", "Articles"]
        figp = px.bar(pc, x="Articles", y="Domain", orientation="h",
                      color="Domain", color_discrete_map=PILLAR_COLORS)
        figp.update_layout(margin=dict(t=10, b=40), showlegend=False, plot_bgcolor="#F0F0F0",
                           xaxis=dict(gridcolor="#E0E0E0"), yaxis=dict(title=""))
        st.plotly_chart(figp, width='stretch')
    with d2:
        st.subheader("Quality mix by domain")
        cross = (df.groupby(["pillar_label", "quality_class"]).size()
                 .unstack(fill_value=0).reindex(columns=QUALITY_ORDER, fill_value=0))
        cross_pct = cross.div(cross.sum(axis=1), axis=0) * 100
        figq = go.Figure()
        for q in QUALITY_ORDER:
            figq.add_bar(y=cross_pct.index, x=cross_pct[q], name=q,
                         orientation="h", marker_color=QUALITY_SCATTER_COLORS[q])
        figq.update_layout(barmode="stack", margin=dict(t=10, b=40), plot_bgcolor="#F0F0F0",
                           xaxis=dict(title="% of domain", gridcolor="#E0E0E0"), yaxis=dict(title=""),
                           legend=dict(orientation="h", y=-0.2))
        st.plotly_chart(figq, width='stretch')

with tab_quality:
    st.markdown(
        "Distribution of Wikipedia editorial quality ratings across the precision oncology corpus, "
        "alongside the relationship between an article's public reach and its current quality."
    )
    q1, q2 = st.columns(2)
    with q1:
        st.subheader("Quality distribution")
        qc = df["quality_class"].value_counts().reindex(
            [q for q in QUALITY_ORDER if q in df["quality_class"].unique()]).reset_index()
        qc.columns = ["Quality", "Count"]
        figq2 = px.bar(qc, x="Quality", y="Count", color="Quality", color_discrete_map=QUALITY_COLORS)
        figq2.update_layout(margin=dict(t=10, b=40), showlegend=False,
                            plot_bgcolor="#F0F0F0", yaxis=dict(gridcolor="#E0E0E0"))
        st.plotly_chart(figq2, width='stretch')
        st.caption(f"{n_stub_start:,} of {n_po:,} ({pct_low:.0f}%) are Stub or Start. "
                   f"{n_fa_ga} have reached Good or Featured Article status.")
    with q2:
        st.subheader("Pageviews vs quality")
        box = df[df["pageviews_12mo"] > 0].copy()
        box["pv_log"] = np.log10(box["pageviews_12mo"] + 1)
        figbx = px.box(box, x="quality_class", y="pv_log", color="quality_class",
                       category_orders={"quality_class": QUALITY_ORDER},
                       color_discrete_map=QUALITY_SCATTER_COLORS,
                       labels={"quality_class": "Quality", "pv_log": "Annual pageviews (log₁₀)"},
                       points="outliers")
        figbx.update_layout(margin=dict(t=10, b=40), showlegend=False,
                            plot_bgcolor="#F0F0F0", yaxis=dict(gridcolor="#E0E0E0"))
        st.plotly_chart(figbx, width='stretch')
        st.caption("Heavily read articles that remain at Stub or Start quality are the highest-yield targets.")

with tab_attention:
    if has_attention:
        st.markdown(
            "Impact-Need against current public attention. Articles in the **upper right** combine "
            "high present readership with a large quality gap."
        )
        s = df[df["wiki_attention_score"].notna() & df["impact_need_score"].notna()].copy()
        figa = px.scatter(
            s, x="wiki_attention_score", y="impact_need_score", color="quality_class",
            color_discrete_map=QUALITY_SCATTER_COLORS,
            category_orders={"quality_class": QUALITY_ORDER[::-1]},
            labels={"wiki_attention_score": "Attention Score (0–100)",
                    "impact_need_score": "Impact-Need Score (0–100)", "quality_class": "Quality"},
            hover_name="title", custom_data=["title", "pillar_label"], opacity=0.75,
        )
        figa.update_traces(marker=dict(size=9), hovertemplate=(
            "<b>%{customdata[0]}</b><br>%{customdata[1]}<br>"
            "Attention: %{x:.1f}<br>Impact-Need: %{y:.1f}<extra></extra>"))
        figa.add_vline(x=50, line_dash="dot", line_color="#AAAAAA", line_width=1.5)
        figa.add_hline(y=50, line_dash="dot", line_color="#AAAAAA", line_width=1.5)
        for txt, x, y, xa, ya in [("High priority", 99, 98, "right", "top"),
                                  ("Hidden gems", 1, 98, "left", "top"),
                                  ("Well-covered", 99, 2, "right", "bottom"),
                                  ("Low priority", 1, 2, "left", "bottom")]:
            figa.add_annotation(x=x, y=y, text=txt, showarrow=False, xanchor=xa, yanchor=ya,
                                font=dict(size=11, color="#888888"))
        figa.update_layout(margin=dict(t=10, b=40), plot_bgcolor="#F0F0F0",
                           xaxis=dict(range=[0, 100], gridcolor="#E0E0E0", zeroline=False),
                           yaxis=dict(range=[0, 100], gridcolor="#E0E0E0", zeroline=False))
        st.plotly_chart(figa, width='stretch')
    else:
        st.info("Attention Score not available. Run `fetch_attention.py`.")

st.divider()
st.caption(
    "© 2026 Zach Schneider-Lynch, Brown University. "
    "Precision oncology articles identified via NLM MeSH 2026 tree membership and "
    "PharmacologicalAction links, requiring both an antineoplastic action and a molecularly "
    "targeted mechanism. Classical cytotoxic chemotherapy is excluded."
)
