import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import xml.etree.ElementTree as ET
import os
from difflib import get_close_matches

st.set_page_config(
    page_title="WikiProject Medicine Article Recommender",
    page_icon="🔬",
    layout="wide",
)

DATA_PATH = "data/scored_articles.csv"

# ColorBrewer Blues (6-class), dark→light maps Stub→FA so the most urgent
# articles are visually loudest in scatter plots and bar charts.
QUALITY_COLORS = {
    "Stub":  "#08306B",
    "Start": "#08519C",
    "C":     "#2171B5",
    "B":     "#6BAED6",
    "GA":    "#9ECAE1",
    "FA":    "#DEEBF7",
}
QUALITY_ORDER = ["Stub", "Start", "C", "B", "GA", "FA"]

# ColorBrewer RdBu-6 diverging palette for the attention scatter plot.
# Red = poor quality (urgent), Blue = good quality (less urgent). Colorblind-safe.
QUALITY_SCATTER_COLORS = {
    "Stub":  "#B2182B",
    "Start": "#EF8A62",
    "C":     "#FDBF93",
    "B":     "#92C5DE",
    "GA":    "#4393C3",
    "FA":    "#2166AC",
}

# ColorBrewer Greens (4-class) for importance — sequential, distinct from Blues.
IMPORTANCE_COLORS = {
    "Low":  "#EDF8E9",
    "Mid":  "#74C476",
    "High": "#238B45",
    "Top":  "#00441B",
}

# Quadrant definitions for the attention scatter selector.
# Key = label shown in radio; value = (high_attention, high_need) bool pair, or None for "all".
_Q_OPTIONS = {
    "All quadrants": None,
    "Edit now": (True, True),
    "Hidden gems": (False, True),
    "Well-covered": (True, False),
    "Low priority": (False, False),
}

# Custom non-equal score buckets weighted toward the top end.
# ColorBrewer Oranges (6-class): light=low score, dark=high score.
_SCORE_BUCKETS = [
    (98,  "#7F2704", "white"),   # top tier
    (95,  "#D94801", "white"),
    (90,  "#F16913", "white"),
    (75,  "#FDAE6B", "#333"),
    (50,  "#FDD0A2", "#333"),
    (0,   "#FFF5EB", "#555"),    # below median
]

_EDIT_TYPE_STYLES = {
    "Expand content":    "background-color:#FEE0D2; color:#99000D; font-weight:600",
    "Improve citations": "background-color:#FFF3CD; color:#7A5500",
    "Polish & review":   "background-color:#EDF8E9; color:#1A6B2E",
    "Maintain / Update": "",
}

_QUALITY_TABLE_STYLES = {
    "Stub":  "background-color:#B10026; color:white",
    "Start": "background-color:#E31A1C; color:white",
    "C":     "background-color:#FC4E2A; color:white",
    "B":     "background-color:#FD8D3C; color:#4D0000",
    "GA":    "background-color:#FEB24C; color:#4D0000",
    "FA":    "background-color:#FED976; color:#4D0000",
}

_IMPORTANCE_TABLE_STYLES = {
    "Top":  "background-color:#AD1457; color:white; font-weight:600",
    "High": "background-color:#6A1B9A; color:white",
    "Mid":  "background-color:#AB47BC; color:white",
    "Low":  "background-color:#F3E5F5; color:#4A148C",
}

def _edit_type_style(col):
    return [_EDIT_TYPE_STYLES.get(str(v), "") for v in col]

def _quality_table_style(col):
    return [_QUALITY_TABLE_STYLES.get(str(v), "") for v in col]

def _importance_table_style(col):
    return [_IMPORTANCE_TABLE_STYLES.get(str(v), "") for v in col]

def _score_style(v):
    """Return CSS string for a single Impact-Need Score value."""
    if v is None or (isinstance(v, float) and v != v):
        return ""
    for threshold, bg, fg in _SCORE_BUCKETS:
        if v >= threshold:
            return f"background-color:{bg}; color:{fg}"
    return ""


_READING_LEVEL_STYLES = {
    "≤6 Elementary":    "background-color:#D4EDDA; color:#155724",
    "7–8 Middle":       "background-color:#D1ECF1; color:#0C5460",
    "9–12 High School": "background-color:#FFF3CD; color:#856404",
    "13–16 College":    "background-color:#FFE5D0; color:#7D3C00",
    "17+ Graduate":     "background-color:#F8D7DA; color:#721C24",
}

def _reading_level_bucket(v):
    if pd.isna(v):
        return "Too short"
    v = float(v)
    if v <= 6:   return "≤6 Elementary"
    if v <= 8:   return "7–8 Middle"
    if v <= 12:  return "9–12 High School"
    if v <= 16:  return "13–16 College"
    return "17+ Graduate"

def _reading_level_style(col):
    return [_READING_LEVEL_STYLES.get(str(v), "") for v in col]


@st.cache_data
def load_mesh_index(mesh_path="data/desc2026.xml"):
    """Build a lightweight MeSH search index: name → IDs and ID → tree numbers."""
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
    """Return (df_with_found_via, suggestion_or_None); empty query returns (None, None)."""
    q = query.strip().lower()
    if not q:
        return None, None

    # ── Title matches (exact substring) ──────────────────────────────────────
    title_hits = df["title"].str.lower().str.contains(q, regex=False)

    # ── Fuzzy fallback: if no title hits, find the closest title ──────────────
    suggestion = None
    if not title_hits.any():
        all_titles_lower = df["title"].str.lower().tolist()
        close = get_close_matches(q, all_titles_lower, n=1, cutoff=0.75)
        if close:
            suggestion = df[df["title"].str.lower() == close[0]]["title"].iloc[0]
            title_hits = df["title"].str.lower().str.contains(close[0], regex=False)

    # ── MeSH expansion ───────────────────────────────────────────────────────
    seed_ids = {mid for name, ids in name_to_ids.items() if q in name for mid in ids}

    # If fuzzy-matched, also expand from the corrected term
    if suggestion and not seed_ids:
        sq = suggestion.lower()
        seed_ids = {mid for name, ids in name_to_ids.items() if sq in name for mid in ids}

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

    # ── Combine ───────────────────────────────────────────────────────────────
    title_df = df[title_hits].copy()
    title_df["found_via"] = "Title match"

    mesh_only = mesh_hits & ~title_hits
    mesh_df = df[mesh_only].copy()
    mesh_df["found_via"] = "MeSH related"
    mesh_df = mesh_df.sort_values("impact_need_score", ascending=False)

    result = pd.concat([title_df, mesh_df], ignore_index=True)
    return result, suggestion


@st.cache_data
def load_data(path):
    df = pd.read_csv(path)
    df["wiki_url"] = "https://en.wikipedia.org/wiki/" + df["title"]
    df["edit_url"] = (
        "https://en.wikipedia.org/w/index.php?title="
        + df["title"].str.replace(" ", "_", regex=False)
        + "&action=edit"
    )
    df["pageviews_12mo"]    = pd.to_numeric(df["pageviews_12mo"],    errors="coerce").fillna(0).astype(int)
    df["unique_editors"]    = pd.to_numeric(df["unique_editors"],    errors="coerce").fillna(0).astype(int)
    df["impact_need_score"] = pd.to_numeric(df["impact_need_score"], errors="coerce")
    if "reading_level" in df.columns:
        df["reading_level"] = pd.to_numeric(df["reading_level"], errors="coerce")
    if "is_rare_disease" in df.columns:
        df["is_rare_disease"] = df["is_rare_disease"].astype(str).str.lower().map(
            {"true": True, "false": False, "1": True, "0": False}
        ).fillna(False)
        df["rare_icon"] = df["is_rare_disease"].map({True: "🦓", False: ""})
    return df


# ── Page header ──────────────────────────────────────────────────────────────
st.markdown("""
    <style>
    .main-title {
        font-size: 2.8rem;
        font-weight: 800;
        margin-top: -2rem;
        margin-bottom: 0.2rem;
        line-height: 1.1;
    }
    .main-subtitle {
        font-size: 1.05rem;
        color: #333333;
        margin-bottom: 1.2rem;
    }
    </style>
    <h1 style="font-size:3.2rem; font-weight:800; margin-top:-2rem; margin-bottom:0.2rem; line-height:1.1;">WikiMed Article Recommender</h1>
    <p style="font-size:1.05rem; color:#333333; margin-bottom:1.2rem;">Helping WikiMed student editors find the WikiProject Medicine articles that need them most — ranked by impact need, real-time public attention, and clinical relevance. All data reflects the ~53,000 articles tagged by <a href="https://en.wikipedia.org/wiki/Wikipedia:WikiProject_Medicine" target="_blank">WikiProject Medicine</a>.</p>
""", unsafe_allow_html=True)

# ── Guard: no data yet ───────────────────────────────────────────────────────
if not os.path.exists(DATA_PATH):
    st.warning("**No scored data found.** Run the pipeline first:")
    st.code(
        "python wiki_scraper.py --sample 500\n"
        "python scoring.py",
        language="bash",
    )
    st.stop()

df = load_data(DATA_PATH)

if "heatmap_filter" not in st.session_state:
    st.session_state["heatmap_filter"] = None
if "rare_filter" not in st.session_state:
    st.session_state["rare_filter"] = None
if "show_onboarding" not in st.session_state:
    st.session_state["show_onboarding"] = True
if "quadrant_sel" not in st.session_state:
    st.session_state["quadrant_sel"] = "All quadrants"

has_equity     = "reading_level" in df.columns and "is_rare_disease" in df.columns
has_attention  = "wiki_attention_score" in df.columns
has_tfidf      = "medical_relevance" in df.columns

name_to_ids, id_to_trees = load_mesh_index()

# ── Onboarding banner ────────────────────────────────────────────────────────
if st.session_state["show_onboarding"]:
    with st.container(border=True):
        ob1, ob2 = st.columns([11, 1])
        with ob1:
            st.markdown(
                "**New here?** This dashboard ranks Wikipedia's medical articles by how urgently "
                "they need editing. The **Impact-Need Score** (0–100) combines public readership, "
                "editorial quality gaps, and clinical importance — a score of 100 means the most "
                "people are reading the weakest article. "
                "Use the **sidebar filters** to narrow by quality class, importance, or specialty, "
                "then click any article link to read it or the **Edit** link to start editing."
            )
        with ob2:
            if st.button("✕", key="dismiss_onboarding", help="Dismiss"):
                st.session_state["show_onboarding"] = False
                st.rerun()

# ── Search bar ───────────────────────────────────────────────────────────────
search_query = st.text_input(
    "🔍 Search articles",
    placeholder="e.g. pneumonia — searches titles and related MeSH terms",
)
search_results, search_suggestion = run_search(search_query, df, name_to_ids, id_to_trees)
if search_suggestion:
    st.info(f"No exact matches for \"{search_query}\" — showing results for **{search_suggestion}** instead.")

# ── Sidebar filters ──────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")
    if st.button("Refresh data"):
        st.cache_data.clear()
        st.rerun()

    all_quality    = [q for q in QUALITY_ORDER if q in df["quality_class"].unique()]
    all_importance = [i for i in ["Low", "Mid", "High", "Top"] if i in df["importance_label"].dropna().unique()]
    all_edit_types = sorted(df["edit_type"].dropna().unique())
    all_difficulty = sorted(df["difficulty"].dropna().unique()) if "difficulty" in df.columns else []

    sel_quality = st.multiselect(
        "Quality class", all_quality, default=[],
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
    sel_importance = st.multiselect(
        "Importance", all_importance, default=[],
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
        sel_difficulty = st.multiselect("Difficulty", all_difficulty, default=[])
    else:
        sel_difficulty = []

    if "specialty" in df.columns:
        all_specialties = sorted(
            {s.strip() for cell in df["specialty"].dropna() for s in cell.split("|")}
        )
        sel_specialty = st.multiselect(
            "Specialty", all_specialties, default=[],
            help="Leave blank to show all specialties"
        )
    else:
        sel_specialty = []

    # Medical relevance filter
    if has_tfidf:
        st.divider()
        st.subheader("Medical Relevance")
        min_med_rel = st.slider(
            "Min medical relevance (1–10)", 1, 10, 1,
            help="Filter to articles scoring at least this value. Higher = more purely clinical content."
        )
    else:
        min_med_rel = 0

    # MeSH filters
    if "mesh_confidence" in df.columns or "mesh_id" in df.columns:
        st.divider()
        st.subheader("MeSH Filters")

    if "mesh_confidence" in df.columns:
        all_confidence = ["High", "Medium", "Low", "Broad"]
        sel_mesh_confidence = st.multiselect(
            "MeSH match confidence",
            all_confidence,
            default=["High", "Medium"],
            help="High/Medium = reliable matches. Low = indirect but often clinically correct. Broad = term too general for research use."
        )
    else:
        sel_mesh_confidence = []

    if "mesh_id" in df.columns:
        sel_mesh_id = st.text_input(
            "Browse by MeSH ID",
            placeholder="e.g. D009203",
            key="mesh_id_input",
            help="Show all articles assigned this exact MeSH descriptor. Copy an ID from the MeSH ID column in the table.",
        )
        if sel_mesh_id.strip():
            if st.button("✕ Clear MeSH ID filter", key="clear_mesh_id"):
                st.session_state["mesh_id_input"] = ""
                st.rerun()
    else:
        sel_mesh_id = ""

    # Equity filters
    if has_equity:
        st.divider()
        st.subheader("Health Equity Filters")
        sel_rare = st.checkbox(
            "Rare diseases only", value=False,
            help="Show only articles flagged as rare diseases from Wikipedia categories"
        )
        max_rl = int(df["reading_level"].dropna().max()) + 1
        sel_reading = st.slider(
            "Max reading level (FK grade)", min_value=1, max_value=max_rl, value=max_rl,
            help="US adults read at ~8th grade on average. Filter to articles at or below this level."
        )
    else:
        sel_rare    = False
        sel_reading = None

    top_n = st.slider("Show top N results", 10, 500, 100, 10)

    st.divider()
    st.caption(f"Total dataset: **{len(df):,}** articles")

    with st.expander("📖 Glossary"):
        st.markdown("""
**Quality Classes** *(Wikipedia editorial rating)*
| Class | Meaning |
|-------|---------|
| FA | Featured Article — Wikipedia's highest standard |
| GA | Good Article — independently reviewed |
| B | Reasonably complete, minor issues |
| C | Substantial but incomplete |
| Start | Developing, major gaps |
| Stub | Very basic, minimal content |

**Importance** *(WikiProject Medicine rating)*
| Level | Meaning |
|-------|---------|
| Top | Core medical topic (e.g. Cancer, Diabetes) |
| High | Major specialty or disease topic |
| Mid | Useful but non-essential |
| Low | Niche or peripheral |

**Impact-Need Score** (0–100): weighted composite — pageviews (30%), importance (25%), quality deficit (25%), editor scarcity (10%), search intent (10%). Score of 100 = highest-need article in dataset.

**Flesch-Kincaid Grade** (FK): US school grade level needed to read the text. Average US adult reads at ~8th grade.
        """)

# ── Apply filters ────────────────────────────────────────────────────────────
filtered = search_results.copy() if search_results is not None else df.copy()

if sel_quality:
    filtered = filtered[filtered["quality_class"].isin(sel_quality)]
if sel_importance:
    filtered = filtered[filtered["importance_label"].isin(sel_importance)]
if sel_edit:
    filtered = filtered[filtered["edit_type"].isin(sel_edit)]
if sel_difficulty and "difficulty" in filtered.columns:
    filtered = filtered[filtered["difficulty"].isin(sel_difficulty)]
if sel_specialty and "specialty" in filtered.columns:
    filtered = filtered[
        filtered["specialty"].fillna("").apply(
            lambda s: any(sp in s for sp in sel_specialty)
        )
    ]
if has_tfidf and min_med_rel > 1:
    filtered = filtered[filtered["medical_relevance"] >= min_med_rel]
if sel_mesh_confidence and "mesh_confidence" in filtered.columns:
    filtered = filtered[filtered["mesh_confidence"].isin(sel_mesh_confidence)]
if sel_rare and "is_rare_disease" in filtered.columns:
    filtered = filtered[filtered["is_rare_disease"] == True]
if sel_reading is not None and "reading_level" in filtered.columns:
    filtered = filtered[
        filtered["reading_level"].isna() | (filtered["reading_level"] <= sel_reading)
    ]

mesh_id_mode = bool(sel_mesh_id.strip()) and "mesh_id" in filtered.columns
if mesh_id_mode:
    filtered = filtered[filtered["mesh_id"].str.upper() == sel_mesh_id.strip().upper()]

filtered = filtered.copy() if (search_results is not None or mesh_id_mode) else filtered.head(top_n).copy()

# Heatmap click-through filter — applied on top of all other filters
_hm = st.session_state.get("heatmap_filter")
if _hm:
    hm_quality, hm_importance = _hm
    filtered = filtered[
        (filtered["quality_class"]    == hm_quality) &
        (filtered["importance_label"] == hm_importance)
    ]

# Rare disease bar click-through filter
_rd = st.session_state.get("rare_filter")
if _rd and "is_rare_disease" in filtered.columns:
    filtered = filtered[
        (filtered["is_rare_disease"] == True) &
        (filtered["quality_class"]   == _rd)
    ]

# Quadrant filter — applied when user selects a quadrant in the Attention tab
_sel_q = _Q_OPTIONS.get(st.session_state.get("quadrant_sel", "All quadrants"))
if _sel_q is not None and has_attention and "wiki_attention_score" in filtered.columns:
    _high_att, _high_need = _sel_q
    filtered = filtered[
        ((filtered["wiki_attention_score"] >= 50) == _high_att) &
        ((filtered["impact_need_score"]    >= 50) == _high_need)
    ]

# ── Summary metric cards ─────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
n = len(filtered)
c1.metric("Articles shown", f"{n:,}")
c2.metric(
    "Avg impact-need score",
    f"{filtered['impact_need_score'].mean():.1f} / 100" if n else "—",
)
if has_attention:
    c3.metric(
        "Avg attention score",
        f"{filtered['wiki_attention_score'].mean():.1f} / 100" if n else "—",
    )
else:
    c3.metric(
        "Avg pageviews (12 mo)",
        f"{int(filtered['pageviews_12mo'].mean()):,}" if n else "—",
    )
if has_tfidf and n:
    c4.metric(
        "Avg medical relevance",
        f"{filtered['medical_relevance'].mean():.1f} / 10" if n else "—",
        help="TF-IDF keyword overlap with MeSH vocabulary"
    )
elif has_equity and n:
    c4.metric(
        "Avg reading level",
        f"Grade {filtered['reading_level'].mean():.1f}" if filtered["reading_level"].notna().any() else "—",
    )
else:
    c4.metric(
        "Avg unique editors",
        f"{filtered['unique_editors'].mean():.1f}" if n else "—",
    )

_hm = st.session_state.get("heatmap_filter")
if _hm:
    hm_q, hm_i = _hm
    n_cell = len(df[(df["quality_class"] == hm_q) & (df["importance_label"] == hm_i)])
    fc1, fc2 = st.columns([8, 1])
    fc1.info(
        f"📊 **Gap matrix filter:** {hm_i} importance × {hm_q} quality "
        f"— {n_cell:,} article{'s' if n_cell != 1 else ''} in full dataset"
    )
    if fc2.button("✕ Clear", key="clear_heatmap_filter"):
        st.session_state["heatmap_filter"] = None
        st.rerun()

_rd = st.session_state.get("rare_filter")
if _rd:
    n_rare_q = len(df[(df["is_rare_disease"] == True) & (df["quality_class"] == _rd)]) if "is_rare_disease" in df.columns else 0
    rc1, rc2 = st.columns([8, 1])
    rc1.info(f"🦓 **Rare disease filter:** {_rd} quality — {n_rare_q:,} rare disease articles in full dataset")
    if rc2.button("✕ Clear", key="clear_rare_filter"):
        st.session_state["rare_filter"] = None
        st.rerun()

_active_q_label = st.session_state.get("quadrant_sel", "All quadrants")
if _active_q_label != "All quadrants":
    qc1, qc2 = st.columns([8, 1])
    qc1.info(f"⚡ **Quadrant filter:** {_active_q_label}")
    if qc2.button("✕ Clear", key="clear_quadrant_filter"):
        st.session_state["quadrant_sel"] = "All quadrants"
        st.rerun()

st.divider()

# ── Article table ────────────────────────────────────────────────────────────
if n == 0:
    st.warning("No articles match the current filters. Try broadening your selection.")
else:
    st.markdown("""
        <style>
        [data-testid="stPageLink"] a {
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.2rem;
            font-weight: 700;
            padding: 0.65rem 1.1rem;
            border: 2px solid #1f6fa8;
            border-radius: 8px;
            color: #1f6fa8 !important;
            background-color: #f0f6fc;
            text-decoration: none !important;
            text-align: center;
            white-space: nowrap;
        }
        [data-testid="stPageLink"] a:hover {
            background-color: #1f6fa8;
            color: white !important;
        }
        </style>
    """, unsafe_allow_html=True)
    left_h, right_h = st.columns([2, 1])
    if mesh_id_mode:
        mid = sel_mesh_id.strip().upper()
        mname = ""
        if "mesh_preferred_name" in filtered.columns and filtered["mesh_preferred_name"].notna().any():
            mname = filtered["mesh_preferred_name"].dropna().iloc[0]
        label = f"{mid} — {mname}" if mname else mid
        left_h.subheader(f"All articles tagged: {label}")
        left_h.caption(f"{n} article{'s' if n != 1 else ''} with this MeSH descriptor")
    elif search_results is not None:
        n_title = (search_results["found_via"] == "Title match").sum()
        n_mesh  = (search_results["found_via"] == "MeSH related").sum()
        left_h.subheader(f"Search results for \"{search_query}\"")
        left_h.caption(f"{n_title} title match{'es' if n_title != 1 else ''} · {n_mesh} related via MeSH")
    else:
        left_h.subheader(f"Top {n} Recommended Articles")
    right_h.page_link("pages/Methodology.py", label="📖 How are scores calculated?", use_container_width=True)

    table_cols = ["rank", "wiki_url", "impact_need_score"]
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
    table_cols += ["edit_url"]

    table_df = filtered[[c for c in table_cols if c in filtered.columns]].copy()

    col_cfg = {
        "rank":               st.column_config.NumberColumn("Rank",             width="small"),
        "rare_icon":          st.column_config.TextColumn("Rare Disease",        width="small"),
        "wiki_url":           st.column_config.LinkColumn("Article",            display_text=r"wiki/(.+)", width="large"),
        "impact_need_score":  st.column_config.TextColumn(
            "Impact-Need Score (0-100)",
            help="Weighted composite of pageviews (30%), importance (25%), quality deficit (25%), editor scarcity (10%), and search intent (10%). Top article = 100.",
            width="medium"
        ),
        "wiki_attention_score": st.column_config.TextColumn(
            "Attention Score (0-100)",
            help="Measures current momentum: pageviews (45%), traffic velocity (20%), inbound links (20%), watchers (10%), active editors (5%). Top article = 100.",
            width="medium"
        ),
        "quality_class":      st.column_config.TextColumn("Quality",
            help="Editorial quality rating assigned by WikiProject Medicine volunteers: Stub → Start → C → B → GA → FA (Featured Article).",
            width="small"),
        "importance_label":   st.column_config.TextColumn("Importance",
            help="Topic importance rating assigned by WikiProject Medicine volunteers: Low → Mid → High → Top.",
            width="small"),
        "pageviews_12mo":     st.column_config.TextColumn("Pageviews (12mo)",
            help="Total page views over the past 12 months, sourced from the Wikimedia pageview API.",
            width="medium"),
        "unique_editors":     st.column_config.TextColumn("Editors", width="small",
            help="Number of unique registered editors who made at least one edit to this article in the past 12 months, sourced from the Wikipedia API (action=query, prop=revisions)."),
        "edit_type":          st.column_config.TextColumn("Recommended Action", width="medium"),
        "difficulty":         st.column_config.TextColumn("Difficulty",         width="small"),
        "specialty":          st.column_config.TextColumn("Specialty",          width="medium"),
        "reading_level":      st.column_config.TextColumn("Reading Level", width="medium",
            help="Flesch-Kincaid Grade Level (FKGL) — estimates the U.S. school grade needed to understand the text. Computed from the article's Wikipedia lead section. 'Too short' = lead section under 30 words."),
        "mesh_id":            st.column_config.TextColumn("MeSH ID",            width="small"),
        "mesh_preferred_name": st.column_config.TextColumn("MeSH Term",         width="medium"),
        "mesh_confidence":    st.column_config.TextColumn("MeSH Confidence",    width="small"),
        "medical_relevance":  st.column_config.TextColumn(
            "Medical Relevance (1-10)",
            help="TF-IDF keyword overlap with the NLM MeSH 2026 vocabulary. Higher = more purely clinical content.",
            width="medium"
        ),
        "top_tfidf_terms":    st.column_config.TextColumn("Key Terms (TF-IDF)", width="large"),
        "edit_url":           st.column_config.LinkColumn("Edit",               width="small"),
        "found_via":          st.column_config.TextColumn("Match type",          width="medium"),
    }

    # Save numeric arrays for gradient colour mapping before converting columns to strings.
    # Streamlit's canvas renderer ignores Styler.format() so we pre-format directly in table_df.
    impact_gmap    = table_df["impact_need_score"].to_numpy()    if "impact_need_score"   in table_df.columns else None
    attention_gmap = table_df["wiki_attention_score"].to_numpy() if "wiki_attention_score" in table_df.columns else None
    pageviews_gmap  = pd.to_numeric(table_df["pageviews_12mo"],  errors="coerce").to_numpy() if "pageviews_12mo"   in table_df.columns else None
    editors_gmap    = pd.to_numeric(table_df["unique_editors"],  errors="coerce").to_numpy() if "unique_editors"   in table_df.columns else None
    relevance_gmap  = pd.to_numeric(table_df["medical_relevance"], errors="coerce").to_numpy() if "medical_relevance" in table_df.columns else None

    if "impact_need_score"   in table_df.columns:
        table_df["impact_need_score"]   = table_df["impact_need_score"].map(lambda x: f"{x:.2f}"   if pd.notna(x) else "")
    if "wiki_attention_score" in table_df.columns:
        table_df["wiki_attention_score"] = table_df["wiki_attention_score"].map(lambda x: f"{x:.2f}" if pd.notna(x) else "")
    if "medical_relevance"   in table_df.columns:
        table_df["medical_relevance"]   = table_df["medical_relevance"].map(lambda x: f"{x:.2f}"   if pd.notna(x) else "")
    if "pageviews_12mo"      in table_df.columns:
        table_df["pageviews_12mo"]      = table_df["pageviews_12mo"].map(lambda x: f"{x:,.0f}"     if pd.notna(x) else "")
    if "unique_editors"      in table_df.columns:
        table_df["unique_editors"]      = table_df["unique_editors"].map(lambda x: f"{x:.0f}"      if pd.notna(x) else "")
    if "reading_level"       in table_df.columns:
        table_df["reading_level"]       = table_df["reading_level"].map(_reading_level_bucket)

    styler = table_df.style
    if impact_gmap is not None:
        # Discrete Oranges buckets (non-equal width, top-heavy) instead of continuous gradient.
        def _apply_score_buckets(col, arr=impact_gmap):
            return [_score_style(v) for v in arr]
        styler = styler.apply(_apply_score_buckets, subset=["impact_need_score"])
    if attention_gmap is not None:
        styler = styler.background_gradient(
            subset=["wiki_attention_score"], cmap="PuBu", vmin=0, vmax=100, gmap=attention_gmap
        )
    if "quality_class" in table_df.columns:
        styler = styler.apply(_quality_table_style, subset=["quality_class"])
    if "importance_label" in table_df.columns:
        styler = styler.apply(_importance_table_style, subset=["importance_label"])
    if pageviews_gmap is not None:
        styler = styler.background_gradient(
            subset=["pageviews_12mo"], cmap="Blues", gmap=pageviews_gmap
        )
    if editors_gmap is not None:
        styler = styler.background_gradient(
            subset=["unique_editors"], cmap="Greens", gmap=editors_gmap
        )
    if relevance_gmap is not None:
        styler = styler.background_gradient(
            subset=["medical_relevance"], cmap="YlGn", vmin=0, vmax=10, gmap=relevance_gmap
        )
    if "edit_type" in table_df.columns:
        styler = styler.apply(_edit_type_style, subset=["edit_type"])
    if "reading_level" in table_df.columns:
        styler = styler.apply(_reading_level_style, subset=["reading_level"])

    st.dataframe(
        styler,
        column_config=col_cfg,
        width='stretch',
        hide_index=True,
        height=480,
    )

    csv_bytes = filtered.drop(columns=["edit_url"], errors="ignore").to_csv(index=False).encode()
    st.download_button(
        "Download filtered results as CSV",
        data=csv_bytes,
        file_name="wikimed_recommendations.csv",
        mime="text/csv",
    )

    if "rare_icon" in filtered.columns and (filtered["rare_icon"] == "🦓").any():
        st.caption("🦓 Rare disease article — affects fewer than 1 in 2,000 people")

    # ── Browse by MeSH ID ────────────────────────────────────────────────────
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
                "Find all articles with the same MeSH ID:",
                options=[""] + unique_ids["mesh_id"].tolist(),
                format_func=lambda x: "Select a MeSH ID from visible articles..." if x == "" else fmt_option(x),
            )
        with brow2:
            st.write("&nbsp;", unsafe_allow_html=True)
            if st.button("Browse all →", disabled=not picked_id, use_container_width=True):
                st.session_state["mesh_id_input"] = picked_id
                st.rerun()

# ── Charts ───────────────────────────────────────────────────────────────────
st.divider()
tab_attention, tab_overview, tab_matrix, tab_equity = st.tabs([
    "⚡ Attention",
    "📊 Score Overview",
    "🔥 Priority Matrix",
    "🏥 Health Equity",
])

# ── Tab 1: Score Overview ────────────────────────────────────────────────────
with tab_overview:
    st.markdown(
        "**Score Distribution** shows how Impact-Need Scores spread across all ~53,000 WikiProject Medicine articles. "
        "Most articles cluster near zero — the right tail represents the highest-priority editing targets. "
        "**Quality Breakdown** shows how many of those articles fall into each Wikipedia editorial tier; "
        "Stub and Start together typically account for the majority."
    )
    ov1, ov2 = st.columns(2)
    with ov1:
        st.subheader("Score Distribution")
        vals = df["impact_need_score"].dropna().values
        bw = 1.06 * vals.std() * len(vals) ** (-0.2)
        samp = vals if len(vals) <= 5000 else np.random.default_rng(42).choice(vals, 5000, replace=False)
        x_grid = np.linspace(0, 100, 400)
        diff = x_grid[:, None] - samp[None, :]
        kde = np.exp(-0.5 * (diff / bw) ** 2).sum(axis=1) / (len(samp) * bw * np.sqrt(2 * np.pi))
        fig_density = go.Figure(go.Scatter(
            x=x_grid, y=kde,
            mode="lines",
            fill="tozeroy",
            line=dict(color="#F16913", width=2.5),
            fillcolor="rgba(241,105,19,0.15)",
            hovertemplate="Score %{x:.1f}<extra></extra>",
        ))
        fig_density.update_layout(
            margin=dict(t=10, b=40),
            xaxis_title="Impact-Need Score (0–100)",
            yaxis_title="Density",
            showlegend=False,
            plot_bgcolor="#F0F0F0",
            xaxis=dict(range=[0, 100], gridcolor="#E0E0E0"),
            yaxis=dict(showticklabels=False, gridcolor="#E0E0E0"),
        )
        st.plotly_chart(fig_density, width='stretch')
    with ov2:
        st.subheader("Quality Level Breakdown — WikiProject Medicine")
        qcounts = (
            df["quality_class"]
            .value_counts()
            .reindex([q for q in QUALITY_ORDER if q in df["quality_class"].unique()])
            .reset_index()
        )
        qcounts.columns = ["Quality", "Count"]
        fig_bar = px.bar(
            qcounts, x="Quality", y="Count",
            color="Quality",
            color_discrete_map=QUALITY_COLORS,
        )
        fig_bar.update_layout(margin=dict(t=10, b=40), showlegend=False, plot_bgcolor="#F0F0F0", yaxis=dict(gridcolor="#E0E0E0"))
        st.plotly_chart(fig_bar, width='stretch')
    st.page_link("pages/Methodology.py", label="📖 How is the Impact-Need Score calculated?")

# ── Tab 2: Priority Matrix ───────────────────────────────────────────────────
with tab_matrix:
    st.markdown(
        "Each cell shows how many **WikiProject Medicine articles** sit at that combination of "
        "**importance** (how medically significant the topic is) and **quality** (how complete the article is). "
        "**Top-left cells** (Top/High importance × Stub/Start quality) represent the biggest "
        "unmet need — clinically important topics with very poor coverage."
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
        heat_df,
        text_auto=True,
        color_continuous_scale="OrRd",
        labels=dict(x="Quality Class", y="Importance", color="Articles"),
        aspect="auto",
    )
    _xs, _ys, _zs = [], [], []
    for _col in heat_df.columns:
        for _idx in heat_df.index:
            _xs.append(_col)
            _ys.append(_idx)
            _zs.append(heat_df.loc[_idx, _col])
    fig_heat.add_trace(go.Scatter(
        x=_xs, y=_ys,
        mode="markers",
        marker=dict(size=36, opacity=0.001, color="rgba(0,0,0,0)"),
        customdata=list(zip(_xs, _ys)),
        hoverinfo="skip",
        showlegend=False,
    ))
    fig_heat.update_layout(
        margin=dict(t=10, b=40),
        coloraxis_showscale=False,
        clickmode="event+select",
        dragmode=False,
        plot_bgcolor="#F0F0F0",
    )
    gap_event = st.plotly_chart(fig_heat, on_select="rerun", key="gap_matrix", use_container_width=True)
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
            if st.session_state.get("heatmap_filter") != new_hm:
                st.session_state["heatmap_filter"] = new_hm
                st.rerun()
    if st.session_state.get("heatmap_filter"):
        st.caption("Click a different cell to change the filter · use ✕ Clear above to reset")
    else:
        st.caption("Click any cell to filter the article table to that importance × quality combination.")
    st.page_link("pages/Methodology.py", label="📖 How are importance and quality defined?")

# ── Tab 3: Attention ─────────────────────────────────────────────────────────
with tab_attention:
    if has_attention:
        st.markdown(
            "Each dot is a WikiProject Medicine article. **Color shows quality** — red dots are Stub/Start "
            "articles with the most room to grow; blue dots are already well-developed. "
            "Use the quadrant selector below to highlight the articles that matter most for your editing goals."
        )

        _sel_q_label = st.radio(
            "Highlight quadrant", list(_Q_OPTIONS.keys()),
            horizontal=True, key="quadrant_sel",
        )
        _sel_q = _Q_OPTIONS[_sel_q_label]

        st.subheader("Impact-Need vs. Attention Score — WikiProject Medicine articles")
        _scatter_src = df[df["wiki_attention_score"].notna() & df["impact_need_score"].notna()].copy()
        _scatter_plot = _scatter_src.sample(min(5000, len(_scatter_src)), random_state=42).copy()

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

        fig_scatter = px.scatter(
            _scatter_plot,
            x="wiki_attention_score",
            y="impact_need_score",
            color="_color",
            color_discrete_map=_cmap,
            category_orders=_cat,
            labels={
                "wiki_attention_score": "Attention Score (0–100)",
                "impact_need_score":    "Impact-Need Score (0–100)",
                "_color":              "Quality",
            },
            hover_name="title",
            custom_data=["title"],
            opacity=0.55,
        )
        fig_scatter.add_vline(x=50, line_dash="dot", line_color="#AAAAAA", line_width=1.5)
        fig_scatter.add_hline(y=50, line_dash="dot", line_color="#AAAAAA", line_width=1.5)
        for _txt, _x, _y, _xa, _ya in [
            ("Edit now",    99, 98, "right", "top"),
            ("Hidden gems",  1, 98, "left",  "top"),
            ("Well-covered",99,  2, "right", "bottom"),
            ("Low priority", 1,  2, "left",  "bottom"),
        ]:
            fig_scatter.add_annotation(x=_x, y=_y, text=_txt, showarrow=False,
                                       xanchor=_xa, yanchor=_ya,
                                       font=dict(size=11, color="#888888"))
        fig_scatter.update_layout(
            margin=dict(t=10, b=40),
            plot_bgcolor="#F0F0F0",
            clickmode="event+select",
            dragmode=False,
            xaxis=dict(range=[0, 100], gridcolor="#E0E0E0", zeroline=False),
            yaxis=dict(range=[0, 100], gridcolor="#E0E0E0", zeroline=False),
        )
        _att_event = st.plotly_chart(fig_scatter, on_select="rerun", key="attention_scatter", use_container_width=True)
        if _att_event and _att_event.selection and _att_event.selection.points:
            _pt = _att_event.selection.points[0]
            _sel_title = ((_pt.get("customdata") or [None])[0]) or _pt.get("hovertext")
            if _sel_title:
                st.link_button(
                    f"Open in Wikipedia: {_sel_title}",
                    f"https://en.wikipedia.org/wiki/{_sel_title.replace(' ', '_')}",
                )
        st.page_link("pages/Methodology.py", label="📖 How is the Attention Score calculated?")
    else:
        st.info(
            "**Attention Score not yet available.** "
            "Run `fetch_attention.py` to add real-time pageview velocity, inbound links, "
            "and watcher counts — then this chart will appear automatically."
        )

# ── Tab 4: Health Equity ─────────────────────────────────────────────────────
with tab_equity:
    if has_equity:
        st.markdown(
            "Health equity gaps appear when important medical information is either "
            "**inaccessible** (written above a typical reader's grade level) or "
            "**absent** (rare disease articles with minimal coverage). "
            "The average US adult reads at an 8th-grade level — articles above that threshold "
            "create barriers for the very patients they're meant to serve."
        )
        eq1, eq2 = st.columns(2)
        with eq1:
            st.subheader("Readability vs. Public Reach")
            st.caption(
                "Top-right quadrant: heavily read articles written above a college reading "
                "level — the biggest accessibility gaps."
            )
            plot_df = df[df["reading_level"].notna() & (df["pageviews_12mo"] > 0)].copy()
            plot_df["pageviews_log"] = np.log10(plot_df["pageviews_12mo"] + 1)
            plot_df["rl_sqrt"] = np.sqrt(plot_df["reading_level"].clip(lower=0))
            fig_rl = px.scatter(
                plot_df.sample(min(5000, len(plot_df)), random_state=42),
                x="rl_sqrt",
                y="pageviews_log",
                color="importance_label",
                color_discrete_map=IMPORTANCE_COLORS,
                category_orders={"importance_label": ["Low", "Mid", "High", "Top"]},
                labels={
                    "rl_sqrt":          "Flesch-Kincaid Grade Level",
                    "pageviews_log":    "Pageviews (log₁₀)",
                    "importance_label": "Importance",
                },
                custom_data=["reading_level", "title"],
                opacity=0.5,
            )
            fig_rl.update_traces(
                hovertemplate="<b>%{customdata[1]}</b><br>"
                              "Grade level: %{customdata[0]:.1f}<br>"
                              "Pageviews (log): %{y:.2f}<extra></extra>"
            )
            ref_lines = [
                (6,  "6th grade",          "#bbb",    "top right"),
                (8,  "8th — avg US adult", "#888",    "top left"),
                (12, "12th grade (HS)",    "#238B45", "top right"),
                (16, "College grad",       "#00441B", "top left"),
            ]
            for grade, label, color, pos in ref_lines:
                fig_rl.add_vline(
                    x=np.sqrt(grade), line_dash="dash", line_color=color, line_width=1.5,
                    annotation_text=label, annotation_position=pos,
                    annotation_font=dict(size=10, color=color),
                    annotation_bgcolor="rgba(255,255,255,0.75)",
                )
            tick_grades = [4, 6, 8, 10, 12, 16, 20, 28]
            fig_rl.update_layout(
                margin=dict(t=10, b=40),
                plot_bgcolor="#F0F0F0",
                xaxis=dict(
                    title="Flesch-Kincaid Grade Level (√ scale)",
                    tickvals=[np.sqrt(g) for g in tick_grades],
                    ticktext=[str(g) for g in tick_grades],
                    gridcolor="#E0E0E0",
                ),
                yaxis=dict(gridcolor="#E0E0E0"),
            )
            _rl_event = st.plotly_chart(fig_rl, on_select="rerun", key="readability_scatter", use_container_width=True)
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
            st.subheader("Rare Disease Coverage by Quality Class")
            st.caption(
                "Stub and Start articles for rare diseases represent the steepest "
                "information gaps — patients searching for these conditions find little."
            )
            rare_df = df[df["is_rare_disease"] == True]
            if len(rare_df) > 0:
                rare_q = (
                    rare_df["quality_class"]
                    .value_counts()
                    .reindex([q for q in QUALITY_ORDER if q in rare_df["quality_class"].unique()])
                    .reset_index()
                )
                rare_q.columns = ["Quality", "Count"]
                fig_rare = px.bar(
                    rare_q, x="Quality", y="Count",
                    color="Quality",
                    color_discrete_map=QUALITY_COLORS,
                )
                fig_rare.update_layout(margin=dict(t=10, b=40), showlegend=False, plot_bgcolor="#F0F0F0", yaxis=dict(gridcolor="#E0E0E0"))
                rare_event = st.plotly_chart(fig_rare, on_select="rerun", key="rare_bar", use_container_width=True)
                if rare_event and rare_event.selection and rare_event.selection.points:
                    clicked_q = rare_event.selection.points[0].get("x")
                    if clicked_q and st.session_state.get("rare_filter") != clicked_q:
                        st.session_state["rare_filter"] = clicked_q
                        st.rerun()
                if st.session_state.get("rare_filter"):
                    st.caption("Click a different bar to change · use ✕ Clear above to reset")
                else:
                    st.caption(f"Total rare disease articles: {len(rare_df):,} · Click a bar to filter the table")
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
    "Licensed under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/deed.en)."
)

