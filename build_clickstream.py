"""
Download the Wikipedia clickstream dump, filter to WikiProject Medicine
articles, and save the subset locally.

Two-step: download .tsv.gz to disk, then filter. More reliable than
streaming a 508 MB file in one SSL connection.

Output: data/clickstream_medicine.tsv
"""

import gzip
import os
import time
import requests
import pandas as pd

URL       = "https://dumps.wikimedia.org/other/clickstream/2026-05/clickstream-enwiki-2026-05.tsv.gz"
GZ_PATH   = "data/clickstream_enwiki_2026-05.tsv.gz"
OUT_PATH  = "data/clickstream_medicine.tsv"
DATA_CSV  = "data/wikiproject_medicine.csv"
UA        = "WikiMedDashboard/1.0 (zachary_schneider-lynch@brown.edu)"
CHUNK     = 4 * 1024 * 1024  # 4 MB chunks

# ── Step 1: download ──────────────────────────────────────────────────────────

TOTAL_BYTES = 532_540_000  # ~508 MB

def download_with_resume(url, dest, ua, chunk=CHUNK):
    s = requests.Session()
    s.headers["User-Agent"] = ua
    start = time.time()

    while True:
        existing = os.path.getsize(dest) if os.path.exists(dest) else 0
        if existing >= TOTAL_BYTES * 0.99:
            print(f"Already complete: {dest} ({existing/1e6:.0f} MB)")
            return

        headers = {"Range": f"bytes={existing}-"} if existing else {}
        mode    = "ab" if existing else "wb"
        print(f"Downloading from byte {existing/1e6:.0f} MB ...", flush=True)

        try:
            with s.get(url, stream=True, timeout=120, headers=headers) as resp:
                resp.raise_for_status()
                downloaded = existing
                with open(dest, mode) as f:
                    for chunk_data in resp.iter_content(chunk_size=chunk):
                        f.write(chunk_data)
                        downloaded += len(chunk_data)
                        if downloaded % (50 * 1024 * 1024) < chunk:
                            print(f"  {downloaded/1e6:.0f}/{TOTAL_BYTES/1e6:.0f} MB  "
                                  f"({downloaded/TOTAL_BYTES*100:.0f}%)  "
                                  f"{time.time()-start:.0f}s", flush=True)
            print(f"Download complete: {downloaded/1e6:.0f} MB", flush=True)
            return
        except Exception as e:
            saved = os.path.getsize(dest) if os.path.exists(dest) else 0
            if "416" in str(e):
                print(f"File already complete ({saved/1e6:.0f} MB).", flush=True)
                return
            print(f"Connection dropped at {saved/1e6:.0f} MB — retrying in 5s... ({e})",
                  flush=True)
            time.sleep(5)

download_with_resume(URL, GZ_PATH, UA)

# ── Step 2: filter ────────────────────────────────────────────────────────────

df = pd.read_csv(DATA_CSV)
# Clickstream uses underscores for spaces — build both lookup sets
medicine_titles_space = set(df["title"].tolist())
medicine_titles_under = {t.replace(" ", "_") for t in medicine_titles_space}
medicine_titles = medicine_titles_space | medicine_titles_under
print(f"\nLoaded {len(medicine_titles_space):,} WikiProject Medicine titles "
      f"({len(medicine_titles):,} with underscore variants).")
print(f"Filtering {GZ_PATH}...")

rows_seen = 0
rows_kept = 0
start = time.time()

with gzip.open(GZ_PATH, "rt", encoding="utf-8") as gz:
    with open(OUT_PATH, "w", encoding="utf-8") as out:
        out.write("prev\tcurr\ttype\tn\n")
        for line in gz:
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 4:
                continue
            rows_seen += 1
            prev, curr, typ, n = parts
            if curr in medicine_titles or prev in medicine_titles:
                out.write(line)
                rows_kept += 1
            if rows_seen % 10_000_000 == 0:
                print(f"  {rows_seen/1e6:.0f}M rows  {rows_kept:,} kept  "
                      f"{time.time()-start:.0f}s", flush=True)

print(f"\nDone in {time.time()-start:.0f}s")
print(f"Rows scanned: {rows_seen:,}")
print(f"Rows kept:    {rows_kept:,}")
print(f"Saved:        {OUT_PATH}  "
      f"({os.path.getsize(OUT_PATH)/1e6:.1f} MB)")
