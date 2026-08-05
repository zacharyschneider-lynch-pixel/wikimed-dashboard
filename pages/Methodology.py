import streamlit as st


st.title("How Scores Are Calculated")
st.caption("WikiMed Article Dashboard — scoring methodology")

# ── Impact-Need Score ─────────────────────────────────────────────────────────
st.header("Impact-Need Score (0–100)")
st.markdown("""
The Impact-Need Score is the primary ranking signal. It identifies Wikipedia medical articles
that have **high public reach but low current quality** — the best targets for WikiMed student editing.

**Formula:**

$$
\\text{Impact-Need} = \\left(P_{pv} \\times 0.30 + N_{imp} \\times 0.25 + N_{qd} \\times 0.25 + P_{es} \\times 0.10 + P_{si} \\times 0.10\\right) \\times \\frac{100}{\\text{max}}
$$

The raw composite is divided by the maximum observed value so the top-ranked article always scores **100**.

| Component | Symbol | Weight | How it's computed |
|---|---|---|---|
| **Pageview percentile** | $P_{pv}$ | 30% | Percentile rank of 12-month pageview count across all 53k articles |
| **Importance** | $N_{imp}$ | 25% | WikiProject Medicine importance label converted to a 0–1 scale: Low=0, Mid=0.33, High=0.67, Top=1.0 |
| **Quality deficit** | $N_{qd}$ | 25% | Inverse of quality class on a 0–1 scale: FA=0, GA=0.25, B=0.5, C=0.75, Start=0.875, Stub=1.0 — higher score = more room to improve |
| **Editor scarcity** | $P_{es}$ | 10% | Percentile rank of $1 / \\ln(\\text{editors} + 2)$ — articles with fewer active editors score higher |
| **Search intent** | $P_{si}$ | 10% | Percentile rank of the fraction of inbound Wikipedia clicks arriving from active search (Google/Bing/etc.) vs. passive internal navigation — derived from May 2026 Wikipedia clickstream data |

**Why these weights?**
The 30/25/25/10/10 split reflects the core hypothesis: public reach and content quality are equally
important for impact. Search intent provides a signal of genuine public demand that
pageviews alone cannot distinguish (a trending news article vs. a chronically under-served health topic).
""")

st.divider()

# ── Wiki Attention Score ──────────────────────────────────────────────────────
st.header("Wiki Attention Score (0–100)")
st.markdown("""
The Wiki Attention Score measures **how much momentum an article currently has** within Wikipedia
and the broader web — independent of whether it needs editing. A high attention score means the
article is actively read, trending, and well-connected within Wikipedia's link graph.

**Formula:**

$$
\\text{Attention} = \\left(P_{pv} \\times 0.45 + P_{vel} \\times 0.20 + P_{links} \\times 0.20 + P_{watch} \\times 0.10 + P_{edit} \\times 0.05\\right) \\times \\frac{100}{\\text{max}}
$$

| Component | Symbol | Weight | How it's computed |
|---|---|---|---|
| **Pageview percentile** | $P_{pv}$ | 45% | Percentile rank of 12-month pageview count |
| **Velocity** | $P_{vel}$ | 20% | Percentile rank of the ratio of recent 3-month traffic rate to the 12-month average — values above 1.0 mean the article is trending up |
| **Inbound links** | $P_{links}$ | 20% | Percentile rank of the number of other Wikipedia articles linking to this one |
| **Watchers** | $P_{watch}$ | 10% | Percentile rank of the number of editors who have this article on their watchlist |
| **Active editors** | $P_{edit}$ | 5% | Percentile rank of unique editors in the past 12 months |

The attention score is **complementary** to the impact-need score, not a substitute for it.
An article can have a high attention score (heavily read, trending) but a low impact-need score
(already well-written), or vice versa.
""")

st.divider()

# ── Medical Relevance Score ───────────────────────────────────────────────────
st.header("Medical Relevance Score (1–10)")
st.markdown("""
The Medical Relevance Score estimates **how clinically focused an article actually is**,
based on its text content — independent of how WikiProject Medicine has categorized it.
This helps distinguish genuinely clinical articles from biographical, historical, or
institutional articles that happen to fall under WikiProject Medicine's scope.

**Method:**

1. **Extract lead sections** — the opening paragraph(s) of each article are fetched via the Wikipedia API.
These are the most information-dense summary of what the article is about.

2. **Compute TF-IDF** across all 53,286 articles using unigrams and bigrams. TF-IDF scores each
term by how distinctive it is to *this* article vs. the full corpus — common terms like "treatment"
or "patients" are down-weighted; characteristic terms like "rituximab" or "myocardial" score high.

3. **Select the top 25 most characteristic terms** per article.

4. **Check against MeSH vocabulary** — the NLM 2026 MeSH descriptor file contains 61,794 terms
(descriptor names + synonyms). A TF-IDF term counts as "medical" if:
   - It exactly matches a MeSH phrase, **or**
   - Any individual word within the term appears in the MeSH word-level vocabulary
   (this handles MeSH's inverted nomenclature, e.g. "monoclonal" matches "Antibodies, Monoclonal")

5. **Score = fraction of top-25 terms matching MeSH × 10**

$$
\\text{Medical Relevance} = \\frac{N_{\\text{MeSH hits}}}{25} \\times 10
$$

**Interpretation:** A score of 8–10 indicates a highly clinical article (e.g., Rituximab = 8.8,
Rhabdomyolysis = 10). A score below 3 suggests the article's most characteristic terms are
non-medical (e.g., biographical, geographic, or historical content).
The Medical Relevance Score can be used as a filter to focus WikiMed students on articles
where their clinical knowledge will add the most value.
""")

st.divider()

# ── MeSH ID Assignment Pipeline ───────────────────────────────────────────────
st.header("MeSH ID Assignment Pipeline")
st.markdown("""
Each of the 53,286 WikiProject Medicine articles was assigned a MeSH descriptor ID (e.g. D009203)
through a **7-layer cascade pipeline**. Each layer only processes articles that the
previous layers could not confidently tag — so higher-confidence methods always take priority.
""")

layers = [
    {
        "tier": "Layer 1",
        "name": "Wikidata Structured Data",
        "confidence": "Exact",
        "icon": "🔗",
        "description": (
            "Query the Wikidata SPARQL endpoint for property **P486** (MeSH Descriptor ID) "
            "linked to each Wikipedia article. Wikidata's MeSH links are human-curated and "
            "verified — this is the gold-standard source and provides the majority of coverage."
        ),
    },
    {
        "tier": "Layer 2",
        "name": "Wikipedia Infobox Wikitext",
        "confidence": "Exact",
        "icon": "📄",
        "description": (
            "Parse raw wikitext for `MeshID=`, `mesh_heading=`, or `mesh=` fields in medical "
            "infoboxes (e.g. {{Infobox medical condition}}). Catches articles that have a "
            "MeSH ID in their infobox but haven't yet been linked in Wikidata."
        ),
    },
    {
        "tier": "Layer 3",
        "name": "MeSH Full Synonym Matching",
        "confidence": "High",
        "icon": "📖",
        "description": (
            "Match the article title against every **entry term** (synonym) across all MeSH "
            "descriptors in the NLM 2026 XML. Each descriptor has dozens of synonyms — "
            "e.g., 'Heart Attack', 'MI', and 'Myocardial Infarct' all resolve to D009203. "
            "Very low false-positive risk because matches must be exact (after normalization)."
        ),
    },
    {
        "tier": "Layer 4",
        "name": "PubMed Citation Consensus",
        "confidence": "High",
        "icon": "📚",
        "description": (
            "Wikipedia medical articles cite primary literature. NLM indexers have already "
            "tagged those papers with MeSH — so we harvest that expert work. Steps: "
            "(a) extract all PMIDs, DOIs, and PMC IDs from article wikitext; "
            "(b) resolve DOIs/PMCs to PMIDs via the NCBI ID converter; "
            "(c) fetch MeSH tags from PubMed efetch for every unique PMID; "
            "(d) vote — **major-topic citation = 2 pts, minor-topic = 1 pt**; "
            "(e) the top-scoring MeSH term is accepted if it exceeds a minimum vote "
            "threshold and has sufficient title similarity."
        ),
    },
    {
        "tier": "Layer 5",
        "name": "BioPortal NLP Annotator",
        "confidence": "Medium",
        "icon": "🧠",
        "description": (
            "Send the Wikipedia intro paragraph (first 3 sentences) to the "
            "**NCBO BioPortal Annotator**, filtered to the MESH ontology. "
            "BioPortal's NLP engine identifies medical concept spans in free text. "
            "The annotation whose matched text most closely overlaps the article title "
            "is accepted if token similarity exceeds 30%."
        ),
    },
    {
        "tier": "Layer 6",
        "name": "NCBI MeSH eSearch",
        "confidence": "Medium",
        "icon": "🔍",
        "description": (
            "Search the NCBI MeSH database directly by article title using the "
            "**E-utilities esearch API**. NCBI's MeSH index includes the full MeSH "
            "Metathesaurus with all entry terms, so this catches cases like "
            "'Heart Attack' → D009203 that pure title-matching might miss. "
            "Returned NCBI UIDs are converted to D-numbers, validated against the local "
            "MeSH XML, and scored by token similarity to the article title."
        ),
    },
    {
        "tier": "Layer 7",
        "name": "NLM Medical Text Indexer (MTI)",
        "confidence": "Lower",
        "icon": "🤖",
        "description": (
            "NLM's **Medical Text Indexer** is the same system that automatically "
            "suggests MeSH terms for PubMed submissions. Two-pass approach: "
            "**Pass 1** — submit the article title alone (low noise, fast); "
            "**Pass 2** — if Pass 1 confidence is below threshold, resubmit with "
            "title + first sentence for more context. "
            "Candidates are always scored against the original article **title** "
            "(not the submitted text) to stay on-topic. "
            "Final score = MTI confidence (0–1000) × semantic similarity to title."
        ),
    },
]

for layer in layers:
    with st.expander(f"{layer['icon']} {layer['tier']}: {layer['name']}  —  Confidence: {layer['confidence']}"):
        st.markdown(layer["description"])

st.markdown("""
**Coverage result:** Running all 7 layers across 53,286 articles achieved **~82% MeSH coverage**.
Articles that remain untagged after all layers are typically biographical, historical, or
organizational articles where no reliable MeSH descriptor exists.

Each assigned MeSH ID enables the **MeSH Tree Search** in the dashboard — when you search
for a term like "antibiotics", the search expands to all articles tagged under that branch
of the MeSH hierarchy, not just those with "antibiotic" in the title.
""")

st.divider()

# ── Cancer Article Identification ─────────────────────────────────────────────
st.header("🎗️ Cancer Article Identification")
st.markdown("""
The [Cancer Dashboard](pages/Cancer_Dashboard.py) identifies oncology-relevant Wikipedia articles
using three complementary MeSH relationship types from the NLM 2026 descriptor file, plus a
title-keyword fallback for articles without MeSH tags. Each layer captures a distinct class of
cancer content that the others would miss.
""")

st.subheader("Layer 1 — MeSH C04 Neoplasms Tree")
st.markdown("""
The NLM MeSH hierarchy places all neoplasm descriptors under tree branch **C04**.
Any article whose assigned MeSH ID has a tree number beginning with `C04` is directly
classified as a cancer article. This covers primary tumor types, histological subtypes,
and cancer-by-site classifications.

- **703 MeSH descriptors** span the full C04 subtree (e.g., C04.588.274 = Lymphoma,
  C04.557.470 = Carcinoma, C04.626 = Neoplasms by Site)
- These represent the core oncology corpus — named tumors and malignancies
""")

st.subheader("Layer 2 — Antineoplastic Drug & Protocol MeSH (PharmacologicalAction links)")
st.markdown("""
Cancer drugs like Cisplatin, Rituximab, and Tamoxifen are classified in the MeSH **D-tree**
by *chemical structure* — not by their clinical use. A Cisplatin article has MeSH ID D002945,
which sits in `D01.210` (Inorganic Chemicals), not in C04.

However, the MeSH XML encodes a separate relationship — **PharmacologicalAction** — that links
each drug to the pharmacological role it plays. Cisplatin's entry contains:

```
PharmacologicalAction → D000970: Antineoplastic Agents
```

We extract all MeSH descriptor IDs whose tree number falls under `D27.505.954.248`
(the Antineoplastic Agents pharmacological role subtree), then find every drug in the
descriptor file that lists one of those IDs as a PharmacologicalAction. This yields
**268 cancer drug descriptors** — a class of articles that a pure C04 tree search
would entirely miss.

Antineoplastic protocol entries (E-tree, `E02.319.077` and `E02.183.750`) add 2 more.
""")

st.subheader("Layer 3 — Hereditary Cancer Syndromes (C16.320.700 subtree)")
st.markdown("""
Inherited cancer predisposition syndromes — Lynch syndrome, Li-Fraumeni syndrome, hereditary
breast and ovarian cancer syndrome (BRCA1/2), Muir-Torre, Birt-Hogg-Dubé, and others — are
classified under MeSH `C16.320.700` (Neoplastic Syndromes, Hereditary), a branch of the
C16 Congenital and Hereditary Diseases tree, not C04.

Extracting this subtree adds **25 hereditary cancer syndrome descriptors** that are clinically
oncology but structurally separated from the main Neoplasms tree.
""")

st.subheader("Layer 4 — Title Keyword Fallback")
st.markdown("""
Approximately 39% of WikiProject Medicine articles have no MeSH ID assigned (see MeSH pipeline
above). For those, a keyword search over the article title catches obvious cancer content
not reachable by MeSH:

`cancer · carcinoma · tumor · tumour · malignant · malignancy · leukemia · leukaemia ·
lymphoma · sarcoma · melanoma · neoplasm · oncology · glioma · blastoma · adenoma ·
mesothelioma · myeloma · metastasis · metastatic`

This is the least precise layer and most likely to produce false positives, but it is
necessary to cover the untagged portion of the corpus.
""")

st.markdown("""
**Coverage summary by layer:**

| Layer | Source | Descriptors / Articles |
|---|---|---|
| MeSH C04 tree | Neoplasms hierarchy | 703 MeSH descriptors |
| PharmacologicalAction (D27.505.954.248) | Antineoplastic drugs | 268 drug descriptors |
| Hereditary syndromes (C16.320.700) | Inherited cancer predispositions | 25 descriptors |
| Title keyword | Untagged article fallback | Variable |

Articles matched by multiple layers are attributed to the highest-confidence source (C04 > MeSH treatment > keyword).
The match type is visible in the Cancer Dashboard table and can be filtered in the sidebar.
""")

st.divider()
st.caption("Data sources: Wikipedia API, WikiProject Medicine categories, NLM MeSH 2026, Wikipedia Clickstream (May 2026), PubMed efetch, BioPortal Annotator, NCBI eSearch, NLM MTI.")
st.page_link("pages/Home.py", label="← Back to Dashboard")
