"""
Full vital-article + attention-flag check on top 100 vs. random baseline.
Includes hidden categories (required for vital article tags).
"""
import csv, urllib.request, urllib.parse, json, time, random

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

def get_talk_cats(titles):
    talk_titles = ["Talk:" + t for t in titles]
    data = wiki_get({
        "action": "query",
        "prop":   "categories",
        "titles": "|".join(talk_titles),
        "cllimit": "500",
    })
    pages = data.get("query", {}).get("pages", {})
    result = {}
    for page in pages.values():
        title = page.get("title", "").replace("Talk:", "")
        cats = [c["title"] for c in page.get("categories", [])]
        result[title] = cats
    return result

def chunked(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i+n]

VITAL_KEYWORDS   = ["vital articles", "vital article"]
ATTENTION_KWS    = ["attention", "urgent", "cleanup", "improve", "expand",
                    "update", "wikify", "requested images", "to-do"]

def classify(cats):
    vital   = [c for c in cats if any(k in c.lower() for k in VITAL_KEYWORDS)]
    attn    = [c for c in cats if any(k in c.lower() for k in ATTENTION_KWS)]
    return vital, attn

print("=== TOP 100 ===")
vital_hits = []
attn_hits  = []

for chunk in chunked(top100, 50):
    titles = [r["title"] for r in chunk]
    cats_map = get_talk_cats(titles)
    for r in chunk:
        vital, attn = classify(cats_map.get(r["title"], []))
        if vital:
            vital_hits.append((r["title"], r["importance_label"], r["quality_class"],
                               float(r["impact_need_score"]), vital))
        if attn:
            attn_hits.append((r["title"], r["importance_label"], r["quality_class"],
                              float(r["impact_need_score"]), attn))
    time.sleep(0.5)

print(f"\nVital Articles in top 100: {len(vital_hits)}/100")
for title, imp, qual, score, cats in vital_hits:
    level = next((c for c in cats if "level" in c.lower()), cats[0])
    print(f"  [{score:5.1f}] {title:<45}  {imp}/{qual}")
    print(f"           {level}")

print(f"\nArticles with attention/maintenance flags: {len(attn_hits)}/100")
for title, imp, qual, score, cats in attn_hits:
    print(f"  [{score:5.1f}] {title:<45}  {imp}/{qual}")
    for c in cats[:2]:
        print(f"           {c}")

# ── Baseline: 300-article random sample ──────────────────────────────────────
print("\n=== BASELINE (300-article random sample) ===")
random.seed(42)
sample = random.sample(rows, 300)
vital_baseline = 0
attn_baseline  = 0

for chunk in chunked(sample, 50):
    titles = [r["title"] for r in chunk]
    cats_map = get_talk_cats(titles)
    for r in chunk:
        vital, attn = classify(cats_map.get(r["title"], []))
        if vital: vital_baseline += 1
        if attn:  attn_baseline  += 1
    time.sleep(0.5)

pct_v_base = vital_baseline / 3
pct_a_base = attn_baseline  / 3

print(f"Vital Articles:   {vital_baseline}/300 = {pct_v_base:.1f}%")
print(f"Attention flags:  {attn_baseline}/300 = {pct_a_base:.1f}%")

print("\n=== SUMMARY ===")
print(f"Vital Article rate   — top 100 : {len(vital_hits)}%  vs baseline {pct_v_base:.1f}%", end="")
if pct_v_base > 0:
    print(f"  ({len(vital_hits)/pct_v_base:.1f}x enrichment)")
else:
    print()
print(f"Attention flag rate  — top 100 : {len(attn_hits)}%  vs baseline {pct_a_base:.1f}%", end="")
if pct_a_base > 0:
    print(f"  ({len(attn_hits)/pct_a_base:.1f}x enrichment)")
else:
    print()
