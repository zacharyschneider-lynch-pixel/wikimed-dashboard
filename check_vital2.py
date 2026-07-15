"""Quick check: what talk-page categories do the top-10 articles actually have?"""
import csv, urllib.request, urllib.parse, json, time

with open("data/scored_articles.csv", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))
rows.sort(key=lambda r: float(r["impact_need_score"]), reverse=True)
top10 = rows[:10]

API = "https://en.wikipedia.org/w/api.php"

def wiki_get(params):
    params["format"] = "json"
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "WikiMedResearch/1.0 (zachary_schneider-lynch@brown.edu)"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

titles = [r["title"] for r in top10]
talk_titles = ["Talk:" + t for t in titles]

# Include hidden categories this time
data = wiki_get({
    "action": "query",
    "prop":   "categories",
    "titles": "|".join(talk_titles),
    "cllimit": "500",
})
pages = data.get("query", {}).get("pages", {})
for page in pages.values():
    title = page.get("title", "")
    cats  = [c["title"] for c in page.get("categories", [])]
    print(f"\n{title}")
    for c in sorted(cats):
        print(f"  {c}")
