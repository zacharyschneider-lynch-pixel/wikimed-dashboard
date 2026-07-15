"""
Refetch pageviews and editor counts for articles where those values are missing.

Reads the existing wikiproject_medicine.csv, identifies rows with null
pageviews_12mo or null unique_editors, re-fetches them with retry logic and
gentler concurrency, then overwrites the CSV with the completed data.
"""

import pandas as pd
import requests
import math
import time
import argparse
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

UA = "WikiMedDashboard/1.0 (zachary_schneider-lynch@brown.edu)"

_local = threading.local()

def get_session():
    if not hasattr(_local, "session"):
        _local.session = requests.Session()
        _local.session.headers.update({"User-Agent": UA})
    return _local.session


def fetch_pageviews(title, start_date, end_date, retries=3):
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


def fetch_unique_editors(title, start_date, end_date, retries=3):
    def iso(d):
        return f"{d[:4]}-{d[4:6]}-{d[6:]}T00:00:00Z"
    for attempt in range(retries):
        try:
            rev_page = list(get_session().get("https://en.wikipedia.org/w/api.php", params={
                "action": "query", "prop": "revisions", "titles": title,
                "rvprop": "user", "rvlimit": "500",
                "rvstart": iso(start_date), "rvend": iso(end_date),
                "rvdir": "newer", "format": "json",
            }, timeout=20).json()["query"]["pages"].values())[0]
            revisions = rev_page.get("revisions", [])
            return len(set(r["user"] for r in revisions))
        except Exception:
            if attempt < retries - 1:
                time.sleep(1)
    return None


def refetch_row(row, start_date, end_date, need_pv, need_ed):
    title = row["title"]
    result = {}
    if need_pv:
        result["pageviews_12mo"] = fetch_pageviews(title, start_date, end_date)
    if need_ed:
        editors = fetch_unique_editors(title, start_date, end_date)
        result["unique_editors"] = editors
        result["editor_scarcity"] = (
            round(1 / math.log(editors + 2), 4) if editors is not None else None
        )
    time.sleep(0.15)
    return title, result


def main():
    parser = argparse.ArgumentParser(description="Refetch missing pageviews and editors")
    parser.add_argument("--input",   default="data/wikiproject_medicine.csv")
    parser.add_argument("--start",   default="20250602", help="Pageview window start YYYYMMDD")
    parser.add_argument("--end",     default="20260602", help="Pageview window end YYYYMMDD")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    df = pd.read_csv(args.input)
    print(f"Loaded {len(df):,} articles.")

    need_pv = df["pageviews_12mo"].isna()
    need_ed = df["unique_editors"].isna()
    todo_mask = need_pv | need_ed
    todo_df = df[todo_mask].copy()

    print(f"Missing pageviews:  {need_pv.sum():,}")
    print(f"Missing editors:    {need_ed.sum():,}")
    print(f"Articles to refetch: {len(todo_df):,}  ({args.workers} workers)\n")

    if len(todo_df) == 0:
        print("Nothing to refetch.")
        return

    # Build lookup for fast row updates
    idx_by_title = {row["title"]: i for i, row in df.iterrows()}
    lock = threading.Lock()
    completed = [0]

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(
                refetch_row,
                row, args.start, args.end,
                need_pv[i], need_ed[i],
            ): row["title"]
            for i, row in todo_df.iterrows()
        }

        for future in as_completed(futures):
            title = futures[future]
            try:
                _, updates = future.result()
                idx = idx_by_title[title]
                with lock:
                    for col, val in updates.items():
                        df.at[idx, col] = val
                    completed[0] += 1
                    if completed[0] % 100 == 0:
                        df.to_csv(args.input, index=False)
                        print(f"  [{completed[0]:,}/{len(todo_df):,}] checkpoint saved", flush=True)
            except Exception as e:
                print(f"  Error on {title}: {e}")

    df.to_csv(args.input, index=False)
    still_missing_pv = df["pageviews_12mo"].isna().sum()
    still_missing_ed = df["unique_editors"].isna().sum()
    print(f"\nDone. Still missing — pageviews: {still_missing_pv:,}  editors: {still_missing_ed:,}")
    print(f"Saved to {args.input}")


if __name__ == "__main__":
    main()
