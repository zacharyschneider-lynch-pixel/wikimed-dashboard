"""
WikiMed Cancer Article Recommender
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import xml.etree.ElementTree as ET
import os
from difflib import get_close_matches

# Promote any pending MeSH ID value before widgets render
if "_cancer_mesh_id_pending" in st.session_state:
    st.session_state["cancer_mesh_id_input"] = st.session_state.pop("_cancer_mesh_id_pending")

st.markdown("""
    <style>
    section[data-testid="stSidebar"] > div:first-child { padding-top: 0.5rem !important; }
    [data-testid="stSidebarCollapseButton"] button { width: 1.4rem !important; height: 1.4rem !important; padding: 0.1rem !important; }
    [data-testid="stSidebarCollapseButton"] svg { width: 0.75rem !important; height: 0.75rem !important; }
    </style>
""", unsafe_allow_html=True)

# ── Constants ─────────────────────────────────────────────────────────────────
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
_EDIT_TYPE_STYLES = {
    "Expand content":    "background-color:#FEE0D2; color:#99000D; font-weight:600",
    "Improve citations": "background-color:#FFF3CD; color:#7A5500",
    "Polish & review":   "background-color:#EDF8E9; color:#1A6B2E",
    "Maintain / Update": "",
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
    (98, "#7F2704", "white"),
    (95, "#D94801", "white"),
    (90, "#F16913", "white"),
    (75, "#FDAE6B", "#333"),
    (50, "#FDD0A2", "#333"),
    ( 0, "#FFF5EB", "#555"),
]
_READING_LEVEL_STYLES = {
    "≤6 Elementary":    "background-color:#D4EDDA; color:#155724",
    "7–8 Middle":       "background-color:#D1ECF1; color:#0C5460",
    "9–12 High School": "background-color:#FFF3CD; color:#856404",
    "13–16 College":    "background-color:#FFE5D0; color:#7D3C00",
    "17+ Graduate":     "background-color:#F8D7DA; color:#721C24",
}
_Q_OPTIONS = {
    "All quadrants": None,
    "High priority": (True, True),
    "Hidden gems":   (False, True),
    "Well-covered":  (True, False),
    "Low priority":  (False, False),
}
_CANCER_KW = [
    "cancer", "carcinoma", "tumor", "tumour", "malignant", "malignancy",
    "leukemia", "leukaemia", "lymphoma", "sarcoma", "melanoma", "neoplasm",
    "oncology", "glioma", "blastoma", "adenoma", "mesothelioma", "myeloma",
    "metastasis", "metastatic",
]


# ── Helpers ───────────────────────────────────────────────────────────────────
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

def _edit_type_style(col):
    return [_EDIT_TYPE_STYLES.get(str(v), "") for v in col]

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


# ── Data loading ──────────────────────────────────────────────────────────────
@st.cache_data
def load_mesh_index(mesh_path="data/desc2026.xml"):
    if not os.path.exists(mesh_path):
        return {}, {}
    root = ET.parse(mesh_path).getroot()
    name_to_ids, id_to_trees = {}, {}
    for desc in root.findall("DescriptorRecord"):
        did   = desc.findtext("DescriptorUI", "")
        dname = desc.findtext("DescriptorName/String", "")
        trees = [tn.text for tn in desc.findall("TreeNumberList/TreeNumber")]
        id_to_trees[did] = trees
        for term in [dname] + [
            c.findtext("ConceptName/String", "")
            for c in desc.findall("ConceptList/Concept")
        ]:
            if term:
                name_to_ids.setdefault(term.lower(), set()).add(did)
    return name_to_ids, id_to_trees


def run_search(query, df, name_to_ids, id_to_trees):
    q = query.strip().lower()
    if not q:
        return None, None
    title_hits = df["title"].str.lower().str.contains(q, regex=False)
    suggestion = None
    if not title_hits.any():
        close = get_close_matches(q, df["title"].str.lower().tolist(), n=1, cutoff=0.75)
        if close:
            suggestion = df[df["title"].str.lower() == close[0]]["title"].iloc[0]
            title_hits = df["title"].str.lower().str.contains(close[0], regex=False)
    seed_ids = {mid for name, ids in name_to_ids.items() if q in name for mid in ids}
    if suggestion and not seed_ids:
        seed_ids = {mid for name, ids in name_to_ids.items() if suggestion.lower() in name for mid in ids}
    prefixes = set()
    for mid in seed_ids:
        for tn in id_to_trees.get(mid, []):
            parts = tn.split(".")
            prefixes.add(".".join(parts[:-1]) if len(parts) > 1 else tn)
    related_ids = {
        mid for mid, trees in id_to_trees.items()
        if any(tn.startswith(p) for tn in trees for p in prefixes)
    }
    mesh_hits = (
        df["mesh_id"].isin(related_ids)
        if "mesh_id" in df.columns
        else pd.Series(False, index=df.index)
    )
    title_df = df[title_hits].copy()
    title_df["found_via"] = "Title match"
    mesh_only = mesh_hits & ~title_hits
    mesh_df = df[mesh_only].copy()
    mesh_df["found_via"] = "MeSH related"
    mesh_df = mesh_df.sort_values("impact_need_score", ascending=False)
    return pd.concat([title_df, mesh_df], ignore_index=True), suggestion


@st.cache_data
def load_all():
    df = pd.read_csv("data/scored_articles.csv")
    df["wiki_url"] = "https://en.wikipedia.org/wiki/" + df["title"]
    df["hemonc_url"] = "https://hemonc.org/wiki/" + df["title"].str.replace(" ", "_", regex=False)
    df["edit_url"] = (
        "https://en.wikipedia.org/w/index.php?title="
        + df["title"].str.replace(" ", "_", regex=False)
        + "&action=edit"
    )
    df["pageviews_12mo"] = pd.to_numeric(df["pageviews_12mo"], errors="coerce").fillna(0).astype(int)
    df["unique_editors"] = pd.to_numeric(df["unique_editors"], errors="coerce").fillna(0).astype(int)
    df["impact_need_score"] = pd.to_numeric(df["impact_need_score"], errors="coerce")
    for col in ["wiki_attention_score", "reading_level", "medical_relevance"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "is_rare_disease" in df.columns:
        df["is_rare_disease"] = df["is_rare_disease"].astype(str).str.lower().map(
            {"true": True, "false": False, "1": True, "0": False}
        ).fillna(False)
        df["rare_icon"] = df["is_rare_disease"].map({True: "🦓", False: ""})
    return df


@st.cache_data
def load_cancer_mesh_ids():
    c04_ids = set()
    treatment_map = {}
    if os.path.exists("data/cancer_mesh_ids.csv"):
        c04_ids = set(pd.read_csv("data/cancer_mesh_ids.csv")["mesh_id"].dropna().tolist())
    if os.path.exists("data/cancer_treatment_mesh_ids.csv"):
        tx = pd.read_csv("data/cancer_treatment_mesh_ids.csv")
        treatment_map = dict(zip(tx["mesh_id"].astype(str), tx["category"].astype(str)))
    return c04_ids, treatment_map


@st.cache_data
def get_cancer_df():
    full_df = load_all()
    c04_ids, treatment_map = load_cancer_mesh_ids()
    mesh_col = full_df["mesh_id"].astype(str) if "mesh_id" in full_df.columns else pd.Series("", index=full_df.index)
    c04_match       = mesh_col.isin(c04_ids)
    treatment_match = mesh_col.isin(treatment_map.keys())
    mesh_match      = c04_match | treatment_match
    kw_match = full_df["title"].str.lower().str.contains("|".join(_CANCER_KW), regex=True, na=False)
    mask = mesh_match | (~mesh_match & kw_match)
    out = full_df[mask].copy()
    out["match_type"] = "Title keyword"
    out.loc[treatment_match[mask.values], "match_type"] = out.loc[
        treatment_match[mask.values], "mesh_id"
    ].astype(str).map(treatment_map).fillna("antineoplastic_drug")
    out.loc[c04_match[mask.values], "match_type"] = "MeSH C04"
    return out, len(full_df)


# ── Guard ─────────────────────────────────────────────────────────────────────
if not os.path.exists("data/scored_articles.csv"):
    st.error("scored_articles.csv not found. Run the pipeline first.")
    st.stop()

df, n_total = get_cancer_df()

has_attention = "wiki_attention_score" in df.columns
has_equity    = "reading_level" in df.columns and "is_rare_disease" in df.columns
has_tfidf     = "medical_relevance" in df.columns

n_cancer     = len(df)
n_stub_start = df["quality_class"].isin(["Stub", "Start"]).sum()
pct_low      = n_stub_start / n_cancer * 100 if n_cancer else 0
n_c04        = (df["match_type"] == "MeSH C04").sum()
n_treatment  = df["match_type"].isin(["antineoplastic_drug", "antineoplastic_protocol"]).sum()
n_hereditary = (df["match_type"] == "hereditary_cancer_syndrome").sum()
n_keyword    = (df["match_type"] == "Title keyword").sum()

name_to_ids, id_to_trees = load_mesh_index()

# ── Session state ─────────────────────────────────────────────────────────────
for _key, _default in [
    ("cancer_heatmap_filter", None),
    ("cancer_rare_filter", None),
    ("cancer_quadrant_sel", "All quadrants"),
]:
    if _key not in st.session_state:
        st.session_state[_key] = _default

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
    <h1 style="font-size:2.6rem;font-weight:800;margin-top:-1rem;margin-bottom:0.15rem;line-height:1.1;">
        🎗️ WikiMed Cancer Article Recommender
    </h1>
    <p style="font-size:1.05rem;color:#444;margin-bottom:1.2rem;">
        Oncology-focused view of WikiProject Medicine — identifying the highest-priority
        cancer Wikipedia articles for WikiMed student editors, ranked by public reach and quality gap.
        Articles matched via NLM MeSH: <strong>C04 Neoplasms</strong> tree (703 descriptors),
        antineoplastic drug PharmacologicalAction links, and hereditary cancer syndromes.
    </p>
""", unsafe_allow_html=True)

# ── Metric cards ──────────────────────────────────────────────────────────────
m1, m2, m3, m4 = st.columns(4)
m1.metric(
    "Cancer-related articles", f"{n_cancer:,}",
    help=(
        f"{n_c04:,} via MeSH C04 (Neoplasms) · "
        f"{n_treatment:,} via antineoplastic drug/protocol MeSH · "
        f"{n_hereditary:,} via hereditary cancer syndrome MeSH · "
        f"{n_keyword:,} via title keyword fallback"
    ),
)
m2.metric(
    "Stub or Start quality", f"{n_stub_start:,}  ({pct_low:.0f}%)",
    help="Articles with the two lowest editorial ratings — minimal or developing content",
)
m3.metric(
    "Avg Impact-Need Score",
    f"{df['impact_need_score'].mean():.1f} / 100" if n_cancer else "—",
)
m4.metric(
    "Avg Attention Score" if has_attention else "Avg pageviews (12 mo)",
    f"{df['wiki_attention_score'].mean():.1f} / 100" if has_attention and n_cancer
    else f"{int(df['pageviews_12mo'].mean()):,}" if n_cancer else "—",
)

# ── Search bar ────────────────────────────────────────────────────────────────
search_query = st.text_input(
    "🔍 Search cancer articles",
    placeholder="e.g. breast cancer, rituximab — searches titles and related MeSH terms",
)
search_results, search_suggestion = run_search(search_query, df, name_to_ids, id_to_trees)
if search_suggestion:
    st.info(f"No exact matches for \"{search_query}\" — showing results for **{search_suggestion}** instead.")

# ── Sidebar filters ───────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")
    if st.button("Refresh data"):
        st.cache_data.clear()
        st.rerun()

    all_q          = [q for q in QUALITY_ORDER if q in df["quality_class"].unique()]
    all_imp        = [i for i in ["Top", "High", "Mid", "Low"] if i in df["importance_label"].dropna().unique()]
    all_edit_types = sorted(df["edit_type"].dropna().unique())
    all_difficulty = sorted(df["difficulty"].dropna().unique()) if "difficulty" in df.columns else []

    sel_q = st.multiselect(
        "Quality class", all_q, default=[],
        help=(
            "Wikipedia's editorial rating for article completeness:\n\n"
            "• **Stub** — very basic, minimal content\n"
            "• **Start** — developing article, major gaps\n"
            "• **C** — substantial but incomplete\n"
            "• **B** — reasonably complete, minor issues\n"
            "• **GA** — Good Article (independently reviewed)\n"
            "• **FA** — Featured Article (Wikipedia's highest standard)"
        ),
    )
    sel_imp = st.multiselect(
        "Importance", all_imp, default=[],
        help=(
            "WikiProject Medicine's rating of clinical significance:\n\n"
            "• **Top** — core medical topic (e.g. Cancer, Diabetes)\n"
            "• **High** — major specialty or disease topic\n"
            "• **Mid** — useful but non-essential\n"
            "• **Low** — niche or peripheral topic"
        ),
    )
    sel_edit = st.multiselect("Edit type needed", all_edit_types, default=[])

    if all_difficulty:
        sel_difficulty = st.multiselect("Article Scope", all_difficulty, default=[])
    else:
        sel_difficulty = []

    if "specialty" in df.columns:
        all_specialties = sorted(
            {s.strip() for cell in df["specialty"].dropna() for s in cell.split("|")}
        )
        sel_specialty = st.multiselect("Specialty", all_specialties, default=[],
                                       help="Leave blank to show all specialties")
    else:
        sel_specialty = []

    sel_match = st.multiselect(
        "Article identification",
        ["MeSH C04", "antineoplastic_drug", "antineoplastic_protocol",
         "hereditary_cancer_syndrome", "Title keyword"],
        default=["MeSH C04", "antineoplastic_drug", "antineoplastic_protocol",
                 "hereditary_cancer_syndrome", "Title keyword"],
        help=(
            "MeSH C04 = NLM Neoplasms tree · "
            "antineoplastic_drug = cancer drugs via MeSH PharmacologicalAction · "
            "hereditary_cancer_syndrome = Li-Fraumeni, Lynch, BRCA-related, etc. · "
            "Title keyword = no MeSH match, keyword fallback"
        ),
    )

    st.divider()
    st.subheader("Medical Relevance")
    if "mesh_id" in df.columns:
        sel_require_mesh = st.checkbox(
            "Require MeSH assignment", value=True,
            help="Only show articles matched to an NLM MeSH descriptor. "
                 "This reliably excludes non-clinical articles (e.g. 'chief medical officer') "
                 "that are not genuine clinical medical topics.",
        )
    else:
        sel_require_mesh = False
    if has_tfidf:
        min_med_rel = st.slider(
            "Min medical relevance score (1–10)", 1, 10, 3,
            help="Filters by how clinically focused an article's content is (1–10). Measures what fraction "
                 "of the article's most distinctive terms match the NLM MeSH medical vocabulary: "
                 "10 = nearly all terms are clinical; 1 = few medical terms. "
                 "The default of 3 removes articles whose top terms are mostly non-clinical.",
        )
    else:
        min_med_rel = 0

    if "mesh_confidence" in df.columns or "mesh_id" in df.columns:
        st.divider()
        st.subheader("MeSH Filters")

    if "mesh_confidence" in df.columns:
        sel_mesh_confidence = st.multiselect(
            "MeSH match confidence",
            ["High", "Medium", "Low", "Broad"],
            default=["High", "Medium"],
            help="High/Medium = reliable matches. Low = indirect. Broad = too general.",
        )
    else:
        sel_mesh_confidence = []

    if "mesh_id" in df.columns:
        sel_mesh_id = st.text_input(
            "Browse by MeSH ID",
            placeholder="e.g. D009369",
            key="cancer_mesh_id_input",
            help="Show all cancer articles assigned this exact MeSH descriptor.",
        )
        if sel_mesh_id.strip():
            if st.button("✕ Clear MeSH ID filter", key="cancer_clear_mesh_id"):
                st.session_state["_cancer_mesh_id_pending"] = ""
                st.rerun()
    else:
        sel_mesh_id = ""

    if has_equity:
        st.divider()
        st.subheader("Health Equity Filters")
        sel_rare = st.checkbox("Rare diseases only", value=False,
                               help="Show only articles flagged as rare diseases from Wikipedia categories")
        max_rl = int(df["reading_level"].dropna().max()) + 1
        sel_reading = st.slider("Max reading level (FK grade)", min_value=1, max_value=max_rl, value=max_rl,
                                help="Flesch-Kincaid Grade Level: 8 ≈ average U.S. adult, 12 ≈ high school graduate, "
                                     "16 ≈ college graduate. Slide left to show only articles at or below a given "
                                     "reading level. Computed from lead sections only.")
    else:
        sel_rare    = False
        sel_reading = None

    top_n = st.slider("Show top N articles", 10, 500, 100, 10)

    st.divider()
    st.caption(f"**{n_cancer:,}** cancer articles")
    st.caption(f"**{n_c04:,}** via MeSH C04 (Neoplasms)")
    st.caption(f"**{n_treatment:,}** via antineoplastic drug MeSH")
    st.caption(f"**{n_hereditary:,}** via hereditary cancer syndrome MeSH")
    st.caption(f"**{n_keyword:,}** via title keyword fallback")
    st.divider()
    st.page_link("pages/Home.py", label="← Full WikiMed Dashboard")

# ── Apply filters ─────────────────────────────────────────────────────────────
filtered = search_results.copy() if search_results is not None else df.copy()

if sel_q:
    filtered = filtered[filtered["quality_class"].isin(sel_q)]
if sel_imp:
    filtered = filtered[filtered["importance_label"].isin(sel_imp)]
if sel_edit:
    filtered = filtered[filtered["edit_type"].isin(sel_edit)]
if sel_difficulty and "difficulty" in filtered.columns:
    filtered = filtered[filtered["difficulty"].isin(sel_difficulty)]
if sel_specialty and "specialty" in filtered.columns:
    filtered = filtered[
        filtered["specialty"].fillna("").apply(lambda s: any(sp in s for sp in sel_specialty))
    ]
if sel_match:
    filtered = filtered[filtered["match_type"].isin(sel_match)]
if sel_require_mesh and "mesh_id" in filtered.columns:
    filtered = filtered[filtered["mesh_id"].notna()]
if has_tfidf and min_med_rel > 1:
    filtered = filtered[filtered["medical_relevance"] >= min_med_rel]
if sel_mesh_confidence and "mesh_confidence" in filtered.columns:
    filtered = filtered[filtered["mesh_confidence"].isin(sel_mesh_confidence)]
if "is_fully_protected" in filtered.columns:
    n_excl = filtered["is_fully_protected"].astype(bool).sum()
    filtered = filtered[~filtered["is_fully_protected"].astype(bool)]
    if n_excl:
        st.sidebar.caption(f"🔒 {n_excl:,} fully protected article{'s' if n_excl != 1 else ''} hidden")
if sel_rare and "is_rare_disease" in filtered.columns:
    filtered = filtered[filtered["is_rare_disease"].astype(bool)]
if sel_reading is not None and "reading_level" in filtered.columns:
    filtered = filtered[
        filtered["reading_level"].isna() | (filtered["reading_level"] <= sel_reading)
    ]

mesh_id_mode = bool(sel_mesh_id.strip()) and "mesh_id" in filtered.columns
if mesh_id_mode:
    filtered = filtered[filtered["mesh_id"].str.upper() == sel_mesh_id.strip().upper()]

_hm = st.session_state.get("cancer_heatmap_filter")
_rd = st.session_state.get("cancer_rare_filter")
bypass_top_n = search_results is not None or mesh_id_mode or bool(_hm) or bool(_rd)
filtered = filtered.copy() if bypass_top_n else filtered.head(top_n).copy()

if _hm:
    hm_quality, hm_importance = _hm
    filtered = filtered[
        (filtered["quality_class"]    == hm_quality) &
        (filtered["importance_label"] == hm_importance)
    ]
if _rd and "is_rare_disease" in filtered.columns:
    filtered = filtered[
        filtered["is_rare_disease"].astype(bool) &
        (filtered["quality_class"] == _rd)
    ]
if (sel_rare or _rd) and "quality_class" in filtered.columns:
    quality_rank = {q: i for i, q in enumerate(QUALITY_ORDER)}
    filtered = filtered.copy()
    filtered["_q_rank"] = filtered["quality_class"].map(quality_rank).fillna(99)
    filtered = filtered.sort_values("_q_rank").drop(columns=["_q_rank"])

_sel_q = _Q_OPTIONS.get(st.session_state.get("cancer_quadrant_sel", "All quadrants"))
if _sel_q is not None and has_attention and "wiki_attention_score" in filtered.columns:
    _high_att, _high_need = _sel_q
    filtered = filtered[
        ((filtered["wiki_attention_score"] >= 50) == _high_att) &
        ((filtered["impact_need_score"]    >= 50) == _high_need)
    ]

n = len(filtered)

# ── Filter banners ────────────────────────────────────────────────────────────
_hm = st.session_state.get("cancer_heatmap_filter")
if _hm:
    hm_q, hm_i = _hm
    n_cell = len(df[(df["quality_class"] == hm_q) & (df["importance_label"] == hm_i)])
    fc1, fc2 = st.columns([8, 1])
    fc1.info(f"📊 **Gap matrix filter:** {hm_i} importance × {hm_q} quality — {n_cell:,} article{'s' if n_cell != 1 else ''} in cancer dataset")
    if fc2.button("✕ Clear", key="cancer_clear_heatmap"):
        st.session_state["cancer_heatmap_filter"] = None
        st.rerun()

_rd = st.session_state.get("cancer_rare_filter")
if _rd:
    n_rare_q = len(df[df["is_rare_disease"].astype(bool) & (df["quality_class"] == _rd)]) if "is_rare_disease" in df.columns else 0
    rc1, rc2 = st.columns([8, 1])
    rc1.info(f"🦓 **Rare disease filter:** {_rd} quality — {n_rare_q:,} rare disease cancer articles in dataset")
    if rc2.button("✕ Clear", key="cancer_clear_rare"):
        st.session_state["cancer_rare_filter"] = None
        st.rerun()

_active_q_label = st.session_state.get("cancer_quadrant_sel", "All quadrants")
if _active_q_label not in ("All quadrants", ""):
    qc1, qc2 = st.columns([8, 1])
    qc1.info(f"⚡ **Quadrant filter:** {_active_q_label}")
    if qc2.button("✕ Clear", key="cancer_clear_quadrant"):
        st.session_state["cancer_quadrant_sel"] = "All quadrants"
        st.rerun()

st.divider()

# ── Article table ─────────────────────────────────────────────────────────────
if n == 0:
    st.warning("No articles match the current filters.")
else:
    st.markdown("""
        <style>
        [data-testid="stPageLink"] a {
            display: flex; align-items: center; justify-content: center;
            font-size: 1.2rem; font-weight: 700; padding: 0.65rem 1.1rem;
            border: 2px solid #1f6fa8; border-radius: 8px; color: #1f6fa8 !important;
            background-color: #f0f6fc; text-decoration: none !important;
            text-align: center; white-space: nowrap;
        }
        [data-testid="stPageLink"] a:hover { background-color: #1f6fa8; color: white !important; }
        </style>
    """, unsafe_allow_html=True)
    left_h, right_h = st.columns([2, 1])
    if mesh_id_mode:
        mid = sel_mesh_id.strip().upper()
        mname = ""
        if "mesh_preferred_name" in filtered.columns and filtered["mesh_preferred_name"].notna().any():
            mname = filtered["mesh_preferred_name"].dropna().iloc[0]
        label = f"{mid} — {mname}" if mname else mid
        left_h.subheader(f"All cancer articles tagged: {label}")
        left_h.caption(f"{n} article{'s' if n != 1 else ''} with this MeSH descriptor")
    elif search_results is not None:
        n_title = (search_results["found_via"] == "Title match").sum()
        n_mesh  = (search_results["found_via"] == "MeSH related").sum()
        left_h.subheader(f"Search results for \"{search_query}\"")
        left_h.caption(f"{n_title} title match{'es' if n_title != 1 else ''} · {n_mesh} related via MeSH")
    else:
        left_h.subheader(f"Top {n} Cancer Articles by Impact-Need Score")
    right_h.page_link("pages/Methodology.py", label="📖 How are scores calculated?", use_container_width=True)

    if "is_semi_protected" in filtered.columns:
        filtered = filtered.copy()
        filtered["protection"] = filtered["is_semi_protected"].astype(bool).map({True: "🔒 Semi", False: ""})

    table_cols = ["rank", "wiki_url", "hemonc_url", "impact_need_score"]
    if has_attention:
        table_cols.append("wiki_attention_score")
    table_cols += ["quality_class", "importance_label", "pageviews_12mo", "unique_editors", "edit_type"]
    if "difficulty" in filtered.columns:
        table_cols.append("difficulty")
    if "specialty" in filtered.columns:
        table_cols.append("specialty")
    if "reading_level" in filtered.columns:
        table_cols.append("reading_level")
    if has_tfidf:
        table_cols.append("medical_relevance")
        table_cols.append("top_tfidf_terms")
    if "mesh_id" in filtered.columns:
        table_cols.append("mesh_id")
    if "mesh_preferred_name" in filtered.columns:
        table_cols.append("mesh_preferred_name")
    if "mesh_confidence" in filtered.columns:
        table_cols.append("mesh_confidence")
    if search_results is not None and "found_via" in filtered.columns:
        wiki_pos = table_cols.index("wiki_url") if "wiki_url" in table_cols else 1
        table_cols.insert(wiki_pos + 1, "found_via")
    if "rare_icon" in filtered.columns:
        table_cols.append("rare_icon")
    if "protection" in filtered.columns:
        table_cols.append("protection")
    table_cols += ["match_type", "edit_url"]

    table_df = filtered[[c for c in table_cols if c in filtered.columns]].copy()

    col_cfg = {
        "rank":               st.column_config.NumberColumn("Rank", width="small",
            help="Position in the ranked list, sorted by Impact-Need Score from highest (1) to lowest."),
        "rare_icon":          st.column_config.TextColumn("Rare Disease", width="small",
            help="🦓 indicates the article covers a rare disease — a condition affecting fewer than 1 in 2,000 people. Categorization is derived from Wikipedia's rare disease article categories."),
        "wiki_url":           st.column_config.LinkColumn("Article", display_text=r"wiki/(.+)", width="large",
            help="Title of the Wikipedia article. Click to open and read it on Wikipedia."),
        "hemonc_url":         st.column_config.LinkColumn(
            "HemOnc.org", display_text="↗", width="small",
            help="Open this topic on HemOnc.org. Best coverage for drugs and regimens — broad disease terms may not have a page. Requires a free HemOnc.org account.",
        ),
        "impact_need_score":  st.column_config.TextColumn(
            "Impact-Need Score (0-100)",
            help="Weighted composite of pageviews (30%), importance (25%), quality deficit (25%), editor scarcity (10%), and search intent (10%). Top article = 100.",
            width="medium",
        ),
        "wiki_attention_score": st.column_config.TextColumn(
            "Attention Score (0-100)",
            help="Measures current momentum: pageviews (45%), traffic velocity (20%), inbound links (20%), watchers (10%), active editors (5%).",
            width="medium",
        ),
        "quality_class":      st.column_config.TextColumn("Quality",
            help="Editorial quality rating: Stub → Start → C → B → GA → FA (Featured Article).",
            width="small"),
        "importance_label":   st.column_config.TextColumn("Importance",
            help="Topic importance: Low → Mid → High → Top.",
            width="small"),
        "pageviews_12mo":     st.column_config.TextColumn("Pageviews (12mo)", width="medium"),
        "unique_editors":     st.column_config.TextColumn("Editors", width="small"),
        "edit_type":          st.column_config.TextColumn("Recommended Action", width="medium",
            help="The primary type of improvement this article is most likely to need, based on its quality class. All types of improvements may benefit any article regardless of quality rating."),
        "difficulty":         st.column_config.TextColumn("Article Scope", width="small",
            help="Estimated scope of available editing work, based on article length and quality class:\n\n• **Focused** — short articles where targeted additions have high impact\n• **Moderate** — developing articles with several areas to improve\n• **Extensive** — longer articles requiring substantive revision across multiple sections"),
        "specialty":          st.column_config.TextColumn("Specialty", width="medium",
            help="Medical specialty assigned based on WikiProject Medicine's tagging system, derived from article categories and WikiProject banners on the article's talk page."),
        "reading_level":      st.column_config.TextColumn("Reading Level", width="medium",
            help="Flesch-Kincaid Grade Level (FKGL) — estimates the U.S. school grade needed to understand the text. Computed from the article's Wikipedia lead section; full article may differ. 'Too short' = lead section under 30 words. Average U.S. adult reads at ~8th grade."),
        "medical_relevance":  st.column_config.TextColumn(
            "Medical Relevance (1-10)",
            help="Estimates how clinically focused the article is (1–10). Calculated by checking how many of the article's most distinctive words match the NLM MeSH medical vocabulary. Scores of 8–10 indicate dense clinical content; scores of 1–3 suggest the top terms are not medically specific.",
            width="medium",
        ),
        "top_tfidf_terms":    st.column_config.TextColumn("Key Terms (TF-IDF)", width="large",
            help="The 25 most distinctive words and phrases in this article compared to all other WikiProject Medicine articles (TF-IDF). These terms reflect what the article is uniquely about and are used to calculate the Medical Relevance score."),
        "mesh_id":            st.column_config.TextColumn("MeSH ID", width="small",
            help="NLM Medical Subject Headings descriptor ID (e.g. D009203). MeSH is the National Library of Medicine's controlled medical vocabulary — having a MeSH ID confirms the article corresponds to a recognized medical concept."),
        "mesh_preferred_name": st.column_config.TextColumn("MeSH Term", width="medium"),
        "mesh_confidence":    st.column_config.TextColumn("MeSH Confidence", width="small"),
        "match_type":         st.column_config.TextColumn("Cancer Match", width="small"),
        "protection":         st.column_config.TextColumn("Protection", width="small",
            help="🔒 Semi = requires autoconfirmed account (≥4 days, ≥10 edits). Fully protected articles are excluded entirely."),
        "edit_url":           st.column_config.LinkColumn("Edit", width="small"),
        "found_via":          st.column_config.TextColumn("Match type", width="medium"),
    }

    impact_gmap    = table_df["impact_need_score"].to_numpy()    if "impact_need_score"    in table_df.columns else None
    attention_gmap = table_df["wiki_attention_score"].to_numpy() if "wiki_attention_score"  in table_df.columns else None
    pageviews_gmap = pd.to_numeric(table_df["pageviews_12mo"],  errors="coerce").to_numpy() if "pageviews_12mo"   in table_df.columns else None
    editors_gmap   = pd.to_numeric(table_df["unique_editors"],  errors="coerce").to_numpy() if "unique_editors"   in table_df.columns else None
    relevance_gmap = pd.to_numeric(table_df["medical_relevance"], errors="coerce").to_numpy() if "medical_relevance" in table_df.columns else None

    if "impact_need_score"    in table_df.columns:
        table_df["impact_need_score"]    = table_df["impact_need_score"].map(lambda x: f"{x:.2f}" if pd.notna(x) else "")
    if "wiki_attention_score" in table_df.columns:
        table_df["wiki_attention_score"] = table_df["wiki_attention_score"].map(lambda x: f"{x:.2f}" if pd.notna(x) else "")
    if "medical_relevance"    in table_df.columns:
        table_df["medical_relevance"]    = table_df["medical_relevance"].map(lambda x: f"{x:.2f}" if pd.notna(x) else "")
    if "pageviews_12mo"       in table_df.columns:
        table_df["pageviews_12mo"]       = table_df["pageviews_12mo"].map(lambda x: f"{x:,.0f}" if pd.notna(x) else "")
    if "unique_editors"       in table_df.columns:
        table_df["unique_editors"]       = table_df["unique_editors"].map(lambda x: f"{x:.0f}" if pd.notna(x) else "")
    if "reading_level"        in table_df.columns:
        table_df["reading_level"]        = table_df["reading_level"].map(_reading_level_bucket)

    styler = table_df.style
    if impact_gmap is not None:
        def _apply_score_buckets(col, arr=impact_gmap):
            return [_score_style(v) for v in arr]
        styler = styler.apply(_apply_score_buckets, subset=["impact_need_score"])
    if attention_gmap is not None:
        styler = styler.background_gradient(subset=["wiki_attention_score"], cmap="PuBu", vmin=0, vmax=100, gmap=attention_gmap)
    if "quality_class" in table_df.columns:
        styler = styler.apply(_quality_table_style, subset=["quality_class"])
    if "importance_label" in table_df.columns:
        styler = styler.apply(_importance_table_style, subset=["importance_label"])
    if pageviews_gmap is not None:
        styler = styler.background_gradient(subset=["pageviews_12mo"], cmap="Blues", gmap=pageviews_gmap)
    if editors_gmap is not None:
        styler = styler.background_gradient(subset=["unique_editors"], cmap="Greens", gmap=editors_gmap)
    if relevance_gmap is not None:
        styler = styler.background_gradient(subset=["medical_relevance"], cmap="YlGn", vmin=0, vmax=10, gmap=relevance_gmap)
    if "edit_type" in table_df.columns:
        styler = styler.apply(_edit_type_style, subset=["edit_type"])
    if "reading_level" in table_df.columns:
        styler = styler.apply(_reading_level_style, subset=["reading_level"])

    st.dataframe(styler, column_config=col_cfg, hide_index=True, height=480, width="stretch")

    csv_bytes = filtered.drop(columns=["edit_url"], errors="ignore").to_csv(index=False).encode()
    st.download_button(
        "Download cancer articles as CSV",
        data=csv_bytes,
        file_name="wikimed_cancer_articles.csv",
        mime="text/csv",
    )

    if "rare_icon" in filtered.columns and (filtered["rare_icon"] == "🦓").any():
        st.caption("🦓 Rare disease article — affects fewer than 1 in 2,000 people")

    # MeSH browse selectbox
    if "mesh_id" in filtered.columns and filtered["mesh_id"].notna().any():
        st.markdown("---")
        unique_ids = (
            filtered.dropna(subset=["mesh_id"])
            [["mesh_id"] + (["mesh_preferred_name"] if "mesh_preferred_name" in filtered.columns else [])]
            .drop_duplicates("mesh_id")
            .sort_values("mesh_id")
        )
        def fmt_option(mid):
            if "mesh_preferred_name" in unique_ids.columns:
                row = unique_ids[unique_ids["mesh_id"] == mid]
                if not row.empty and pd.notna(row["mesh_preferred_name"].iloc[0]):
                    return f"{mid} — {row['mesh_preferred_name'].iloc[0]}"
            return mid

        brow1, brow2 = st.columns([3, 1])
        with brow1:
            picked_id = st.selectbox(
                "Find all cancer articles with the same MeSH ID:",
                options=[""] + unique_ids["mesh_id"].tolist(),
                format_func=lambda x: "Select a MeSH ID from visible articles..." if x == "" else fmt_option(x),
            )
        with brow2:
            st.write("&nbsp;", unsafe_allow_html=True)
            if st.button("Browse all →", disabled=not picked_id, use_container_width=True):
                st.session_state["_cancer_mesh_id_pending"] = picked_id
                st.rerun()

# ── Charts (tabbed) ───────────────────────────────────────────────────────────
st.divider()
tab_attention, tab_overview, tab_matrix, tab_equity = st.tabs([
    "⚡ Attention",
    "📊 Score Overview",
    "🔥 Priority Matrix",
    "🏥 Health Equity",
])

# ── Tab: Attention ────────────────────────────────────────────────────────────
with tab_attention:
    if has_attention:
        st.markdown(
            "Each dot is a cancer-related Wikipedia article. **Color shows quality** — red dots are "
            "Stub/Start articles with the most room to grow; blue dots are already well-developed. "
            "The top-right 'High priority' quadrant — heavily read, poor-quality — is the highest-impact "
            "target for WikiMed student editors."
        )
        _sel_q_label = st.radio(
            "Highlight quadrant", list(_Q_OPTIONS.keys()),
            horizontal=True, key="cancer_quadrant_sel",
        )
        _sel_q = _Q_OPTIONS[_sel_q_label]

        st.subheader("Impact-Need vs. Attention Score — Cancer Articles")
        _scatter_src = df[df["wiki_attention_score"].notna() & df["impact_need_score"].notna()].copy()
        _scatter_plot = _scatter_src.sample(min(3000, len(_scatter_src)), random_state=42).copy()

        if _sel_q is not None:
            _high_att, _high_need = _sel_q
            _in_q = (
                ((_scatter_plot["wiki_attention_score"] >= 50) == _high_att) &
                ((_scatter_plot["impact_need_score"]    >= 50) == _high_need)
            )
            _scatter_plot["_color"] = _scatter_plot["quality_class"].where(_in_q, "_other")
            _cmap = {**QUALITY_SCATTER_COLORS, "_other": "#CCCCCC"}
            _cat  = {"_color": ["FA", "GA", "B", "C", "Start", "Stub", "_other"]}
        else:
            _scatter_plot["_color"] = _scatter_plot["quality_class"]
            _cmap = QUALITY_SCATTER_COLORS
            _cat  = {"_color": ["FA", "GA", "B", "C", "Start", "Stub"]}

        fig_sc = px.scatter(
            _scatter_plot,
            x="wiki_attention_score", y="impact_need_score",
            color="_color", color_discrete_map=_cmap, category_orders=_cat,
            labels={
                "wiki_attention_score": "Attention Score (0–100)",
                "impact_need_score":    "Impact-Need Score (0–100)",
                "_color":              "Quality",
            },
            hover_name="title", custom_data=["title"], opacity=0.6,
        )
        fig_sc.add_vline(x=50, line_dash="dot", line_color="#AAAAAA", line_width=1.5)
        fig_sc.add_hline(y=50, line_dash="dot", line_color="#AAAAAA", line_width=1.5)
        for _txt, _x, _y, _xa, _ya in [
            ("High priority", 99, 98, "right", "top"),
            ("Hidden gems",    1, 98, "left",  "top"),
            ("Well-covered",  99,  2, "right", "bottom"),
            ("Low priority",   1,  2, "left",  "bottom"),
        ]:
            fig_sc.add_annotation(x=_x, y=_y, text=_txt, showarrow=False,
                                  xanchor=_xa, yanchor=_ya,
                                  font=dict(size=11, color="#888888"))
        fig_sc.update_layout(
            margin=dict(t=10, b=40), plot_bgcolor="#F0F0F0",
            clickmode="event+select", dragmode=False,
            xaxis=dict(range=[0, 100], gridcolor="#E0E0E0", zeroline=False),
            yaxis=dict(range=[0, 100], gridcolor="#E0E0E0", zeroline=False),
        )
        _sc_event = st.plotly_chart(fig_sc, on_select="rerun", key="cancer_attention_scatter", use_container_width=True)
        if _sc_event and _sc_event.selection and _sc_event.selection.points:
            _pt = _sc_event.selection.points[0]
            _sel = ((_pt.get("customdata") or [None])[0]) or _pt.get("hovertext")
            if _sel:
                st.link_button(
                    f"Open in Wikipedia: {_sel}",
                    f"https://en.wikipedia.org/wiki/{_sel.replace(' ', '_')}",
                )
        st.page_link("pages/Methodology.py", label="📖 How is the Attention Score calculated?")
    else:
        st.info(
            "**Attention Score not yet available.** "
            "Run `fetch_attention.py` to add real-time pageview velocity, inbound links, "
            "and watcher counts — then this chart will appear automatically."
        )

# ── Tab: Score Overview ───────────────────────────────────────────────────────
with tab_overview:
    st.markdown(
        "**Score Distribution** shows how Impact-Need Scores spread across cancer-related articles. "
        "**Quality Breakdown** shows how many fall into each Wikipedia editorial tier."
    )
    ov1, ov2 = st.columns(2)
    with ov1:
        st.subheader("Score Distribution — Cancer Articles")
        vals = df["impact_need_score"].dropna().values
        if len(vals) > 1:
            bw = 1.06 * vals.std() * len(vals) ** (-0.2)
            samp = vals if len(vals) <= 5000 else np.random.default_rng(42).choice(vals, 5000, replace=False)
            x_grid = np.linspace(0, 100, 400)
            diff = x_grid[:, None] - samp[None, :]
            kde = np.exp(-0.5 * (diff / bw) ** 2).sum(axis=1) / (len(samp) * bw * np.sqrt(2 * np.pi))
            fig_density = go.Figure(go.Scatter(
                x=x_grid, y=kde, mode="lines", fill="tozeroy",
                line=dict(color="#F16913", width=2.5),
                fillcolor="rgba(241,105,19,0.15)",
                hovertemplate="Score %{x:.1f}<extra></extra>",
            ))
            fig_density.update_layout(
                margin=dict(t=10, b=40),
                xaxis_title="Impact-Need Score (0–100)",
                yaxis_title="Density",
                showlegend=False, plot_bgcolor="#F0F0F0",
                xaxis=dict(range=[0, 100], gridcolor="#E0E0E0"),
                yaxis=dict(showticklabels=False, gridcolor="#E0E0E0"),
            )
            st.plotly_chart(fig_density, use_container_width=True)
    with ov2:
        st.subheader("Quality Level Breakdown — Cancer Articles")
        qcounts = (
            df["quality_class"]
            .value_counts()
            .reindex([q for q in QUALITY_ORDER if q in df["quality_class"].unique()])
            .reset_index()
        )
        qcounts.columns = ["Quality", "Count"]
        fig_bar = px.bar(qcounts, x="Quality", y="Count", color="Quality", color_discrete_map=QUALITY_COLORS)
        fig_bar.update_layout(margin=dict(t=10, b=40), showlegend=False, plot_bgcolor="#F0F0F0", yaxis=dict(gridcolor="#E0E0E0"))
        st.plotly_chart(fig_bar, use_container_width=True)
        st.caption(f"{n_stub_start:,} of {n_cancer:,} cancer articles ({pct_low:.0f}%) are Stub or Start.")
    st.page_link("pages/Methodology.py", label="📖 How is the Impact-Need Score calculated?")

# ── Tab: Priority Matrix ──────────────────────────────────────────────────────
with tab_matrix:
    st.markdown(
        "Each cell shows how many **cancer-related articles** sit at that combination of "
        "**importance** and **quality**. "
        "**Top-left cells** (Top/High importance × Stub/Start quality) are the biggest unmet need. "
        "**Click any cell** to filter the article table above."
    )
    imp_order_rev = [i for i in ["Top", "High", "Mid", "Low"] if i in df["importance_label"].dropna().unique()]
    qual_order    = [q for q in QUALITY_ORDER if q in df["quality_class"].unique()]
    heat_df = (
        df.dropna(subset=["importance_label", "quality_class"])
        .groupby(["importance_label", "quality_class"])
        .size()
        .unstack(fill_value=0)
        .reindex(index=imp_order_rev, columns=qual_order, fill_value=0)
    )
    fig_heat = px.imshow(
        heat_df, text_auto=True, color_continuous_scale="OrRd",
        labels=dict(x="Quality Class", y="Importance", color="Articles"),
        aspect="auto",
    )
    _xs, _ys = [], []
    for _col in heat_df.columns:
        for _idx in heat_df.index:
            _xs.append(_col)
            _ys.append(_idx)
    fig_heat.add_trace(go.Scatter(
        x=_xs, y=_ys, mode="markers",
        marker=dict(size=36, opacity=0.001, color="rgba(0,0,0,0)"),
        customdata=list(zip(_xs, _ys)),
        hoverinfo="skip", showlegend=False,
    ))
    fig_heat.update_layout(
        margin=dict(t=10, b=40), coloraxis_showscale=False,
        clickmode="event+select", dragmode=False, plot_bgcolor="#F0F0F0",
    )
    gap_event = st.plotly_chart(fig_heat, on_select="rerun", key="cancer_gap_matrix", use_container_width=True)
    if gap_event and gap_event.selection and gap_event.selection.points:
        pt = gap_event.selection.points[0]
        clicked_q = pt.get("x")
        clicked_imp = pt.get("y")
        if not clicked_q or not clicked_imp:
            cd = pt.get("customdata")
            if cd and len(cd) >= 2:
                clicked_q, clicked_imp = cd[0], cd[1]
        if clicked_q and clicked_imp:
            new_hm = (clicked_q, clicked_imp)
            if st.session_state.get("cancer_heatmap_filter") != new_hm:
                st.session_state["cancer_heatmap_filter"] = new_hm
                st.rerun()
    if st.session_state.get("cancer_heatmap_filter"):
        st.caption("Click a different cell to change the filter · use ✕ Clear above to reset")
    else:
        st.caption("Click any cell to filter the article table to that importance × quality combination.")
    st.page_link("pages/Methodology.py", label="📖 How are importance and quality defined?")

# ── Tab: Health Equity ────────────────────────────────────────────────────────
with tab_equity:
    if has_equity:
        st.markdown(
            "Health equity gaps appear when important cancer information is either "
            "**inaccessible** (written above a typical reader's grade level) or "
            "**absent** (rare disease articles with minimal coverage). "
            "The average US adult reads at an 8th-grade level."
        )
        eq1, eq2 = st.columns(2)
        with eq1:
            st.subheader("Readability vs. Public Reach")
            st.caption("Top-right: heavily read cancer articles written above a college reading level.")
            plot_df = df[df["reading_level"].notna() & (df["pageviews_12mo"] > 0)].copy()
            plot_df["pageviews_log"] = np.log10(plot_df["pageviews_12mo"] + 1)
            plot_df["rl_sqrt"] = np.sqrt(plot_df["reading_level"].clip(lower=0))
            fig_rl = px.scatter(
                plot_df.sample(min(3000, len(plot_df)), random_state=42),
                x="rl_sqrt", y="pageviews_log",
                color="importance_label", color_discrete_map=IMPORTANCE_COLORS,
                category_orders={"importance_label": ["Low", "Mid", "High", "Top"]},
                labels={
                    "rl_sqrt":          "Flesch-Kincaid Grade Level",
                    "pageviews_log":    "Pageviews (log₁₀)",
                    "importance_label": "Importance",
                },
                custom_data=["reading_level", "title"], opacity=0.5,
            )
            fig_rl.update_traces(
                hovertemplate="<b>%{customdata[1]}</b><br>"
                              "Grade level: %{customdata[0]:.1f}<br>"
                              "Pageviews (log): %{y:.2f}<extra></extra>"
            )
            ref_lines = [
                (6,  "6th grade",       "#aaaaaa", 0.99),
                (8,  "avg US adult",    "#666666", 0.82),
                (12, "12th grade (HS)", "#238B45", 0.65),
                (16, "college grad",    "#00441B", 0.48),
            ]
            for grade, label, color, ypos in ref_lines:
                fig_rl.add_vline(x=np.sqrt(grade), line_dash="dash", line_color=color, line_width=1.5)
                fig_rl.add_annotation(
                    x=np.sqrt(grade), y=ypos, yref="paper", text=label, showarrow=False,
                    xanchor="left", yanchor="top", font=dict(size=9, color=color),
                    bgcolor="rgba(255,255,255,0.82)", borderpad=2,
                )
            tick_grades = [4, 6, 8, 10, 12, 16, 20, 28]
            fig_rl.update_layout(
                margin=dict(t=10, b=40), plot_bgcolor="#F0F0F0",
                xaxis=dict(
                    title="Flesch-Kincaid Grade Level (√ scale)",
                    tickvals=[np.sqrt(g) for g in tick_grades],
                    ticktext=[str(g) for g in tick_grades],
                    gridcolor="#E0E0E0",
                ),
                yaxis=dict(gridcolor="#E0E0E0"),
            )
            _rl_event = st.plotly_chart(fig_rl, on_select="rerun", key="cancer_readability_scatter", use_container_width=True)
            if _rl_event and _rl_event.selection and _rl_event.selection.points:
                _pt_rl = _rl_event.selection.points[0]
                _cd_rl = _pt_rl.get("customdata") or []
                _sel_title_rl = _cd_rl[1] if len(_cd_rl) > 1 else None
                if _sel_title_rl:
                    st.link_button(
                        f"Open in Wikipedia: {_sel_title_rl}",
                        f"https://en.wikipedia.org/wiki/{_sel_title_rl.replace(' ', '_')}",
                    )
        with eq2:
            st.subheader("Rare Cancer Disease Coverage by Quality Class")
            st.caption("Stub and Start rare cancer disease articles represent the steepest information gaps.")
            rare_df = df[df["is_rare_disease"].astype(bool)]
            if len(rare_df) > 0:
                rare_q = (
                    rare_df["quality_class"]
                    .value_counts()
                    .reindex([q for q in QUALITY_ORDER if q in rare_df["quality_class"].unique()])
                    .reset_index()
                )
                rare_q.columns = ["Quality", "Count"]
                fig_rare = px.bar(rare_q, x="Quality", y="Count", color="Quality", color_discrete_map=QUALITY_COLORS)
                fig_rare.update_layout(margin=dict(t=10, b=40), showlegend=False, plot_bgcolor="#F0F0F0", yaxis=dict(gridcolor="#E0E0E0"))
                rare_event = st.plotly_chart(fig_rare, on_select="rerun", key="cancer_rare_bar", use_container_width=True)
                if rare_event and rare_event.selection and rare_event.selection.points:
                    clicked_q = rare_event.selection.points[0].get("x")
                    if clicked_q and st.session_state.get("cancer_rare_filter") != clicked_q:
                        st.session_state["cancer_rare_filter"] = clicked_q
                        st.rerun()
                if st.session_state.get("cancer_rare_filter"):
                    st.caption("Click a different bar to change · use ✕ Clear above to reset")
                else:
                    st.caption(f"Total rare cancer disease articles: {len(rare_df):,} · Click a bar to filter the table")
            else:
                st.info("Run enrich_public_health.py to populate rare disease data.")
        st.page_link("pages/Methodology.py", label="📖 How are health equity metrics defined?")
    else:
        st.info(
            "**Health equity data not yet available.** "
            "Run `enrich_public_health.py` to add reading level and rare disease flags — "
            "then this tab will populate automatically."
        )

st.divider()
st.caption(
    "© 2026 Zach Schneider-Lynch, Brown University. "
    "Licensed under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/deed.en). "
    "Cancer articles identified via NLM MeSH C04 (Neoplasms) tree (703 descriptors, 2026 release) "
    "and title keyword matching."
)
