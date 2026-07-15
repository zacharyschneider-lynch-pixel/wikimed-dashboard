"""
WikiMed article metadata scraper.

Pipeline
--------
Phase 1  Get article titles + quality class from quality-specific categories
Phase 2  Get importance labels from importance-specific categories
Phase 3  Batch-fetch Talk page info (watchers) — 50 articles per API call
Phase 4  Batch-fetch article info (byte length) — 50 articles per API call
Phase 5  Per-article: pageviews (12mo) + unique editors (12mo)

Resume   Completed titles are tracked in the output CSV; re-running skips them.
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

# Main-thread session (used for phases 1–4)
S = requests.Session()
S.headers.update({"User-Agent": UA})

# Thread-local sessions for Phase 5 workers
_local = threading.local()

def get_session():
    if not hasattr(_local, "session"):
        _local.session = requests.Session()
        _local.session.headers.update({"User-Agent": UA})
    return _local.session

QUALITY_CATEGORIES = {
    "FA":    "Category:FA-Class_medicine_articles",
    "GA":    "Category:GA-Class_medicine_articles",
    "B":     "Category:B-Class_medicine_articles",
    "C":     "Category:C-Class_medicine_articles",
    "Start": "Category:Start-Class_medicine_articles",
    "Stub":  "Category:Stub-Class_medicine_articles",
}
IMPORTANCE_CATEGORIES = {
    "Top":  "Category:Top-importance_medicine_articles",
    "High": "Category:High-importance_medicine_articles",
    "Mid":  "Category:Mid-importance_medicine_articles",
    "Low":  "Category:Low-importance_medicine_articles",
}
QUALITY_MAP    = {"FA": 1, "GA": 1, "B": 2, "C": 3, "Start": 4, "Stub": 5}
IMPORTANCE_MAP = {"Top": 4, "High": 3, "Mid": 2, "Low": 1}

FIELDNAMES = [
    "title", "quality_class", "quality_deficit",
    "importance_label", "importance_rating",
    "watchers", "article_bytes",
    "pageviews_12mo", "unique_editors", "editor_scarcity",
]


# ── Helpers ──────────────────────────────────────────────────────────────────

def date_range_12mo():
    end   = datetime.now()
    start = end - timedelta(days=365)
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def iso(yyyymmdd):
    return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:]}T00:00:00Z"


def chunked(iterable, n):
    it = iter(iterable)
    while True:
        chunk = list(islice(it, n))
        if not chunk:
            break
        yield chunk


def paginate_category(cat_title):
    """Yield all Talk-namespace titles in a category."""
    params = {
        "action": "query",
        "list": "categorymembers",
        "cmtitle": cat_title,
        "cmlimit": "500",
        "cmnamespace": "1",
        "format": "json",
    }
    while True:
        data = S.get("https://en.wikipedia.org/w/api.php", params=params).json()
        for m in data["query"]["categorymembers"]:
            yield m["title"].replace("Talk:", "")
        if "continue" not in data:
            break
        params["cmcontinue"] = data["continue"]["cmcontinue"]
        time.sleep(0.3)


# ── Phase 1: article list with quality ───────────────────────────────────────

def collect_article_quality(sample=None, quality_filter=None):
    article_quality = {}
    cats = {k: v for k, v in QUALITY_CATEGORIES.items()
            if quality_filter is None or k in quality_filter}
    for quality, cat in cats.items():
        print(f"  Fetching {quality} articles from {cat}...")
        count = 0
        for title in paginate_category(cat):
            article_quality[title] = quality
            count += 1
            if sample and count >= sample:
                break
    return article_quality


# ── Phase 2: importance from importance categories ────────────────────────────

def collect_importance():
    importance = {}
    for label, cat in IMPORTANCE_CATEGORIES.items():
        print(f"  Fetching {label}-importance articles...")
        for title in paginate_category(cat):
            importance[title] = label
    return importance


# ── Phase 3: batch Talk page info (watchers) ──────────────────────────────────

def fetch_watchers_batch(titles):
    """Return {title: watcher_count} for up to 50 titles."""
    talk_titles = [f"Talk:{t}" for t in titles]
    data = S.get("https://en.wikipedia.org/w/api.php", params={
        "action": "query",
        "prop": "info",
        "titles": "|".join(talk_titles),
        "inprop": "watchers",
        "format": "json",
    }).json()
    result = {}
    for page in data["query"]["pages"].values():
        raw = page.get("title", "").replace("Talk:", "")
        result[raw] = page.get("watchers")
    return result


# ── Phase 4: batch article info (byte length) ─────────────────────────────────

def fetch_bytes_batch(titles):
    """Return {title: byte_length} for up to 50 titles."""
    data = S.get("https://en.wikipedia.org/w/api.php", params={
        "action": "query",
        "prop": "info",
        "titles": "|".join(titles),
        "format": "json",
    }).json()
    result = {}
    for page in data["query"]["pages"].values():
        result[page.get("title", "")] = page.get("length")
    return result


# ── Phase 5: per-article pageviews + editors ──────────────────────────────────

def fetch_pageviews(title, start_date, end_date):
    safe = title.replace(" ", "_")
    try:
        pv = requests.get(
            f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
            f"en.wikipedia/all-access/user/{safe}/monthly/{start_date}/{end_date}",
            headers={"User-Agent": "WikiMedDashboard/1.0"},
            timeout=15,
        ).json()
        return sum(item["views"] for item in pv.get("items", []))
    except Exception:
        return None


def fetch_unique_editors(title, start_date, end_date):
    try:
        rev_page = list(get_session().get("https://en.wikipedia.org/w/api.php", params={
            "action": "query", "prop": "revisions", "titles": title,
            "rvprop": "user", "rvlimit": "500",
            "rvstart": iso(start_date), "rvend": iso(end_date),
            "rvdir": "newer", "format": "json",
        }).json()["query"]["pages"].values())[0]
        revisions = rev_page.get("revisions", [])
        return len(set(r["user"] for r in revisions))
    except Exception:
        return None


def fetch_article_data(title, start_date, end_date, article_quality, article_importance,
                       watchers_map, bytes_map):
    """Fetch pageviews + editors for one article and return the complete row dict."""
    quality    = article_quality.get(title)
    importance = article_importance.get(title)
    editors    = fetch_unique_editors(title, start_date, end_date)
    pageviews  = fetch_pageviews(title, start_date, end_date)
    return {
        "title":             title,
        "quality_class":     quality,
        "quality_deficit":   QUALITY_MAP.get(quality),
        "importance_label":  importance,
        "importance_rating": IMPORTANCE_MAP.get(importance),
        "watchers":          watchers_map.get(title),
        "article_bytes":     bytes_map.get(title),
        "pageviews_12mo":    pageviews,
        "unique_editors":    editors,
        "editor_scarcity":   round(1 / math.log(editors + 2), 4) if editors is not None else None,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Collect WikiProject Medicine metadata")
    parser.add_argument("--sample", type=int, default=None,
                        help="Limit to first N articles per quality class (omit for all ~53k)")
    parser.add_argument("--quality", nargs="+", default=None,
                        metavar="CLASS",
                        help="Only collect these quality classes, e.g. --quality C Start Stub")
    parser.add_argument("--workers", type=int, default=8,
                        help="Parallel workers for Phase 5 (default: 8)")
    parser.add_argument("--output", default="data/wikiproject_medicine.csv")
    args = parser.parse_args()

    outdir = os.path.dirname(args.output)
    if outdir:
        os.makedirs(outdir, exist_ok=True)

    start_date, end_date = date_range_12mo()
    print(f"Date window: {start_date} to {end_date}")

    # Resume: load already-completed titles
    done = set()
    file_exists = os.path.exists(args.output)
    if file_exists:
        with open(args.output, newline="", encoding="utf-8") as f:
            done = {row["title"] for row in csv.DictReader(f)}
        print(f"Resuming: {len(done):,} articles already collected.")

    # Phase 1: article list + quality
    print("\n[Phase 1] Collecting article list + quality from categories...")
    article_quality = collect_article_quality(sample=args.sample, quality_filter=args.quality)
    articles = list(article_quality.keys())
    print(f"  Total unique articles: {len(articles):,}")

    # Phase 2: importance
    print("\n[Phase 2] Collecting importance ratings from categories...")
    article_importance = collect_importance()
    print(f"  Importance data for {len(article_importance):,} articles.")

    # Determine what still needs per-article data
    todo = [a for a in articles if a not in done]
    print(f"\n{len(todo):,} articles need per-article data ({len(done):,} skipped).")

    if not todo:
        print("Nothing to do. Exiting.")
        return

    # Pre-fetch batch data for todo articles
    print("\n[Phase 3] Batch-fetching watcher counts...")
    watchers_map = {}
    for i, batch in enumerate(chunked(todo, 50)):
        watchers_map.update(fetch_watchers_batch(batch))
        if i % 20 == 0:
            print(f"  {min((i + 1) * 50, len(todo)):,}/{len(todo):,}")
        time.sleep(0.3)

    print("\n[Phase 4] Batch-fetching article byte lengths...")
    bytes_map = {}
    for i, batch in enumerate(chunked(todo, 50)):
        bytes_map.update(fetch_bytes_batch(batch))
        if i % 20 == 0:
            print(f"  {min((i + 1) * 50, len(todo)):,}/{len(todo):,}")
        time.sleep(0.3)

    # Phase 5: per-article pageviews + editors (parallel)
    print(f"\n[Phase 5] Fetching pageviews and editor counts ({args.workers} workers)...")
    mode = "a" if file_exists else "w"
    write_lock = threading.Lock()
    completed  = [0]  # list so the closure can mutate it

    with open(args.output, mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {
                pool.submit(
                    fetch_article_data,
                    title, start_date, end_date,
                    article_quality, article_importance,
                    watchers_map, bytes_map,
                ): title
                for title in todo
            }

            for future in as_completed(futures):
                title = futures[future]
                try:
                    row = future.result()
                    with write_lock:
                        writer.writerow(row)
                        f.flush()
                        completed[0] += 1
                        if completed[0] % 100 == 0:
                            print(f"  [{completed[0]:,}/{len(todo):,}]")
                except Exception as e:
                    print(f"  Error on {title}: {e}")

    print(f"\nDone. {completed[0]:,} articles saved to {args.output}")


if __name__ == "__main__":
    main()
