"""
Summarise the filtered Wikipedia clickstream into per-article signals
for use in scoring.py.

Signals computed per article:
  search_arrivals   — clicks arriving from search / external (active intent)
  internal_arrivals — clicks arriving via internal Wikipedia links
  total_inbound     — total inbound clicks
  search_pct        — fraction of inbound clicks from search (0–1)
  med_outbound      — clicks sent to OTHER WikiProject Medicine articles
                      (measures stepping-stone importance in the med. graph)

Output: data/clickstream_signals.csv

Run after build_clickstream.py:
    python build_clickstream_signals.py
"""

import pandas as pd

CS_PATH  = "data/clickstream_medicine.tsv"
MED_PATH = "data/wikiproject_medicine.csv"
OUT_PATH = "data/clickstream_signals.csv"

SEARCH_TYPES = {"other-search", "other-external", "other-empty"}

cs  = pd.read_csv(CS_PATH, sep="\t", dtype={"n": int})
med = pd.read_csv(MED_PATH)

# Build title lookup: underscore ↔ space
space_titles  = set(med["title"])
under_to_space = {t.replace(" ", "_"): t for t in space_titles}
med_under      = set(under_to_space.keys())

def to_space(t):
    return under_to_space.get(t, t.replace("_", " "))

# ── Inbound signals (curr = this article) ────────────────────────────────────
inbound = cs[cs["curr"].isin(med_under)].copy()

search_in   = (inbound[inbound["prev"].isin(SEARCH_TYPES)]
               .groupby("curr")["n"].sum()
               .rename("search_arrivals"))

internal_in = (inbound[~inbound["prev"].isin(SEARCH_TYPES)]
               .groupby("curr")["n"].sum()
               .rename("internal_arrivals"))

total_in    = (inbound.groupby("curr")["n"].sum()
               .rename("total_inbound"))

# ── Outbound to other medicine articles (prev = this article) ─────────────────
med_out = (cs[(cs["prev"].isin(med_under)) &
              (cs["curr"].isin(med_under)) &
              (cs["prev"] != cs["curr"])]
           .groupby("prev")["n"].sum()
           .rename("med_outbound"))

# ── Combine ───────────────────────────────────────────────────────────────────
signals = (pd.concat([search_in, internal_in, total_in, med_out], axis=1)
           .fillna(0)
           .astype(int)
           .reset_index()
           .rename(columns={"index": "title_under", "curr": "title_under"}))

# Convert underscore titles back to space form
signals["title"] = signals["title_under"].apply(to_space)
signals = signals.drop(columns=["title_under"])

signals["search_pct"] = (
    signals["search_arrivals"] / signals["total_inbound"].clip(lower=1)
).round(4)

# Reorder
signals = signals[["title", "search_arrivals", "internal_arrivals",
                   "total_inbound", "search_pct", "med_outbound"]]

signals.to_csv(OUT_PATH, index=False)

print(f"Saved {len(signals):,} article signals to {OUT_PATH}")
print()
print(f"Articles with any inbound clicks:  {(signals['total_inbound'] > 0).sum():,}")
print(f"Articles with search arrivals:     {(signals['search_arrivals'] > 0).sum():,}")
print(f"Articles as stepping stones:       {(signals['med_outbound'] > 0).sum():,}")
print()
print("Top 10 by search arrivals:")
print(signals.nlargest(10, "search_arrivals")
      [["title","search_arrivals","search_pct","med_outbound"]].to_string(index=False))
print()
print("Top 10 by med_outbound (stepping stones):")
print(signals.nlargest(10, "med_outbound")
      [["title","med_outbound","search_arrivals","total_inbound"]].to_string(index=False))
