"""
Fetch two additional attention signals needed for the Wiki Attention Score:

  inbound_links  — count of mainspace Wikipedia articles linking to this article
                   (capped at 500 per call; sufficient for percentile ranking)
  pageviews_3mo  — pageviews over the most recent 3 months (used to compute velocity)

Run after wiki_scraper.py:
    python fetch_attention.py

Resume-safe: skips articles already recorded in the output CSV.
"""

import requests
import csv
import time
import math
import argparse
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from itertools import islice

UA = "WikiMedDashboard/1.0 (zachary_schneider-lynch@brown.edu)"

S = requests.Session()
S.headers.update({"User-Agent": UA})

_local = threading.local()

def get_session():
    if not hasattr(_local, "session"):
        _local.session = requests.Session()
        _local.session.headers.update({"User-Agent": UA})
    return _local.session


FIELDNAMES = ["title", "inbound_links", "pageviews_3mo"]


def chunked(iterable, n):
    it = iter(iterable)
    while True:
        chunk = list(islice(it, n))
        if not chunk:
            break
        yield chunk


def date_range_3mo():
    end   = datetime.now()
    start = end - timedelta(days=90)
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


# ── Phase 1: inbound wikilinks (batched, 5 articles per call) ────────────────

def fetch_inbound_links_batch(titles):
    """Return {title: link_count} for up to 5 titles."""
    data = S.get("https://en.wikipedia.org/w/api.php", params={
        "action": "query",
        "prop": "linkshere",
        "titles": "|".join(titles),
        "lhnamespace": "0",
        "lhlimit": "500",
        "format": "json",
    }).json()
    result = {}
    for page in data["query"]["pages"].values():
        title = page.get("title", "")
        links = page.get("linkshere", [])
        # If there's a continuation for this page, count is 500+; treat as 500
        result[title] = len(links)
    return result


def collect_inbound_links(titles):
    """Batch-fetch inbound link counts for all titles."""
    link_map = {}
    batches = list(chunked(titles, 5))
    for i, batch in enumerate(batches):
        try:
            link_map.update(fetch_inbound_links_batch(batch))
        except Exception as e:
            print(f"  Error on batch {i}: {e}")
        if i % 200 == 0:
            print(f"  {min((i+1)*5, len(titles)):,}/{len(titles):,}", flush=True)
        time.sleep(0.3)
    return link_map


# ── Phase 2: 3-month pageviews (per-article, threaded) ───────────────────────

def fetch_pageviews_3mo(title, start_date, end_date, retries=3):
    safe = title.replace(" ", "_")
    url = (
        f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
        f"en.wikipedia/all-access/user/{safe}/monthly/{start_date}/{end_date}"
    )
    for attempt in range(retries):
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=20)
            if r.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            data = r.json()
            return sum(item["views"] for item in data.get("items", []))
        except Exception:
            if attempt < retries - 1:
                time.sleep(1)
    return None


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Fetch inbound links + 3-month pageviews")
    parser.add_argument("--input",   default="data/wikiproject_medicine.csv")
    parser.add_argument("--output",  default="data/attention_signals.csv")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    import pandas as pd
    df = pd.read_csv(args.input)
    all_titles = df["title"].tolist()
    print(f"Loaded {len(all_titles):,} articles.\n")

    # Resume: skip titles already in output
    done = set()
    file_exists = os.path.exists(args.output)
    if file_exists:
        with open(args.output, newline="", encoding="utf-8") as f:
            done = {row["title"] for row in csv.DictReader(f)}
        print(f"Resuming: {len(done):,} articles already done.")

    todo = [t for t in all_titles if t not in done]
    print(f"{len(todo):,} articles to process.\n")

    if not todo:
        print("Nothing to do.")
        return

    # Phase 1: inbound links (batched, main thread)
    print("[Phase 1] Fetching inbound wikilink counts (batched)...")
    link_map = collect_inbound_links(todo)
    print(f"  Done. Got link counts for {len(link_map):,} articles.\n")

    # Phase 2: 3-month pageviews (threaded)
    start_3mo, end_3mo = date_range_3mo()
    print(f"[Phase 2] Fetching 3-month pageviews ({start_3mo} to {end_3mo}, {args.workers} workers)...")

    write_lock = threading.Lock()
    completed  = [0]

    mode = "a" if file_exists else "w"
    with open(args.output, mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {
                pool.submit(fetch_pageviews_3mo, title, start_3mo, end_3mo): title
                for title in todo
            }
            for future in as_completed(futures):
                title = futures[future]
                try:
                    pv3 = future.result()
                    row = {
                        "title":         title,
                        "inbound_links": link_map.get(title),
                        "pageviews_3mo": pv3,
                    }
                    with write_lock:
                        writer.writerow(row)
                        f.flush()
                        completed[0] += 1
                        if completed[0] % 500 == 0:
                            print(f"  [{completed[0]:,}/{len(todo):,}]", flush=True)
                except Exception as e:
                    print(f"  Error on {title}: {e}")

    print(f"\nDone. {completed[0]:,} articles saved to {args.output}")


if __name__ == "__main__":
    main()
