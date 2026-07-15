"""
Build TF-IDF corpus from article lead sections and score each article's
medical relevance: what fraction of its most characteristic terms appear
in the MeSH vocabulary.

Inputs:
  data/article_leads.csv   — from fetch_article_leads.py
  data/desc2026.xml        — MeSH descriptor file

Output:
  data/tfidf_signals.csv   — one row per article:
    title, medical_relevance (0-1), top_tfidf_terms (pipe-separated)

Run after fetch_article_leads.py:
    python build_tfidf_medical.py
"""

import xml.etree.ElementTree as ET
import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

LEADS_PATH  = "data/article_leads.csv"
MESH_PATH   = "data/desc2026.xml"
OUT_PATH    = "data/tfidf_signals.csv"
TOP_N       = 25   # top TF-IDF terms to examine per article

# ── Build MeSH vocabulary ─────────────────────────────────────────────────────
print("Loading MeSH vocabulary...", flush=True)
tree = ET.parse(MESH_PATH)
root = tree.getroot()
mesh_vocab = set()

for desc in root.findall("DescriptorRecord"):
    name = desc.findtext("DescriptorName/String", "")
    if name:
        mesh_vocab.add(name.lower())
    for concept in desc.findall("ConceptList/Concept"):
        cname = concept.findtext("ConceptName/String", "")
        if cname:
            mesh_vocab.add(cname.lower())

print(f"MeSH vocabulary: {len(mesh_vocab):,} terms (descriptors + synonyms)")

# Also build a word-level set — MeSH uses inverted forms like "Antibodies, Monoclonal"
# so "monoclonal antibody" won't exact-match, but "monoclonal" will hit the word set.
mesh_words = {
    word
    for term in mesh_vocab
    for word in term.split()
    if len(word) > 3
}
print(f"MeSH word-level tokens: {len(mesh_words):,}")

# ── Load article leads ────────────────────────────────────────────────────────
print("Loading article leads...", flush=True)
leads  = pd.read_csv(LEADS_PATH)
leads["lead"] = leads["lead"].fillna("")
print(f"Articles loaded: {len(leads):,}")

# ── Fit TF-IDF ───────────────────────────────────────────────────────────────
print("Fitting TF-IDF (unigrams + bigrams)...", flush=True)
vectorizer = TfidfVectorizer(
    max_features=100_000,
    stop_words="english",
    ngram_range=(1, 2),   # bigrams catch "blood pressure", "heart failure"
    min_df=3,             # ignore terms appearing in fewer than 3 articles
    max_df=0.90,          # ignore terms appearing in >90% of articles
    sublinear_tf=True,    # apply log(1+tf) to dampen high counts
)
tfidf_matrix = vectorizer.fit_transform(leads["lead"])
feature_names = vectorizer.get_feature_names_out()
print(f"Vocabulary size: {len(feature_names):,} terms")

# ── Score medical relevance per article ───────────────────────────────────────
print("Scoring medical relevance...", flush=True)
rows = []

for i in range(len(leads)):
    # Work on the sparse row directly — avoid densifying the full matrix
    row        = tfidf_matrix.getrow(i)
    cx         = row.tocoo()
    if cx.nnz == 0:
        top_terms = []
    else:
        order     = cx.data.argsort()[-TOP_N:][::-1]
        top_terms = [feature_names[cx.col[j]] for j in order]

    def is_medical(term):
        # Exact phrase match OR any constituent word hits the MeSH word set
        return term in mesh_vocab or any(w in mesh_words for w in term.split())

    med_hits   = sum(1 for t in top_terms if is_medical(t))
    med_rel    = round(med_hits / len(top_terms), 4) if top_terms else 0.0

    rows.append({
        "title":              leads["title"].iloc[i],
        "medical_relevance":  med_rel,
        "top_tfidf_terms":    "|".join(top_terms[:10]),
    })

out = pd.DataFrame(rows)
out.to_csv(OUT_PATH, index=False)

# ── Summary stats ─────────────────────────────────────────────────────────────
print(f"\nSaved {len(out):,} articles to {OUT_PATH}")
print()
print("Medical relevance distribution:")
bins = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.01]
labels = ["0-10%","10-20%","20-30%","30-40%","40-50%",
          "50-60%","60-70%","70-80%","80-90%","90-100%"]
out["band"] = pd.cut(out["medical_relevance"], bins=bins, labels=labels, right=False)
print(out["band"].value_counts().sort_index().to_string())
print()
print("Lowest medical relevance (likely non-clinical articles):")
print(out.nsmallest(10, "medical_relevance")[["title","medical_relevance","top_tfidf_terms"]].to_string(index=False))
print()
print("Highest medical relevance:")
print(out.nlargest(10, "medical_relevance")[["title","medical_relevance","top_tfidf_terms"]].to_string(index=False))
