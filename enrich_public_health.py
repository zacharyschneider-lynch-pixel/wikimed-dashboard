"""
Public health enrichment — adds three equity-focused columns to the dataset:

  reading_level   — Flesch-Kincaid Grade Level of the article intro
                    (higher = harder to read; average US adult reads at ~8th grade)
  is_rare_disease — True if article is in Wikipedia's rare disease categories
  rare_disease_source — which category matched (for transparency)

Run after enrich_mesh_synonyms.py:
    python enrich_public_health.py
"""

import os
import time
import threading
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from itertools import islice

import requests
import pandas as pd
import textstat

UA  = "WikiMedDashboard/1.0 (zachary_schneider-lynch@brown.edu)"
API = "https://en.wikipedia.org/w/api.php"

DATA_PATH   = "data/wikiproject_medicine.csv"
SCORED_PATH = "data/scored_articles.csv"

_local = threading.local()

def get_session():
    if not hasattr(_local, "session"):
        _local.session = requests.Session()
        _local.session.headers.update({"User-Agent": UA})
    return _local.session


def chunked(iterable, n):
    it = iter(iterable)
    while True:
        chunk = list(islice(it, n))
        if not chunk:
            break
        yield chunk


# ── Phase 1: rare disease flag from Wikipedia categories ─────────────────────

RARE_CATEGORIES = [
    "Category:Rare diseases",
    "Category:Rare infectious diseases",
    "Category:Rare genetic disorders",
    "Category:Rare cancers",
    "Category:Rare syndromes",
    "Category:Rare neurological disorders",
    "Category:Rare endocrine disorders",
    "Category:Rare metabolic disorders",
    "Category:Rare cardiovascular diseases",
    "Category:Rare respiratory diseases",
    "Category:Rare skin conditions",
    "Category:Rare kidney diseases",
    "Category:Rare autoimmune diseases",
]

def paginate_category_articles(cat_title):
    """Yield article titles (ns=0) in a category."""
    params = {
        "action": "query", "list": "categorymembers",
        "cmtitle": cat_title, "cmlimit": "500",
        "cmnamespace": "0", "format": "json",
    }
    S = get_session()
    while True:
        data = S.get(API, params=params, timeout=30).json()
        for m in data["query"]["categorymembers"]:
            yield m["title"]
        if "continue" not in data:
            break
        params["cmcontinue"] = data["continue"]["cmcontinue"]
        time.sleep(0.2)


def collect_rare_diseases():
    """Return {title: source_category} for all rare disease articles."""
    rare_map = {}
    for cat in RARE_CATEGORIES:
        label = cat.replace("Category:", "")
        print(f"  {label} ...", flush=True)
        try:
            for title in paginate_category_articles(cat):
                if title not in rare_map:
                    rare_map[title] = label
        except Exception as e:
            print(f"    Error: {e}")
        time.sleep(0.3)
    return rare_map


# ── Phase 2: reading level from Wikipedia intro extracts ─────────────────────

def fetch_extracts_batch(titles, retries=3):
    """Return {title: plain_text_intro} for up to 20 titles."""
    for attempt in range(retries):
        try:
            r = get_session().get(API, params={
                "action": "query",
                "prop": "extracts",
                "titles": "|".join(titles),
                "exintro": True,
                "explaintext": True,
                "exsentences": 10,
                "format": "json",
            }, timeout=30)
            data = r.json()
            result = {}
            for page in data["query"]["pages"].values():
                title   = page.get("title", "")
                extract = page.get("extract", "").strip()
                if extract:
                    result[title] = extract
            return result
        except Exception:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    return {}


def compute_reading_level(text):
    """Flesch-Kincaid Grade Level, rounded to 1 decimal. Returns None if text too short."""
    words = text.split()
    if len(words) < 30:
        return None
    return round(textstat.flesch_kincaid_grade(text), 1)


def collect_reading_levels(titles, workers=3):
    """Batch-fetch extracts then compute FK grade level per article."""
    reading_map = {}
    batches = list(chunked(titles, 20))
    lock = threading.Lock()
    done = [0]

    def process_batch(batch):
        extracts = fetch_extracts_batch(batch)
        results  = {}
        for title, text in extracts.items():
            results[title] = compute_reading_level(text)
        time.sleep(0.5)
        return results

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(process_batch, batch): batch for batch in batches}
        for future in as_completed(futures):
            result = future.result()
            with lock:
                reading_map.update(result)
                done[0] += len(futures[future])
                if done[0] % 5000 == 0:
                    print(f"  Reading level: {done[0]:,}/{len(titles):,}", flush=True)

    return reading_map


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data",   default=DATA_PATH)
    parser.add_argument("--scored", default=SCORED_PATH)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--skip-reading-level", action="store_true")
    args = parser.parse_args()

    df = pd.read_csv(args.data)
    print(f"Loaded {len(df):,} articles.\n")

    # Phase 1: rare disease flag
    print("[Phase 1] Collecting rare disease categories from Wikipedia...")
    rare_map = collect_rare_diseases()
    df["is_rare_disease"]    = df["title"].map(lambda t: t in rare_map)
    df["rare_disease_source"] = df["title"].map(rare_map)
    rare_count = df["is_rare_disease"].sum()
    print(f"  Flagged {rare_count:,} rare disease articles ({rare_count/len(df)*100:.1f}%)\n")

    # Phase 2: reading level (resume-safe — skip articles already scored)
    if not args.skip_reading_level:
        already_done = set(df[df["reading_level"].notna()]["title"]) if "reading_level" in df.columns else set()
        todo_titles  = [t for t in df["title"].tolist() if t not in already_done]
        print(f"[Phase 2] Computing reading levels ({args.workers} workers)...")
        if already_done:
            print(f"  Resuming: {len(already_done):,} already done, {len(todo_titles):,} remaining.")
        reading_map = collect_reading_levels(todo_titles, workers=args.workers)
        for title, rl in reading_map.items():
            df.loc[df["title"] == title, "reading_level"] = rl
        scored = df["reading_level"].notna().sum()
        avg    = df["reading_level"].mean()
        print(f"  Reading level computed for {scored:,} articles. Mean grade level: {avg:.1f}\n")
    else:
        print("[Phase 2] Skipped reading level (--skip-reading-level flag).\n")

    # Save
    df.to_csv(args.data, index=False)
    print(f"Saved to {args.data}")

    if os.path.exists(args.scored):
        scored_df = pd.read_csv(args.scored)
        for col in ["is_rare_disease", "rare_disease_source", "reading_level"]:
            if col in df.columns:
                scored_df = scored_df.drop(columns=[col], errors="ignore")
                scored_df = scored_df.merge(df[["title", col]], on="title", how="left")
        scored_df.to_csv(args.scored, index=False)
        print(f"Updated {args.scored}")

    print("\nDone. Reload the dashboard to see the new equity columns.")


if __name__ == "__main__":
    main()
