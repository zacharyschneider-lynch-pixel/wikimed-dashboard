"""
Tier 3 MeSH enrichment: NCBI MeSH esearch.

For each article without a MeSH ID, searches the NCBI MeSH database
(eutils esearch) by article title. The NCBI MeSH database includes the
full MeSH Metathesaurus with all entry terms (synonyms), so this catches
cases like "Heart Attack" -> D009203 "Myocardial Infarction" that pure
title-matching misses.

Workflow per article:
  1. esearch db=mesh for the article title -> list of NCBI MeSH UIDs
  2. Convert NCBI UIDs to MeSH descriptor IDs (D-numbers)
  3. Validate against local desc2026.xml - confirm ID exists and get name
  4. Pick candidate with highest title/synonym similarity above threshold

No authentication required (uses free NCBI E-utilities).
Optional NCBI API key raises rate limit from 3 to 10 req/sec:
  https://www.ncbi.nlm.nih.gov/account/

Run after enrich_mesh_pubmed.py:
    python enrich_mesh_esearch.py
    python enrich_mesh_esearch.py --ncbi-key YOUR_KEY --also-upgrade
"""

import os
import re
import time
import argparse
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import xml.etree.ElementTree as ET

import requests
import pandas as pd

DATA_PATH   = "data/wikiproject_medicine.csv"
SCORED_PATH = "data/scored_articles.csv"
MESH_XML    = "data/desc2026.xml"
ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
UA          = "WikiMedDashboard/1.0 (zachary_schneider-lynch@brown.edu)"


# ── Text helpers ──────────────────────────────────────────────────────────────

def normalize(text):
    text = text.lower()
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def token_similarity(a, b):
    ta = set(normalize(a).split())
    tb = set(normalize(b).split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


# ── MeSH local index ──────────────────────────────────────────────────────────

def load_mesh(xml_path):
    """
    Returns:
      preferred:  {UI -> preferred_name}
      synonyms:   {UI -> frozenset of normalized entry terms}
    """
    print("Loading MeSH XML...")
    tree = ET.parse(xml_path)
    root = tree.getroot()
    preferred = {}
    synonyms  = {}

    for rec in root.findall("DescriptorRecord"):
        ui   = rec.findtext("DescriptorUI",       "").strip()
        name = rec.findtext("DescriptorName/String", "").strip()
        if not ui or not name:
            continue
        preferred[ui] = name
        terms = {normalize(name)}
        for el in rec.iter("Term"):
            s = el.findtext("String", "").strip()
            if s:
                terms.add(normalize(s))
        synonyms[ui] = frozenset(terms)

    print(f"  {len(preferred):,} descriptors loaded.")
    return preferred, synonyms


# ── NCBI UID -> MeSH descriptor ID ───────────────────────────────────────────

def ncbi_uid_to_mesh(ncbi_uid):
    """
    NCBI MeSH database UIDs follow the pattern: 68XXXXXX
    where XXXXXX are the 6 digits of the MeSH descriptor (D-number).
    e.g. 68009203 -> D009203 (Myocardial Infarction)
    """
    s = str(ncbi_uid)
    if s.startswith("68") and len(s) >= 7:
        return "D" + s[2:]
    return None


# ── Per-article lookup ────────────────────────────────────────────────────────

def esearch_mesh_candidates(title, preferred, synonyms, session, ncbi_key=None,
                            min_sim=0.25):
    """
    Search NCBI MeSH for the article title.
    Returns (best_mesh_id, best_name, best_sem) or (None, None, 0).
    """
    params = {
        "db":      "mesh",
        "term":    title,
        "retmax":  25,
        "retmode": "json",
    }
    if ncbi_key:
        params["api_key"] = ncbi_key

    for attempt in range(3):
        try:
            r = session.get(ESEARCH_URL, params=params, timeout=20)
            if r.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            if r.status_code != 200:
                return None, None, 0.0
            ids = r.json().get("esearchresult", {}).get("idlist", [])
            break
        except Exception:
            if attempt < 2:
                time.sleep(1)
            else:
                return None, None, 0.0
    else:
        return None, None, 0.0

    # Convert NCBI UIDs -> MeSH descriptor IDs, validate against local XML
    candidates = []
    for uid in ids:
        mesh_id = ncbi_uid_to_mesh(uid)
        if mesh_id and mesh_id in preferred:
            candidates.append(mesh_id)

    if not candidates:
        return None, None, 0.0

    # Score each candidate against the article title
    best_id, best_name, best_sem = None, None, 0.0
    for mesh_id in candidates:
        pname    = preferred[mesh_id]
        name_sim = token_similarity(title, pname)
        syn_hit  = 1.0 if normalize(title) in synonyms.get(mesh_id, frozenset()) else 0.0
        sem      = max(name_sim, syn_hit)
        if sem > best_sem:
            best_sem  = sem
            best_id   = mesh_id
            best_name = pname

    if best_sem < min_sim:
        return None, None, 0.0

    return best_id, best_name, best_sem


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ncbi-key",    default=None,
                        help="Optional NCBI API key for 10 req/sec "
                             "(https://www.ncbi.nlm.nih.gov/account/)")
    parser.add_argument("--workers",     type=int, default=3)
    parser.add_argument("--min-sim",     type=float, default=0.25,
                        help="Min title/synonym similarity to accept match (default 0.25)")
    parser.add_argument("--also-upgrade", action="store_true",
                        help="Re-process Low/Broad confidence matches too")
    args = parser.parse_args()

    preferred, synonyms = load_mesh(MESH_XML)

    df = pd.read_csv(DATA_PATH)
    print(f"\nLoaded {len(df):,} articles.")

    no_mesh = df["mesh_id"].isna()
    if args.also_upgrade and "mesh_confidence" in df.columns:
        low_broad = df["mesh_confidence"].isin(["Low", "Broad"])
        todo_mask = no_mesh | low_broad
        print(f"Targets: {no_mesh.sum():,} no-MeSH + {low_broad.sum():,} Low/Broad "
              f"= {todo_mask.sum():,} total")
    else:
        todo_mask = no_mesh
        print(f"Targets: {no_mesh.sum():,} articles with no MeSH ID")

    todo_titles = df[todo_mask]["title"].tolist()
    if not todo_titles:
        print("Nothing to do.")
        return

    # Rate limit: 3/sec without key, 10/sec with key
    min_gap = 0.11 if args.ncbi_key else 0.35

    idx_by_title = {row["title"]: i for i, row in df.iterrows()}
    lock         = threading.Lock()
    completed    = [0]
    new_hits     = [0]
    upgrades     = [0]

    def worker(title):
        s = requests.Session()
        s.headers["User-Agent"] = UA
        time.sleep(min_gap)
        return title, *esearch_mesh_candidates(
            title, preferred, synonyms, s, args.ncbi_key, args.min_sim
        )

    print(f"\nProcessing {len(todo_titles):,} articles ({args.workers} workers)...\n")

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(worker, t): t for t in todo_titles}

        for future in as_completed(futures):
            title = futures[future]
            try:
                _, mesh_id, mesh_name, sem = future.result()
                idx = idx_by_title[title]

                with lock:
                    old_id = df.at[idx, "mesh_id"] if pd.notna(df.at[idx, "mesh_id"]) else None
                    if mesh_id:
                        if not old_id:
                            new_hits[0] += 1
                        else:
                            upgrades[0] += 1
                        df.at[idx, "mesh_id"] = mesh_id

                    completed[0] += 1
                    if completed[0] % 200 == 0:
                        df.to_csv(DATA_PATH, index=False)
                        pct = completed[0] / len(todo_titles) * 100
                        print(f"  [{completed[0]:,}/{len(todo_titles):,}  {pct:.0f}%]  "
                              f"+{new_hits[0]:,} new  +{upgrades[0]:,} upgraded  "
                              f"(checkpoint saved)", flush=True)

            except Exception as e:
                print(f"  Error on {title!r}: {e}")

    df.to_csv(DATA_PATH, index=False)
    after = df["mesh_id"].notna().sum()
    print(f"\n{'='*55}")
    print(f"New MeSH assignments:  {new_hits[0]:,}")
    print(f"Confidence upgrades:   {upgrades[0]:,}")
    print(f"Coverage now:          {after:,} / {len(df):,} ({after/len(df)*100:.1f}%)")

    if os.path.exists(SCORED_PATH):
        scored = pd.read_csv(SCORED_PATH)
        scored = scored.drop(columns=["mesh_id"], errors="ignore")
        scored = scored.merge(df[["title", "mesh_id"]], on="title", how="left")
        scored.to_csv(SCORED_PATH, index=False)
        print(f"Updated {SCORED_PATH}")

    print("\nDone. Run validate_mesh.py to refresh confidence scores.")


if __name__ == "__main__":
    main()
