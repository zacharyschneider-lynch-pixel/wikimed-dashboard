"""
Tier 1 MeSH enrichment: match Wikipedia article titles against all MeSH entry
terms (synonyms), not just preferred descriptor names.

NLM publishes the full descriptor XML at:
  https://nlmpubs.nlm.nih.gov/projects/mesh/MESH_FILES/xmlmesh/desc2025.xml

Each MeSH descriptor has a preferred name plus dozens of entry terms (e.g.,
"Heart Attack", "MI", and "Myocardial Infarct" all map to D009203).
Matching against the full synonym set meaningfully increases coverage with
very low false-positive risk.

Run after enrich_mesh.py:
    python enrich_mesh_synonyms.py
"""

import os
import re
import xml.etree.ElementTree as ET
import pandas as pd
import requests

MESH_XML_URL  = "https://nlmpubs.nlm.nih.gov/projects/mesh/MESH_FILES/xmlmesh/desc2026.xml"
MESH_XML_PATH = "data/desc2026.xml"
DATA_PATH     = "data/wikiproject_medicine.csv"
SCORED_PATH   = "data/scored_articles.csv"

UA = "WikiMedDashboard/1.0 (zachary_schneider-lynch@brown.edu)"


# ── Helpers ───────────────────────────────────────────────────────────────────

def normalize(text):
    """Lowercase, collapse whitespace, strip non-alphanumeric except spaces."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def download_mesh_xml():
    print(f"Downloading MeSH descriptor XML (~300 MB) from NLM...")
    os.makedirs("data", exist_ok=True)
    with requests.get(MESH_XML_URL, headers={"User-Agent": UA}, stream=True, timeout=120) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        downloaded = 0
        with open(MESH_XML_PATH, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):  # 1 MB chunks
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded / total * 100
                    print(f"  {pct:.0f}%  ({downloaded // (1 << 20)} MB)", end="\r", flush=True)
    print(f"\nSaved to {MESH_XML_PATH}")


def build_entry_term_lookup(xml_path):
    """
    Parse MeSH descriptor XML and return:
      lookup: {normalized_entry_term -> descriptor_UI}
      preferred: {descriptor_UI -> preferred_name}
    """
    print("Parsing MeSH XML (this takes ~30 s)...")
    tree = ET.parse(xml_path)
    root = tree.getroot()

    lookup    = {}   # normalized term -> UI
    preferred = {}   # UI -> preferred name

    for record in root.findall("DescriptorRecord"):
        ui   = record.findtext("DescriptorUI", "").strip()
        name = record.findtext("DescriptorName/String", "").strip()
        if not ui or not name:
            continue

        preferred[ui] = name

        # Collect every term string across all concepts
        all_terms = set()
        all_terms.add(name)
        for term_el in record.iter("Term"):
            s = term_el.findtext("String", "").strip()
            if s:
                all_terms.add(s)

        for term in all_terms:
            key = normalize(term)
            if key and key not in lookup:   # first match wins (preferred name takes priority)
                lookup[key] = ui

    print(f"  Built lookup with {len(lookup):,} normalized entry terms across {len(preferred):,} descriptors.")
    return lookup, preferred


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # 1. Download XML if not cached
    if not os.path.exists(MESH_XML_PATH):
        download_mesh_xml()
    else:
        size_mb = os.path.getsize(MESH_XML_PATH) / (1 << 20)
        print(f"Using cached MeSH XML ({size_mb:.0f} MB) at {MESH_XML_PATH}")

    # 2. Build entry-term lookup
    lookup, preferred = build_entry_term_lookup(MESH_XML_PATH)

    # 3. Load article data
    df = pd.read_csv(DATA_PATH)
    print(f"\nLoaded {len(df):,} articles from {DATA_PATH}")

    before = df["mesh_id"].notna().sum()
    print(f"MeSH coverage before: {before:,} ({before/len(df)*100:.1f}%)")

    # 4. Match titles for articles still missing a MeSH ID
    missing = df["mesh_id"].isna()
    new_hits = 0
    for idx, row in df[missing].iterrows():
        key = normalize(row["title"])
        if key in lookup:
            df.at[idx, "mesh_id"] = lookup[key]
            new_hits += 1

    after = df["mesh_id"].notna().sum()
    print(f"\nNew matches via entry terms: {new_hits:,}")
    print(f"MeSH coverage after:  {after:,} ({after/len(df)*100:.1f}%)")

    # 5. Show sample of new matches
    newly_matched = df[missing & df["mesh_id"].notna()].head(20)
    if not newly_matched.empty:
        print("\nSample new matches:")
        for _, r in newly_matched.iterrows():
            print(f"  {r['title']!r:50s} -> {r['mesh_id']}  ({preferred.get(r['mesh_id'], '?')})")

    # 6. Save
    df.to_csv(DATA_PATH, index=False)
    print(f"\nSaved enriched data to {DATA_PATH}")

    if os.path.exists(SCORED_PATH):
        scored = pd.read_csv(SCORED_PATH)
        scored = scored.drop(columns=["mesh_id"], errors="ignore")
        scored = scored.merge(df[["title", "mesh_id"]], on="title", how="left")
        scored.to_csv(SCORED_PATH, index=False)
        print(f"Updated {SCORED_PATH}")

    print("\nDone. Reload the dashboard to see updated MeSH coverage.")


if __name__ == "__main__":
    main()
