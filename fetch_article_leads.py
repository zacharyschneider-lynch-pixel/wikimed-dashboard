"""
Fetch the lead section (intro paragraph) for every WikiProject Medicine article
via the Wikipedia extracts API. Saves to data/article_leads.csv.

Supports resume — skips titles already in the output file.

Run time: ~5 minutes for 53k articles.
"""

import os
import time
import requests
import pandas as pd

API   = "https://en.wikipedia.org/w/api.php"
UA    = "WikiMedDashboard/1.0 (zachary_schneider-lynch@brown.edu)"
SRC   = "data/wikiproject_medicine.csv"
OUT   = "data/article_leads.csv"
BATCH = 20

df     = pd.read_csv(SRC)
titles = df["title"].tolist()

if os.path.exists(OUT):
    done   = set(pd.read_csv(OUT)["title"])
    titles = [t for t in titles if t not in done]
    mode, header = "a", False
    print(f"Resuming — {len(done):,} already fetched, {len(titles):,} remaining.")
else:
    mode, header = "w", True
    print(f"Fetching lead sections for {len(titles):,} articles...")

session = requests.Session()
session.headers["User-Agent"] = UA

start = time.time()
fetched = 0

for i in range(0, len(titles), BATCH):
    batch = titles[i : i + BATCH]
    params = {
        "action":      "query",
        "prop":        "extracts",
        "exintro":     1,
        "explaintext": 1,
        "exlimit":     BATCH,
        "titles":      "|".join(batch),
        "format":      "json",
        "formatversion": 2,
    }
    try:
        r = session.get(API, params=params, timeout=30)
        r.raise_for_status()
        pages = r.json()["query"]["pages"]
        rows  = [{"title": p["title"], "lead": p.get("extract", "")} for p in pages]
        pd.DataFrame(rows).to_csv(OUT, mode=mode, header=header, index=False)
        mode, header = "a", False
        fetched += len(rows)
    except Exception as e:
        print(f"  Error at batch {i}: {e} — skipping")

    if fetched % 5000 < BATCH:
        elapsed = time.time() - start
        rate    = fetched / elapsed if elapsed > 0 else 0
        remaining = len(titles) - i - BATCH
        eta = remaining / (rate * BATCH) if rate > 0 else 0
        print(f"  {fetched:,} fetched  |  {elapsed:.0f}s elapsed  |  ETA ~{eta:.0f}s", flush=True)

    time.sleep(0.1)

print(f"\nDone. {fetched:,} lead sections saved to {OUT}")
