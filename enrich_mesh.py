"""
Enrich the main article CSV with two new columns:

  specialty  — clinical specialty from WikiProject Medicine task force categories
               (pipe-separated if an article belongs to multiple, e.g. "Cardiology | Nephrology")
  mesh_id    — MeSH descriptor ID (e.g. D012345) from Wikidata first, infobox fallback

Run after wiki_scraper.py + scoring.py:
    python enrich_mesh.py
"""

import requests
import re
import time
import pandas as pd
from itertools import islice

S = requests.Session()
S.headers.update({"User-Agent": "WikiMedDashboard/1.0 (zachary_schneider-lynch@brown.edu)"})

# ── Task force category → display label ──────────────────────────────────────
TASK_FORCES = {
    "Category:Cardiology task force articles":                        "Cardiology",
    "Category:Dermatology task force articles":                       "Dermatology",
    "Category:Emergency medicine and EMS task force articles":        "Emergency Medicine",
    "Category:Gastroenterology task force articles":                  "Gastroenterology",
    "Category:Hematology-oncology task force articles":               "Hematology / Oncology",
    "Category:Medical genetics task force articles":                  "Medical Genetics",
    "Category:Nephrology task force articles":                        "Nephrology",
    "Category:Neurology task force articles":                         "Neurology",
    "Category:Ophthalmology task force articles":                     "Ophthalmology",
    "Category:Pathology task force articles":                         "Pathology",
    "Category:Psychiatry task force articles":                        "Psychiatry",
    "Category:Pulmonology task force articles":                       "Pulmonology",
    "Category:Radiology task force articles":                         "Radiology",
    "Category:Reproductive medicine task force articles":             "Reproductive Medicine",
    "Category:Toxicology task force articles":                        "Toxicology",
    # "Society and medicine" and "Translation Task Force" intentionally omitted
}

MESH_PATTERN = re.compile(
    r'\|\s*(?:MeshID|MeSHID|mesh_heading|mesh)\s*=\s*([DC]\d+)',
    re.IGNORECASE,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def chunked(iterable, n):
    it = iter(iterable)
    while True:
        chunk = list(islice(it, n))
        if not chunk:
            break
        yield chunk


def paginate_category(cat_title, namespace=1):
    params = {
        "action": "query", "list": "categorymembers",
        "cmtitle": cat_title, "cmlimit": "500",
        "cmnamespace": str(namespace), "format": "json",
    }
    while True:
        data = S.get("https://en.wikipedia.org/w/api.php", params=params).json()
        for m in data["query"]["categorymembers"]:
            yield m["title"].replace("Talk:", "")
        if "continue" not in data:
            break
        params["cmcontinue"] = data["continue"]["cmcontinue"]
        time.sleep(0.3)


# ── Phase 1: task force specialties ──────────────────────────────────────────

def collect_specialties():
    """Return {article_title: [specialty, ...]}."""
    specialty_map = {}
    for cat, label in TASK_FORCES.items():
        print(f"  {label} ...")
        for title in paginate_category(cat, namespace=1):
            specialty_map.setdefault(title, [])
            if label not in specialty_map[title]:
                specialty_map[title].append(label)
    return specialty_map


# ── Phase 2: Wikidata SPARQL MeSH IDs ────────────────────────────────────────

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
SPARQL_QUERY = """
SELECT ?article ?meshId WHERE {{
  ?item wdt:P486 ?meshId .
  ?article schema:isPartOf <https://en.wikipedia.org/> ;
           schema:about ?item .
}}
LIMIT 100000
OFFSET {offset}
"""

def collect_wikidata_mesh():
    """Return {article_title: mesh_id} from Wikidata."""
    mesh_map = {}
    offset = 0
    while True:
        r = requests.get(
            SPARQL_ENDPOINT,
            params={"query": SPARQL_QUERY.format(offset=offset), "format": "json"},
            headers={"User-Agent": "WikiMedDashboard/1.0", "Accept": "application/json"},
            timeout=60,
        )
        rows = r.json()["results"]["bindings"]
        if not rows:
            break
        for row in rows:
            url   = row["article"]["value"]
            title = url.replace("https://en.wikipedia.org/wiki/", "").replace("_", " ")
            mesh  = row["meshId"]["value"]
            if title not in mesh_map:          # keep first match per article
                mesh_map[title] = mesh
        print(f"  {len(mesh_map):,} articles with MeSH so far (offset {offset})")
        if len(rows) < 100000:
            break
        offset += 100000
        time.sleep(2)
    return mesh_map


# ── Phase 3: infobox MeSH fallback ───────────────────────────────────────────

def fetch_infobox_mesh_batch(titles):
    """Return {title: mesh_id} for up to 50 article titles via wikitext parsing."""
    data = S.get("https://en.wikipedia.org/w/api.php", params={
        "action": "query", "prop": "revisions",
        "titles": "|".join(titles),
        "rvprop": "content", "rvslots": "main",
        "format": "json",
    }).json()
    result = {}
    for page in data["query"]["pages"].values():
        title = page.get("title", "")
        try:
            wikitext = page["revisions"][0]["slots"]["main"]["*"]
            m = MESH_PATTERN.search(wikitext)
            if m:
                result[title] = m.group(1)
        except (KeyError, IndexError):
            pass
    return result


def collect_infobox_mesh(titles):
    """Batch-fetch MeSH IDs from article infoboxes for the given title list."""
    mesh_map = {}
    batches = list(chunked(titles, 50))
    for i, batch in enumerate(batches):
        mesh_map.update(fetch_infobox_mesh_batch(batch))
        if i % 20 == 0:
            print(f"  {min((i+1)*50, len(titles)):,}/{len(titles):,} infoboxes scanned")
        time.sleep(0.3)
    return mesh_map


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--data",   default="data/wikiproject_medicine.csv")
    parser.add_argument("--scored", default="data/scored_articles.csv")
    parser.add_argument("--skip-infobox", action="store_true",
                        help="Skip infobox phase (faster, Wikidata only for MeSH)")
    args = parser.parse_args()

    df = pd.read_csv(args.data)
    print(f"Loaded {len(df):,} articles.\n")

    # Phase 1: specialties
    print("[Phase 1] Collecting task force specialties...")
    specialty_map = collect_specialties()
    df["specialty"] = df["title"].map(
        lambda t: " | ".join(specialty_map[t]) if t in specialty_map else None
    )
    covered = df["specialty"].notna().sum()
    print(f"  Specialty assigned to {covered:,} articles ({covered/len(df)*100:.1f}%)\n")

    # Phase 2: Wikidata MeSH
    print("[Phase 2] Fetching MeSH IDs from Wikidata...")
    wikidata_mesh = collect_wikidata_mesh()
    df["mesh_id"] = df["title"].map(wikidata_mesh)
    wikidata_hits = df["mesh_id"].notna().sum()
    print(f"  MeSH from Wikidata: {wikidata_hits:,} articles\n")

    # Phase 3: infobox fallback (skip Stub class — rarely have infoboxes)
    if not args.skip_infobox:
        missing_mesh = df[df["mesh_id"].isna() & (df["quality_class"] != "Stub")]
        print(f"[Phase 3] Infobox MeSH for {len(missing_mesh):,} non-Stub articles without Wikidata coverage...")
        infobox_mesh = collect_infobox_mesh(missing_mesh["title"].tolist())
        for title, mesh in infobox_mesh.items():
            df.loc[df["title"] == title, "mesh_id"] = mesh
        infobox_hits = len(infobox_mesh)
        total_mesh = df["mesh_id"].notna().sum()
        print(f"  MeSH from infoboxes: {infobox_hits:,} additional articles")
        print(f"  Total MeSH coverage: {total_mesh:,} ({total_mesh/len(df)*100:.1f}%)\n")

    # Save enriched data CSV
    df.to_csv(args.data, index=False)
    print(f"Saved enriched data to {args.data}")

    # Update scored_articles.csv with the new columns
    if pd.io.common.file_exists(args.scored):
        scored = pd.read_csv(args.scored)
        for col in ["specialty", "mesh_id"]:
            if col in df.columns:
                scored = scored.drop(columns=[col], errors="ignore")
                scored = scored.merge(df[["title", col]], on="title", how="left")
        scored.to_csv(args.scored, index=False)
        print(f"Updated scored articles at {args.scored}")

    print("\nDone. Reload the dashboard and use the new Specialty filter.")


if __name__ == "__main__":
    main()
