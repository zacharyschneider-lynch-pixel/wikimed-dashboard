"""
Tier 2 MeSH enrichment: BioPortal Annotator API.

For each article still missing a MeSH ID, this script:
  1. Fetches the Wikipedia intro paragraph (plain text) via the MediaWiki API.
  2. Sends it to the BioPortal Annotator filtered to the MESH ontology.
  3. Selects the best-matching MeSH descriptor, preferring terms whose
     preferred name most closely matches the article title.

Requires a free BioPortal API key:
  https://bioportal.bioontology.org/account

Pass key via --api-key or set env var BIOPORTAL_API_KEY.

Run after enrich_mesh_synonyms.py:
    python enrich_mesh_bioportal.py --api-key YOUR_KEY

Resume-safe: skips articles already assigned a MeSH ID.
"""

import os
import re
import time
import math
import argparse
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import pandas as pd

UA = "WikiMedDashboard/1.0 (zachary_schneider-lynch@brown.edu)"
BIOPORTAL_URL = "https://data.bioontology.org/annotator"

DATA_PATH   = "data/wikiproject_medicine.csv"
SCORED_PATH = "data/scored_articles.csv"

_local = threading.local()


def get_session():
    if not hasattr(_local, "session"):
        _local.session = requests.Session()
        _local.session.headers.update({"User-Agent": UA})
    return _local.session


# ── Helpers ───────────────────────────────────────────────────────────────────

def normalize(text):
    text = text.lower()
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def title_similarity(a, b):
    """Simple token overlap ratio between two normalized strings."""
    ta = set(normalize(a).split())
    tb = set(normalize(b).split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


# ── Phase 1: fetch Wikipedia intro extracts ──────────────────────────────────

def fetch_extracts_batch(titles):
    """Return {title: intro_text} for up to 20 titles."""
    r = get_session().get("https://en.wikipedia.org/w/api.php", params={
        "action": "query",
        "prop": "extracts",
        "titles": "|".join(titles),
        "exintro": True,
        "explaintext": True,
        "exsentences": 3,       # first 3 sentences is plenty for annotation
        "format": "json",
    }, timeout=30)
    result = {}
    for page in r.json()["query"]["pages"].values():
        title = page.get("title", "")
        extract = page.get("extract", "").strip()
        if extract:
            result[title] = extract
    return result


def collect_extracts(titles, batch_size=20):
    """Batch-fetch Wikipedia intro text for all titles."""
    extracts = {}
    batches = [titles[i:i+batch_size] for i in range(0, len(titles), batch_size)]
    for i, batch in enumerate(batches):
        try:
            extracts.update(fetch_extracts_batch(batch))
        except Exception as e:
            print(f"  Extract error batch {i}: {e}")
        if i % 50 == 0 and i > 0:
            print(f"  Extracts: {min((i+1)*batch_size, len(titles)):,}/{len(titles):,}", flush=True)
        time.sleep(0.2)
    return extracts


# ── Phase 2: BioPortal annotator ─────────────────────────────────────────────

def annotate(text, api_key, retries=3):
    """
    Call BioPortal annotator for the given text, return list of
    {mesh_id, preferred_name} dicts (MESH ontology only).
    """
    for attempt in range(retries):
        try:
            r = requests.post(
                BIOPORTAL_URL,
                data={
                    "text": text[:2000],        # cap at 2000 chars
                    "ontologies": "MESH",
                    "whole_word_only": "true",
                    "apikey": api_key,
                },
                timeout=30,
            )
            if r.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            if r.status_code != 200:
                return []
            annotations = r.json()
            results = []
            seen = set()
            for ann in annotations:
                cls_id = ann.get("annotatedClass", {}).get("@id", "")
                # URI looks like: http://purl.bioontology.org/ontology/MESH/D009203
                mesh_id = cls_id.split("/")[-1]
                if not re.match(r'^[DC]\d+', mesh_id):
                    continue
                # prefLabel is not returned inline — use the matched text instead.
                # This is the span of the article text that triggered the annotation,
                # which is what we want to compare against the article title anyway.
                ann_spans = ann.get("annotations", [])
                matched_text = ann_spans[0]["text"] if ann_spans else ""
                if mesh_id not in seen:
                    seen.add(mesh_id)
                    results.append({"mesh_id": mesh_id, "preferred_name": matched_text})
            return results
        except Exception:
            if attempt < retries - 1:
                time.sleep(1)
    return []


def best_mesh_for_article(title, text, api_key):
    """
    Annotate article text, then pick the MeSH term whose preferred name
    most closely matches the article title. Returns (mesh_id, score) or
    (None, 0) if no confident match.
    """
    candidates = annotate(text, api_key)
    if not candidates:
        return None, 0.0

    best_id, best_score = None, 0.0
    for c in candidates:
        score = title_similarity(title, c["preferred_name"])
        if score > best_score:
            best_score = score
            best_id = c["mesh_id"]

    # Require at least 30% token overlap to accept the match
    if best_score < 0.30:
        return None, best_score

    return best_id, best_score


def process_article(title, text, api_key):
    mesh_id, score = best_mesh_for_article(title, text, api_key)
    time.sleep(0.15)        # ~6-7 req/s per worker, well within BioPortal limits
    return title, mesh_id, score


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="BioPortal MeSH annotation")
    parser.add_argument("--api-key",  default=os.environ.get("BIOPORTAL_API_KEY", ""),
                        help="BioPortal API key (or set BIOPORTAL_API_KEY env var)")
    parser.add_argument("--workers",  type=int, default=6)
    parser.add_argument("--min-score", type=float, default=0.30,
                        help="Minimum title-similarity score to accept a match (default 0.30)")
    args = parser.parse_args()

    if not args.api_key:
        print("ERROR: BioPortal API key required.")
        print("  Get a free key at https://bioportal.bioontology.org/account")
        print("  Then run: python enrich_mesh_bioportal.py --api-key YOUR_KEY")
        return

    df = pd.read_csv(DATA_PATH)
    print(f"Loaded {len(df):,} articles.")

    before = df["mesh_id"].notna().sum()
    print(f"MeSH coverage before: {before:,} ({before/len(df)*100:.1f}%)")

    missing = df[df["mesh_id"].isna()]["title"].tolist()
    print(f"Articles needing annotation: {len(missing):,}\n")

    if not missing:
        print("Nothing to do.")
        return

    # Phase 1: fetch Wikipedia intro text
    print("[Phase 1] Fetching Wikipedia intro extracts...")
    extracts = collect_extracts(missing)
    print(f"  Got extracts for {len(extracts):,}/{len(missing):,} articles.\n")

    # Phase 2: annotate with BioPortal
    print(f"[Phase 2] Annotating with BioPortal ({args.workers} workers)...")
    lock = threading.Lock()
    completed = [0]
    new_hits   = [0]

    # Build title->index map for fast updates
    idx_by_title = {row["title"]: i for i, row in df.iterrows()}

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(process_article, title, extracts.get(title, title), args.api_key): title
            for title in missing
        }
        for future in as_completed(futures):
            title = futures[future]
            try:
                _, mesh_id, score = future.result()
                with lock:
                    if mesh_id:
                        df.at[idx_by_title[title], "mesh_id"] = mesh_id
                        new_hits[0] += 1
                    completed[0] += 1
                    if completed[0] % 200 == 0:
                        df.to_csv(DATA_PATH, index=False)
                        print(f"  [{completed[0]:,}/{len(missing):,}] "
                              f"+{new_hits[0]:,} new matches (checkpoint saved)", flush=True)
            except Exception as e:
                print(f"  Error on {title}: {e}")

    # Final save
    df.to_csv(DATA_PATH, index=False)
    after = df["mesh_id"].notna().sum()
    print(f"\nNew matches via BioPortal: {new_hits[0]:,}")
    print(f"MeSH coverage after: {after:,} ({after/len(df)*100:.1f}%)")

    if os.path.exists(SCORED_PATH):
        scored = pd.read_csv(SCORED_PATH)
        scored = scored.drop(columns=["mesh_id"], errors="ignore")
        scored = scored.merge(df[["title", "mesh_id"]], on="title", how="left")
        scored.to_csv(SCORED_PATH, index=False)
        print(f"Updated {SCORED_PATH}")

    print("\nDone. Reload the dashboard to see updated MeSH coverage.")


if __name__ == "__main__":
    main()
