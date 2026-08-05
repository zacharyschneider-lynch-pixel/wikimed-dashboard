"""
fetch_protection.py
-------------------
Fetches Wikipedia article protection status for all articles in scored_articles.csv
and writes two new columns back to the CSV:

  is_fully_protected  — bool: edit-protected to sysop (admin) level only. Students cannot edit.
  is_semi_protected   — bool: edit-protected to autoconfirmed level. Students can edit after
                        their account is ≥4 days old with ≥10 edits (~first week of a course).

Fully protected articles are excluded from dashboard recommendations entirely.
Semi-protected articles are flagged with a 🔒 badge but still shown.

Usage:
    python fetch_protection.py
    python fetch_protection.py --resume   # skip titles that already have a non-null value

Wikipedia API: https://en.wikipedia.org/w/api.php?action=query&prop=info&inprop=protection
Batch size: 50 titles per request (API limit).
Rate: ~0.5 s delay between batches to stay well under the API rate limit.
"""

import argparse
import time
import sys

import pandas as pd
import requests

DATA_PATH = "data/scored_articles.csv"
BATCH_SIZE = 50
DELAY = 0.5  # seconds between batches

HEADERS = {
    "User-Agent": (
        "WikiMedDashboard/1.0 "
        "(Brown University SC-HIA research; zachary_schneider-lynch@brown.edu)"
    )
}


def fetch_batch(titles: list[str]) -> dict[str, tuple[bool, bool]]:
    """
    Query the Wikipedia API for protection status of up to 50 titles.
    Returns {title: (is_fully_protected, is_semi_protected)}.
    """
    params = {
        "action":    "query",
        "prop":      "info",
        "inprop":    "protection",
        "titles":    "|".join(titles),
        "format":    "json",
        "formatversion": "2",
    }
    r = requests.get(
        "https://en.wikipedia.org/w/api.php",
        params=params,
        headers=HEADERS,
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()

    # Wikipedia may normalize titles (e.g. lowercase first letter, spaces → underscores).
    # Build a map from the input form back to the canonical form.
    norm_map: dict[str, str] = {}
    for entry in data.get("query", {}).get("normalized", []):
        norm_map[entry["from"]] = entry["to"]

    prot_by_canonical: dict[str, tuple[bool, bool]] = {}
    for page in data.get("query", {}).get("pages", []):
        canonical = page["title"]
        protection = page.get("protection", [])
        edit_levels = {p["level"] for p in protection if p.get("type") == "edit"}
        is_full = "sysop" in edit_levels
        is_semi = "autoconfirmed" in edit_levels and not is_full
        prot_by_canonical[canonical] = (is_full, is_semi)

    results: dict[str, tuple[bool, bool]] = {}
    for t in titles:
        canonical = norm_map.get(t, t)
        results[t] = prot_by_canonical.get(canonical, (False, False))

    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--resume", action="store_true",
        help="Skip rows that already have a non-null is_fully_protected value."
    )
    args = parser.parse_args()

    print(f"Loading {DATA_PATH} …")
    df = pd.read_csv(DATA_PATH)

    # Initialise columns if absent
    if "is_fully_protected" not in df.columns:
        df["is_fully_protected"] = pd.NA
    if "is_semi_protected" not in df.columns:
        df["is_semi_protected"] = pd.NA

    # Decide which rows to process
    if args.resume:
        todo_mask = df["is_fully_protected"].isna()
        print(f"Resume mode: {todo_mask.sum():,} titles still need fetching.")
    else:
        todo_mask = pd.Series(True, index=df.index)
        print(f"Full run: fetching protection status for {len(df):,} articles.")

    titles = df.loc[todo_mask, "title"].tolist()
    total  = len(titles)

    if total == 0:
        print("Nothing to do.")
        return

    n_full = 0
    n_semi = 0
    n_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_num, start in enumerate(range(0, total, BATCH_SIZE), 1):
        batch = titles[start : start + BATCH_SIZE]

        try:
            results = fetch_batch(batch)
        except requests.RequestException as exc:
            print(f"\n  ⚠ Batch {batch_num}/{n_batches} failed: {exc}. Retrying once…")
            time.sleep(2)
            try:
                results = fetch_batch(batch)
            except requests.RequestException as exc2:
                print(f"  ✗ Batch {batch_num}/{n_batches} failed again: {exc2}. Skipping.")
                continue

        for title, (is_full, is_semi) in results.items():
            mask = df["title"] == title
            df.loc[mask, "is_fully_protected"] = is_full
            df.loc[mask, "is_semi_protected"]  = is_semi
            if is_full: n_full += 1
            if is_semi: n_semi += 1

        pct = (batch_num / n_batches) * 100
        processed = min(start + BATCH_SIZE, total)
        print(
            f"\r  Batch {batch_num:>4}/{n_batches}  "
            f"({processed:>6,}/{total:,} titles, {pct:.0f}%)  "
            f"full={n_full}  semi={n_semi}",
            end="", flush=True,
        )

        if batch_num < n_batches:
            time.sleep(DELAY)

    print(f"\n\nDone. Fully protected: {n_full:,}  Semi-protected: {n_semi:,}")

    # Fill any remaining NAs (articles that weren't queried) with False
    df["is_fully_protected"] = df["is_fully_protected"].fillna(False).astype(bool)
    df["is_semi_protected"]  = df["is_semi_protected"].fillna(False).astype(bool)

    df.to_csv(DATA_PATH, index=False)
    print(f"Saved to {DATA_PATH}")


if __name__ == "__main__":
    main()
