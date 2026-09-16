"""
fetch_is_biography.py
---------------------
Flags Wikipedia articles that are biographies, using Wikipedia's own category
system, and writes an `is_biography` column back to scored_articles.csv.

Why this is needed
------------------
The MeSH assignment pipeline matches article titles against MeSH descriptor
names and synonyms. Surnames collide with eponymous syndromes, so biographies
acquire clinical MeSH IDs they have nothing to do with:

    Li Zhaoping, Li Lianda, Li Jieshou, Li Huanying, Li Sijin, Li Zhisui,
    Zihai Li            -> D016864  Li-Fraumeni Syndrome
    Lydia Lynch         -> D055847  (Lynch syndrome / HNPCC)
    John Henry Wishart  -> D016518  (Wishart -> neurofibromatosis type II)

These then surface as recommended articles and distort corpus statistics —
Joseph Merrick (tagged D009456, neurofibromatosis) draws ~598,000 views a year,
more than any genuine article in the precision oncology subset.

Detection
---------
Wikipedia places every biography in dated birth/death categories and living
subjects in "Living people". Checking for those is far more reliable than name
heuristics, and costs one batched API call per 50 titles.

Usage:
    python fetch_is_biography.py                 # whole corpus
    python fetch_is_biography.py --resume        # only rows not yet flagged
    python fetch_is_biography.py --titles-from data/po_articles.csv
"""

import argparse
import re
import time

import pandas as pd
import requests

DATA_PATH  = "data/scored_articles.csv"
BATCH_SIZE = 50
DELAY      = 0.5

HEADERS = {
    "User-Agent": (
        "WikiMedDashboard/1.0 "
        "(Brown University SC-HIA research; zachary_schneider-lynch@brown.edu)"
    )
}

BIO_CATEGORY = re.compile(r"^Category:(Living people|\d{1,4}s? (?:births|deaths))", re.I)


def fetch_batch(titles: list[str]) -> dict[str, bool]:
    """Return {title: is_biography} for up to 50 titles.

    The categories API caps how many category rows one response carries across
    all requested pages, so a 50-title batch is routinely truncated and returns
    partial category lists. Ignoring the continuation token silently produces
    false negatives — biographies whose birth/death category fell past the cut.
    This follows `clcontinue` until the batch is complete.
    """
    params = {
        "action": "query",
        "prop": "categories",
        "cllimit": "max",
        "titles": "|".join(titles),
        "format": "json",
        "formatversion": "2",
    }

    norm: dict[str, str] = {}
    cats_by_page: dict[str, list[str]] = {}

    while True:
        r = requests.get("https://en.wikipedia.org/w/api.php",
                         params=params, headers=HEADERS, timeout=30)
        r.raise_for_status()
        data = r.json()

        for e in data.get("query", {}).get("normalized", []):
            norm[e["from"]] = e["to"]
        for page in data.get("query", {}).get("pages", []):
            cats_by_page.setdefault(page["title"], []).extend(
                c["title"] for c in page.get("categories", [])
            )

        cont = data.get("continue")
        if not cont:
            break
        params.update(cont)
        time.sleep(0.1)

    by_canonical = {
        title: any(BIO_CATEGORY.match(c) for c in cats)
        for title, cats in cats_by_page.items()
    }
    return {t: by_canonical.get(norm.get(t, t), False) for t in titles}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--resume", action="store_true",
                    help="Skip rows that already have an is_biography value.")
    ap.add_argument("--titles-from",
                    help="CSV with a 'title' column; flag only those titles.")
    args = ap.parse_args()

    print(f"Loading {DATA_PATH} ...")
    df = pd.read_csv(DATA_PATH)
    if "is_biography" not in df.columns:
        df["is_biography"] = pd.NA

    if args.titles_from:
        wanted = set(pd.read_csv(args.titles_from)["title"])
        mask = df["title"].isin(wanted)
        print(f"Restricted to {int(mask.sum()):,} titles from {args.titles_from}")
    else:
        mask = pd.Series(True, index=df.index)
    if args.resume:
        mask &= df["is_biography"].isna()

    titles = df.loc[mask, "title"].tolist()
    total = len(titles)
    if total == 0:
        print("Nothing to do.")
        return

    print(f"Checking {total:,} articles for biography categories ...")
    n_bio = 0
    n_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE

    for i, start in enumerate(range(0, total, BATCH_SIZE), 1):
        batch = titles[start:start + BATCH_SIZE]
        try:
            res = fetch_batch(batch)
        except requests.RequestException as exc:
            print(f"\n  Batch {i}/{n_batches} failed: {exc}. Retrying once ...")
            time.sleep(2)
            try:
                res = fetch_batch(batch)
            except requests.RequestException as exc2:
                print(f"  Batch {i}/{n_batches} failed again: {exc2}. Skipping.")
                continue

        for title, is_bio in res.items():
            df.loc[df["title"] == title, "is_biography"] = bool(is_bio)
            n_bio += bool(is_bio)

        print(f"\r  Batch {i:>4}/{n_batches}  biographies found: {n_bio}",
              end="", flush=True)
        if i < n_batches:
            time.sleep(DELAY)

    print(f"\n\nFlagged {n_bio:,} biographies out of {total:,} checked.")
    df.to_csv(DATA_PATH, index=False)
    print(f"Saved to {DATA_PATH}")

    flagged = df[df["is_biography"] == True]          # noqa: E712
    if len(flagged):
        print("\nHighest-traffic biographies found:")
        cols = [c for c in ["title", "mesh_id", "pageviews_12mo"] if c in flagged.columns]
        print(flagged.nlargest(min(15, len(flagged)), "pageviews_12mo")[cols].to_string(index=False))


if __name__ == "__main__":
    main()
