"""
Validate MeSH ID assignments across all three enrichment layers.

For every article with a MeSH ID, computes:
  mesh_preferred_name   — human-readable MeSH concept name
  title_mesh_similarity — token overlap between article title and preferred name (0-1)
  mesh_tree_depth       — specificity of the MeSH term (deeper = more specific)
  mesh_confidence       — High / Medium / Low / Broad flag

Outputs:
  data/mesh_validation_metrics.csv  — full metrics for all matched articles
  data/mesh_validation_sample.csv   — 100-article spot-check for manual review
"""

import os
import re
import xml.etree.ElementTree as ET
import pandas as pd

MESH_XML_PATH = "data/desc2026.xml"
SCORED_PATH   = "data/scored_articles.csv"
DATA_PATH     = "data/wikiproject_medicine.csv"


def normalize(text):
    text = text.lower()
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    return set(re.sub(r"\s+", " ", text).strip().split())


def token_similarity(a, b):
    ta, tb = normalize(a), normalize(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def load_mesh_lookup(xml_path):
    """
    Parse desc2026.xml and return two dicts:
      preferred: {descriptor_UI -> preferred_name}
      tree_depth: {descriptor_UI -> max_tree_depth}
    """
    print("Parsing MeSH XML for validation...")
    tree = ET.parse(xml_path)
    root = tree.getroot()

    preferred   = {}
    tree_depth  = {}

    for record in root.findall("DescriptorRecord"):
        ui   = record.findtext("DescriptorUI", "").strip()
        name = record.findtext("DescriptorName/String", "").strip()
        if not ui or not name:
            continue
        preferred[ui] = name

        # Tree numbers look like C14.280.238.984 — depth = number of segments
        depths = []
        for tn in record.iter("TreeNumber"):
            parts = tn.text.strip().split(".")
            depths.append(len(parts))
        tree_depth[ui] = max(depths) if depths else 0

    print(f"  Loaded {len(preferred):,} descriptors.")
    return preferred, tree_depth


def confidence_label(similarity, depth):
    """Assign a confidence tier based on title similarity and MeSH specificity."""
    if depth <= 1:
        return "Broad"
    if depth == 2 and similarity < 0.4:
        return "Broad"
    if similarity >= 0.6 and depth >= 3:
        return "High"
    if similarity >= 0.3 and depth >= 3:
        return "Medium"
    if similarity >= 0.3 and depth == 2:
        return "Medium"
    return "Low"


def main():
    if not os.path.exists(MESH_XML_PATH):
        print(f"ERROR: {MESH_XML_PATH} not found. Run enrich_mesh_synonyms.py first.")
        return

    preferred, tree_depth = load_mesh_lookup(MESH_XML_PATH)

    df = pd.read_csv(SCORED_PATH)
    matched = df[df["mesh_id"].notna()].copy()
    print(f"\nArticles with MeSH IDs: {len(matched):,} / {len(df):,}")

    # Compute validation metrics
    matched["mesh_preferred_name"] = matched["mesh_id"].map(preferred)
    matched["title_mesh_similarity"] = matched.apply(
        lambda r: token_similarity(str(r["title"]), str(r["mesh_preferred_name"] or "")),
        axis=1
    ).round(3)
    matched["mesh_tree_depth"] = matched["mesh_id"].map(tree_depth).fillna(0).astype(int)
    matched["mesh_confidence"] = matched.apply(
        lambda r: confidence_label(r["title_mesh_similarity"], r["mesh_tree_depth"]),
        axis=1
    )

    # Summary
    print("\nConfidence distribution:")
    counts = matched["mesh_confidence"].value_counts()
    for label in ["High", "Medium", "Low", "Broad"]:
        n = counts.get(label, 0)
        print(f"  {label:8s}: {n:6,}  ({n/len(matched)*100:.1f}%)")

    print("\nMean tree depth by confidence:")
    print(matched.groupby("mesh_confidence")["mesh_tree_depth"].mean().round(2).to_string())

    print("\nSample of LOW confidence matches (likely problems):")
    low = matched[matched["mesh_confidence"] == "Low"].nsmallest(15, "title_mesh_similarity")
    for _, r in low.iterrows():
        print(f"  {r['title']!r:45s} -> {r['mesh_id']}  {r['mesh_preferred_name']!r}  "
              f"(sim={r['title_mesh_similarity']:.2f}, depth={r['mesh_tree_depth']})")

    print("\nSample of BROAD matches:")
    broad = matched[matched["mesh_confidence"] == "Broad"].head(10)
    for _, r in broad.iterrows():
        print(f"  {r['title']!r:45s} -> {r['mesh_id']}  {r['mesh_preferred_name']!r}  "
              f"(depth={r['mesh_tree_depth']})")

    # Save full metrics
    metrics_cols = ["rank", "title", "mesh_id", "mesh_preferred_name",
                    "title_mesh_similarity", "mesh_tree_depth", "mesh_confidence",
                    "quality_class", "importance_label", "pageviews_12mo"]
    metrics_df = matched[[c for c in metrics_cols if c in matched.columns]].copy()
    metrics_df.to_csv("data/mesh_validation_metrics.csv", index=False)
    print(f"\nSaved full metrics to data/mesh_validation_metrics.csv")

    # Stratified spot-check sample (25 per confidence tier)
    sample_parts = []
    for label in ["High", "Medium", "Low", "Broad"]:
        tier = matched[matched["mesh_confidence"] == label]
        n = min(25, len(tier))
        sample_parts.append(tier.sample(n, random_state=42))
    sample = pd.concat(sample_parts).sort_values("mesh_confidence")

    sample_cols = ["title", "mesh_id", "mesh_preferred_name", "title_mesh_similarity",
                   "mesh_tree_depth", "mesh_confidence", "quality_class",
                   "importance_label", "pageviews_12mo"]
    sample_df = sample[[c for c in sample_cols if c in sample.columns]].copy()
    sample_df["correct_yn"] = ""   # blank column for reviewer to fill in
    sample_df["reviewer_notes"] = ""
    sample_df.to_csv("data/mesh_validation_sample.csv", index=False)
    print(f"Saved {len(sample_df)}-article spot-check to data/mesh_validation_sample.csv")

    # Update scored_articles.csv with confidence metrics
    for col in ["mesh_preferred_name", "title_mesh_similarity", "mesh_tree_depth", "mesh_confidence"]:
        df = df.drop(columns=[col], errors="ignore")
        df = df.merge(matched[["title", col]], on="title", how="left")
    df.to_csv(SCORED_PATH, index=False)
    print(f"Updated {SCORED_PATH} with validation columns.")
    print("\nDone.")


if __name__ == "__main__":
    main()
