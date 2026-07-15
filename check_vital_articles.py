"""
Check how many of the top-100 Impact-Need-scored articles are also
listed as Wikipedia Vital Articles (a cross-project editorial list,
independent of WikiProject Medicine quality/importance ratings).

Wikipedia Vital Articles are selected by broad community consensus
as the most important articles regardless of quality class -- making
this a genuinely independent signal for validation.
"""
import csv, urllib.request, urllib.parse, json, time

# ── Load top 100 articles ─────────────────────────────────────────────────────
with open("data/scored_articles.csv", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

rows.sort(key=lambda r: float(r["impact_need_score"]), reverse=True)
top100 = rows[:100]

API = "https://en.wikipedia.org/w/api.php"

def wiki_get(params):
    params["format"] = "json"
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "WikiMedResearch/1.0 (zachary_schneider-lynch@brown.edu)"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

# ── Strategy: check each article's TALK page categories for vital-article tags
# Also check article categories for WikiProject Medicine "urgent" or "attention" flags
print("Checking top 100 articles for Vital Article status and attention flags...")
print("(querying Wikipedia API -- may take ~30 seconds)\n")

vital_hits   = []
attention_hits = []
errors = []

VITAL_PREFIXES = [
    "Wikipedia:Vital articles",
    "Vital articles",
]
ATTENTION_KEYWORDS = [
    "attention", "urgent", "cleanup", "improve",
    "expand", "update", "wikify",
]

# Batch API calls -- 50 titles at a time
def chunked(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i+n]

for chunk in chunked(top100, 50):
    titles      = [r["title"] for r in chunk]
    talk_titles = ["Talk:" + t for t in titles]

    # Query talk page categories
    data = wiki_get({
        "action": "query",
        "prop":   "categories",
        "titles": "|".join(talk_titles),
        "cllimit": "500",
        "clshow":  "!hidden",
    })

    pages = data.get("query", {}).get("pages", {})
    talk_cats = {}  # talk_title -> [cat names]
    for page in pages.values():
        title = page.get("title", "")
        cats  = [c["title"] for c in page.get("categories", [])]
        talk_cats[title] = cats

    # Query article categories (for maintenance tags)
    data2 = wiki_get({
        "action": "query",
        "prop":   "categories",
        "titles": "|".join(titles),
        "cllimit": "500",
    })
    pages2 = data2.get("query", {}).get("pages", {})
    art_cats = {}
    for page in pages2.values():
        title = page.get("title", "")
        cats  = [c["title"] for c in page.get("categories", [])]
        art_cats[title] = cats

    for r in chunk:
        t = r["title"]
        talk_t = "Talk:" + t
        t_cats = talk_cats.get(talk_t, [])
        a_cats = art_cats.get(t, [])
        all_cats = t_cats + a_cats

        # Check for vital article status
        is_vital = any(
            any(pref in c for pref in VITAL_PREFIXES)
            for c in all_cats
        )
        if is_vital:
            vital_cats = [c for c in all_cats if any(p in c for p in VITAL_PREFIXES)]
            vital_hits.append((t, r["importance_label"], r["quality_class"],
                               float(r["impact_need_score"]), vital_cats))

        # Check for attention/maintenance flags
        attn_cats = [
            c for c in all_cats
            if any(kw in c.lower() for kw in ATTENTION_KEYWORDS)
        ]
        if attn_cats:
            attention_hits.append((t, r["importance_label"], r["quality_class"],
                                   float(r["impact_need_score"]), attn_cats))

    time.sleep(0.5)  # be polite to the API

# ── Also check the full dataset baseline for vital articles (sample 500) ──────
print(f"\n=== RESULTS ===\n")
print(f"Top-100 articles that are Wikipedia Vital Articles: {len(vital_hits)}")
for title, imp, qual, score, cats in vital_hits:
    level = next((c for c in cats if "Vital" in c), cats[0] if cats else "?")
    print(f"  [{score:5.1f}] {title:<45} {imp}/{qual}  -> {level}")

print(f"\nTop-100 articles with maintenance/attention categories: {len(attention_hits)}")
for title, imp, qual, score, cats in attention_hits[:20]:
    print(f"  [{score:5.1f}] {title:<45} {imp}/{qual}")
    for c in cats[:3]:
        print(f"           {c}")

# ── Baseline: what % of ALL articles are vital? ────────────────────────────────
# Query a random sample of 200 articles from the full dataset
import random
random.seed(42)
sample_all = random.sample(rows, 200)
vital_all = 0

for chunk in chunked(sample_all, 50):
    talk_titles = ["Talk:" + r["title"] for r in chunk]
    data = wiki_get({
        "action": "query",
        "prop":   "categories",
        "titles": "|".join(talk_titles),
        "cllimit": "200",
        "clshow":  "!hidden",
    })
    pages = data.get("query", {}).get("pages", {})
    for page in pages.values():
        cats = [c["title"] for c in page.get("categories", [])]
        if any(any(p in c for p in VITAL_PREFIXES) for c in cats):
            vital_all += 1
    time.sleep(0.5)

print(f"\n=== BASELINE (200-article random sample from full 53k dataset) ===")
print(f"  Vital Articles: {vital_all}/200 = {vital_all/2:.1f}%")
print(f"\n=== COMPARISON ===")
print(f"  Vital Article rate — top 100  : {len(vital_hits)}%")
print(f"  Vital Article rate — all (est): {vital_all/2:.1f}%")
if vital_all > 0:
    print(f"  Enrichment factor             : {len(vital_hits)/(vital_all/2):.1f}x")
