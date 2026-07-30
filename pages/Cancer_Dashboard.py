"""
WikiMed Cancer Article Recommender
Filters the full WikiProject Medicine corpus to oncology articles using the
NLM MeSH C04 (Neoplasms) tree, with a title-keyword fallback for untagged articles.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import os

st.set_page_config(
    page_title="Cancer Articles — WikiMed Recommender",
    page_icon="🎗️",
    layout="wide",
)

QUALITY_COLORS = {
    "Stub": "#08306B", "Start": "#08519C", "C": "#2171B5",
    "B": "#6BAED6", "GA": "#9ECAE1", "FA": "#DEEBF7",
}
QUALITY_ORDER = ["Stub", "Start", "C", "B", "GA", "FA"]
QUALITY_SCATTER_COLORS = {
    "Stub": "#B2182B", "Start": "#EF8A62", "C": "#FDBF93",
    "B": "#92C5DE", "GA": "#4393C3", "FA": "#2166AC",
}
_EDIT_TYPE_STYLES = {
    "Expand content":    "background-color:#FEE0D2; color:#99000D; font-weight:600",
    "Improve citations": "background-color:#FFF3CD; color:#7A5500",
    "Polish & review":   "background-color:#EDF8E9; color:#1A6B2E",
    "Maintain / Update": "",
}

_CANCER_KW = [
    "cancer", "carcinoma", "tumor", "tumour", "malignant", "malignancy",
    "leukemia", "leukaemia", "lymphoma", "sarcoma", "melanoma", "neoplasm",
    "oncology", "glioma", "blastoma", "adenoma", "mesothelioma", "myeloma",
    "metastasis", "metastatic",
]


@st.cache_data
def load_all():
    df = pd.read_csv("data/scored_articles.csv")
    df["wiki_url"] = "https://en.wikipedia.org/wiki/" + df["title"]
    df["edit_url"] = (
        "https://en.wikipedia.org/w/index.php?title="
        + df["title"].str.replace(" ", "_", regex=False)
        + "&action=edit"
    )
    for col in ["pageviews_12mo", "unique_editors"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    for col in ["impact_need_score", "wiki_attention_score", "reading_level"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


@st.cache_data
def load_cancer_mesh_ids():
    path = "data/cancer_mesh_ids.csv"
    if not os.path.exists(path):
        return set()
    return set(pd.read_csv(path)["mesh_id"].dropna().tolist())


@st.cache_data
def get_cancer_df():
    df = load_all()
    cancer_ids = load_cancer_mesh_ids()
    mesh_match = (
        df["mesh_id"].isin(cancer_ids)
        if "mesh_id" in df.columns
        else pd.Series(False, index=df.index)
    )
    kw_match = df["title"].str.lower().str.contains(
        "|".join(_CANCER_KW), regex=True, na=False
    )
    mask = mesh_match | (~mesh_match & kw_match)
    out = df[mask].copy()
    out["match_type"] = "MeSH C04"
    out.loc[~mesh_match[mask.values], "match_type"] = "Title keyword"
    return out, len(df)


# ── Guard ─────────────────────────────────────────────────────────────────────
if not os.path.exists("data/scored_articles.csv"):
    st.error("scored_articles.csv not found. Run the pipeline first.")
    st.stop()

df, n_total = get_cancer_df()
has_attention = "wiki_attention_score" in df.columns

n_cancer    = len(df)
n_stub_start = df["quality_class"].isin(["Stub", "Start"]).sum()
pct_low     = n_stub_start / n_cancer * 100 if n_cancer else 0
n_mesh      = (df["match_type"] == "MeSH C04").sum()

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
    <h1 style="font-size:2.6rem;font-weight:800;margin-top:-1rem;margin-bottom:0.15rem;line-height:1.1;">
        WikiMed Cancer Article Recommender
    </h1>
    <p style="font-size:1.05rem;color:#444;margin-bottom:1.2rem;">
        Oncology-focused view of WikiProject Medicine — identifying the highest-priority
        cancer Wikipedia articles for WikiMed student editors, ranked by public reach and quality gap.
        Articles matched via the NLM MeSH <strong>C04 Neoplasms</strong> tree (703 descriptors).
    </p>
""", unsafe_allow_html=True)

# ── Metric cards ──────────────────────────────────────────────────────────────
m1, m2, m3, m4 = st.columns(4)
m1.metric(
    "Cancer-related articles",
    f"{n_cancer:,}",
    help=f"{n_mesh:,} matched via MeSH C04 tree · {n_cancer - n_mesh:,} via title keywords",
)
m2.metric(
    "Stub or Start quality",
    f"{n_stub_start:,}  ({pct_low:.0f}%)",
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

st.divider()

# ── Charts ────────────────────────────────────────────────────────────────────
ch1, ch2 = st.columns(2)

with ch1:
    st.subheader("Quality Distribution — WikiProject Medicine Cancer Articles")
    qcounts = (
        df["quality_class"]
        .value_counts()
        .reindex([q for q in QUALITY_ORDER if q in df["quality_class"].unique()])
        .reset_index()
    )
    qcounts.columns = ["Quality", "Count"]
    fig_q = px.bar(qcounts, x="Quality", y="Count", color="Quality",
                   color_discrete_map=QUALITY_COLORS)
    fig_q.update_layout(
        margin=dict(t=10, b=40), showlegend=False,
        plot_bgcolor="#F0F0F0", yaxis=dict(gridcolor="#E0E0E0"),
    )
    st.plotly_chart(fig_q, use_container_width=True)
    st.caption(
        f"{n_stub_start:,} of {n_cancer:,} cancer articles ({pct_low:.0f}%) "
        "are Stub or Start — the lowest two quality tiers."
    )

with ch2:
    if has_attention:
        st.subheader("Impact-Need vs. Attention Score — Cancer Articles")
        _src = df[df["wiki_attention_score"].notna() & df["impact_need_score"].notna()].copy()
        _plot = _src.sample(min(3000, len(_src)), random_state=42).copy()
        _plot["_color"] = _plot["quality_class"]
        fig_sc = px.scatter(
            _plot,
            x="wiki_attention_score", y="impact_need_score",
            color="_color",
            color_discrete_map=QUALITY_SCATTER_COLORS,
            category_orders={"_color": ["FA", "GA", "B", "C", "Start", "Stub"]},
            labels={
                "wiki_attention_score": "Attention Score (0–100)",
                "impact_need_score":    "Impact-Need Score (0–100)",
                "_color":              "Quality",
            },
            hover_name="title",
            custom_data=["title"],
            opacity=0.6,
        )
        fig_sc.add_vline(x=50, line_dash="dot", line_color="#AAAAAA", line_width=1.5)
        fig_sc.add_hline(y=50, line_dash="dot", line_color="#AAAAAA", line_width=1.5)
        for _txt, _x, _y, _xa, _ya in [
            ("Edit now",    99, 98, "right", "top"),
            ("Hidden gems",  1, 98, "left",  "top"),
            ("Well-covered",99,  2, "right", "bottom"),
            ("Low priority", 1,  2, "left",  "bottom"),
        ]:
            fig_sc.add_annotation(x=_x, y=_y, text=_txt, showarrow=False,
                                  xanchor=_xa, yanchor=_ya,
                                  font=dict(size=11, color="#888888"))
        fig_sc.update_layout(
            margin=dict(t=10, b=40),
            plot_bgcolor="#F0F0F0",
            clickmode="event+select",
            dragmode=False,
            xaxis=dict(range=[0, 100], gridcolor="#E0E0E0", zeroline=False),
            yaxis=dict(range=[0, 100], gridcolor="#E0E0E0", zeroline=False),
        )
        _sc_event = st.plotly_chart(fig_sc, on_select="rerun",
                                    key="cancer_scatter", use_container_width=True)
        if _sc_event and _sc_event.selection and _sc_event.selection.points:
            _pt = _sc_event.selection.points[0]
            _sel = ((_pt.get("customdata") or [None])[0]) or _pt.get("hovertext")
            if _sel:
                st.link_button(
                    f"Open in Wikipedia: {_sel}",
                    f"https://en.wikipedia.org/wiki/{_sel.replace(' ', '_')}",
                )
    else:
        st.subheader("Quality × Importance — Cancer Articles")
        _imp_order = [i for i in ["Top", "High", "Mid", "Low"]
                      if i in df["importance_label"].dropna().unique()]
        _qual_order = [q for q in QUALITY_ORDER if q in df["quality_class"].unique()]
        _heat = (
            df.dropna(subset=["importance_label", "quality_class"])
            .groupby(["importance_label", "quality_class"]).size()
            .unstack(fill_value=0)
            .reindex(index=_imp_order, columns=_qual_order, fill_value=0)
        )
        fig_h = px.imshow(_heat, text_auto=True, color_continuous_scale="OrRd",
                          labels=dict(x="Quality Class", y="Importance", color="Articles"),
                          aspect="auto")
        fig_h.update_layout(margin=dict(t=10, b=40), coloraxis_showscale=False,
                             plot_bgcolor="#F0F0F0")
        st.plotly_chart(fig_h, use_container_width=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")
    if st.button("Refresh data"):
        st.cache_data.clear()
        st.rerun()

    all_q   = [q for q in QUALITY_ORDER if q in df["quality_class"].unique()]
    sel_q   = st.multiselect("Quality class", all_q, default=[])
    all_imp = [i for i in ["Top", "High", "Mid", "Low"]
               if i in df["importance_label"].dropna().unique()]
    sel_imp = st.multiselect("Importance", all_imp, default=[])
    sel_edit = st.multiselect(
        "Edit type needed",
        sorted(df["edit_type"].dropna().unique()),
        default=[],
    )
    sel_match = st.multiselect(
        "Article identification",
        ["MeSH C04", "Title keyword"],
        default=["MeSH C04", "Title keyword"],
        help="MeSH C04 = confirmed via NLM Neoplasms tree. Title keyword = cancer-related title without a MeSH tag.",
    )
    top_n = st.slider("Show top N articles", 10, 500, 100, 10)

    st.divider()
    st.caption(f"**{n_cancer:,}** cancer articles")
    st.caption(f"**{n_mesh:,}** matched via MeSH C04")
    st.caption(f"**{n_cancer - n_mesh:,}** matched via title keyword")
    st.divider()
    st.page_link("Dashboard.py", label="← Full WikiMed Dashboard")

# ── Apply sidebar filters ─────────────────────────────────────────────────────
filtered = df.copy()
if sel_q:
    filtered = filtered[filtered["quality_class"].isin(sel_q)]
if sel_imp:
    filtered = filtered[filtered["importance_label"].isin(sel_imp)]
if sel_edit:
    filtered = filtered[filtered["edit_type"].isin(sel_edit)]
if sel_match:
    filtered = filtered[filtered["match_type"].isin(sel_match)]
filtered = filtered.head(top_n)

# ── Article table ─────────────────────────────────────────────────────────────
st.divider()
st.subheader(f"Top {len(filtered)} Cancer Articles by Impact-Need Score")
st.caption(
    "Articles most urgently needing WikiMed student editing — ranked by the weighted "
    "composite of pageviews, clinical importance, quality gap, editor scarcity, and search intent."
)

if len(filtered) == 0:
    st.warning("No articles match the current filters.")
else:
    table_cols = ["rank", "wiki_url", "impact_need_score"]
    if "wiki_attention_score" in filtered.columns:
        table_cols.append("wiki_attention_score")
    table_cols += ["quality_class", "importance_label", "pageviews_12mo",
                   "unique_editors", "edit_type", "match_type", "edit_url"]
    if "mesh_id" in filtered.columns:
        table_cols.append("mesh_id")

    table_df = filtered[[c for c in table_cols if c in filtered.columns]].copy()
    for col, fmt in [
        ("impact_need_score",    lambda x: f"{x:.2f}" if pd.notna(x) else ""),
        ("wiki_attention_score", lambda x: f"{x:.2f}" if pd.notna(x) else ""),
        ("pageviews_12mo",       lambda x: f"{x:,.0f}" if pd.notna(x) else ""),
        ("unique_editors",       lambda x: f"{x:.0f}" if pd.notna(x) else ""),
    ]:
        if col in table_df.columns:
            table_df[col] = table_df[col].map(fmt)

    styler = table_df.style
    if "edit_type" in table_df.columns:
        styler = styler.apply(
            lambda col: [_EDIT_TYPE_STYLES.get(str(v), "") for v in col],
            subset=["edit_type"],
        )

    col_cfg = {
        "rank":                 st.column_config.NumberColumn("Rank", width="small"),
        "wiki_url":             st.column_config.LinkColumn("Article", display_text=r"wiki/(.+)", width="large"),
        "impact_need_score":    st.column_config.TextColumn("Impact-Need Score", width="medium"),
        "wiki_attention_score": st.column_config.TextColumn("Attention Score", width="medium"),
        "quality_class":        st.column_config.TextColumn("Quality", width="small"),
        "importance_label":     st.column_config.TextColumn("Importance", width="small"),
        "pageviews_12mo":       st.column_config.TextColumn("Pageviews (12mo)", width="medium"),
        "unique_editors":       st.column_config.TextColumn("Editors", width="small"),
        "edit_type":            st.column_config.TextColumn("Recommended Action", width="medium"),
        "match_type":           st.column_config.TextColumn("Cancer Match", width="small"),
        "mesh_id":              st.column_config.TextColumn("MeSH ID", width="small"),
        "edit_url":             st.column_config.LinkColumn("Edit", width="small"),
    }

    st.dataframe(styler, column_config=col_cfg, hide_index=True, height=480, width="stretch")

    csv_bytes = filtered.drop(columns=["edit_url"], errors="ignore").to_csv(index=False).encode()
    st.download_button(
        "Download cancer articles as CSV",
        data=csv_bytes,
        file_name="wikimed_cancer_articles.csv",
        mime="text/csv",
    )

st.divider()
st.caption(
    "© 2026 Zach Schneider-Lynch, Brown University. "
    "Licensed under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/deed.en). "
    "Cancer articles identified via NLM MeSH C04 (Neoplasms) tree (703 descriptors, 2026 release) "
    "and title keyword matching."
)
