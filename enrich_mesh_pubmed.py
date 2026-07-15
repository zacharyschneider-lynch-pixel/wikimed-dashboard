"""
Tier 1 MeSH enrichment: PubMed citation consensus.

Wikipedia medical articles cite primary literature — and NLM indexers have
already tagged those papers with MeSH. This script harvests that work:

  Phase 1 — Batch-fetch Wikipedia wikitext, extract all cited PMIDs.
  Phase 2 — Batch-query PubMed efetch for MeSH on every unique PMID.
             Each PMID is fetched only once, shared across articles.
  Phase 3 — Vote per article:
               major-topic MeSH mention = 2 pts
               minor-topic MeSH mention = 1 pt
             Among top candidates, prefer title/synonym match, then
             tree depth (most specific term wins ties).

No API key needed for basic use (3 req/sec PubMed limit).
Optional free NCBI key raises limit to 10 req/sec:
  https://www.ncbi.nlm.nih.gov/account/

Run FIRST in the enrichment pipeline:
    python enrich_mesh_pubmed.py
    python enrich_mesh_pubmed.py --ncbi-key YOUR_KEY --also-upgrade
"""

import os
import re
import time
import argparse
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import xml.etree.ElementTree as ET

import requests
import pandas as pd

DATA_PATH   = "data/wikiproject_medicine.csv"
SCORED_PATH = "data/scored_articles.csv"
MESH_XML    = "data/desc2026.xml"
WIKI_API    = "https://en.wikipedia.org/w/api.php"
EFETCH_URL  = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
IDCONV_URL  = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
UA          = "WikiMedDashboard/1.0 (zachary_schneider-lynch@brown.edu)"

# Every form a PMID can appear in Wikipedia wikitext
PMID_PATTERNS = [
    re.compile(r'pmid\s*=\s*(\d{5,9})',              re.IGNORECASE),  # citation template
    re.compile(r'\bPMID\s*:?\s*(\d{5,9})'),                           # inline PMID tag
    re.compile(r'pubmed\.ncbi\.nlm\.nih\.gov/(\d{5,9})'),             # new PubMed URL
    re.compile(r'ncbi\.nlm\.nih\.gov/pubmed/(\d{5,9})'),              # old PubMed URL
    re.compile(r'\{\{\s*cite\s+pmid\s*\|\s*(\d{5,9})', re.IGNORECASE), # {{cite pmid|}}
]

# DOI and PMC patterns — resolved to PMIDs in phase 1b
DOI_PATTERN = re.compile(r'\|\s*doi\s*=\s*([^\s|}{<]+)',  re.IGNORECASE)
PMC_PATTERN = re.compile(r'\|\s*pmc\s*=\s*(\d+)',         re.IGNORECASE)


# ── Text helpers ──────────────────────────────────────────────────────────────

def normalize(text):
    text = text.lower()
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def token_similarity(a, b):
    ta = set(normalize(a).split())
    tb = set(normalize(b).split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


# ── MeSH index ───────────────────────────────────────────────────────────────

def load_mesh(xml_path):
    """
    Returns:
      preferred:  {UI -> preferred_name}
      synonyms:   {UI -> frozenset of normalized entry terms}
      tree_depth: {UI -> max tree depth (deeper = more specific)}
    """
    print("Loading MeSH XML...")
    tree = ET.parse(xml_path)
    root = tree.getroot()
    preferred  = {}
    synonyms   = {}
    tree_depth = {}

    for rec in root.findall("DescriptorRecord"):
        ui   = rec.findtext("DescriptorUI",       "").strip()
        name = rec.findtext("DescriptorName/String", "").strip()
        if not ui or not name:
            continue

        preferred[ui] = name

        terms = {normalize(name)}
        for el in rec.iter("Term"):
            s = el.findtext("String", "").strip()
            if s:
                terms.add(normalize(s))
        synonyms[ui] = frozenset(terms)

        depths = [len(tn.text.strip().split(".")) for tn in rec.iter("TreeNumber")]
        tree_depth[ui] = max(depths) if depths else 0

    print(f"  {len(preferred):,} MeSH descriptors loaded.")
    return preferred, synonyms, tree_depth


# ── Phase 1: Wikipedia wikitext → PMIDs ──────────────────────────────────────

def extract_pmids(wikitext):
    """Return sorted list of unique PMID strings found in wikitext."""
    found = set()
    for pat in PMID_PATTERNS:
        found.update(pat.findall(wikitext))
    return sorted(found)


def extract_dois_pmcs(wikitext):
    """Return (dois, pmcs) — raw values found in citation templates."""
    dois = set()
    pmcs = set()
    for m in DOI_PATTERN.finditer(wikitext):
        doi = m.group(1).strip().rstrip(".")
        if doi.startswith("10."):
            dois.add(doi)
    for m in PMC_PATTERN.finditer(wikitext):
        pmcs.add(m.group(1))
    return sorted(dois), sorted(pmcs)


def resolve_pmcs(pmcs, session):
    """
    Resolve a list of PMC ID strings (digits only, no 'PMC' prefix) to PMIDs
    via the NCBI PMC ID converter. Returns {pmc_str: pmid_str}.
    """
    mapping = {}
    for i in range(0, len(pmcs), 50):
        batch = [f"PMC{p}" for p in pmcs[i:i + 50]]
        try:
            r = session.get(IDCONV_URL, params={"ids": ",".join(batch), "format": "json"},
                            timeout=20)
            for rec in r.json().get("records", []):
                pmid   = str(rec.get("pmid", ""))
                pmcid  = rec.get("pmcid", "").replace("PMC", "")
                if pmid.isdigit() and pmcid:
                    mapping[pmcid] = pmid
        except Exception:
            pass
        time.sleep(0.12)
    return mapping


def resolve_dois(dois, session):
    """
    Resolve a list of DOI strings to PMIDs via PubMed esearch with [doi] field.
    Batches up to 10 DOIs per query using OR. Returns {doi_lower: pmid_str}.
    """
    ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    mapping = {}
    for i in range(0, len(dois), 10):
        batch = dois[i:i + 10]
        term  = " OR ".join(f'"{d}"[doi]' for d in batch)
        try:
            r = session.get(ESEARCH, params={
                "db": "pubmed", "term": term, "retmode": "json", "retmax": len(batch),
            }, timeout=20)
            pmids = r.json().get("esearchresult", {}).get("idlist", [])
            # esearch returns PMIDs but not which DOI mapped to which PMID;
            # for small batches (<=10) we can verify each DOI individually
            for doi in batch:
                r2 = session.get(ESEARCH, params={
                    "db": "pubmed", "term": f'"{doi}"[doi]',
                    "retmode": "json", "retmax": 1,
                }, timeout=15)
                ids = r2.json().get("esearchresult", {}).get("idlist", [])
                if ids:
                    mapping[doi.lower()] = ids[0]
                time.sleep(0.12)
        except Exception:
            pass
        time.sleep(0.12)
    return mapping


def fetch_wikitext_batch(titles, session):
    """Fetch raw wikitext for up to 20 titles. Returns {title: wikitext}."""
    try:
        r = session.get(WIKI_API, params={
            "action":  "query",
            "prop":    "revisions",
            "titles":  "|".join(titles),
            "rvprop":  "content",
            "rvslots": "main",
            "format":  "json",
        }, timeout=30)
        result = {}
        for page in r.json()["query"]["pages"].values():
            title = page.get("title", "")
            try:
                text = page["revisions"][0]["slots"]["main"]["*"]
                result[title] = text
            except (KeyError, IndexError):
                pass
        return result
    except Exception:
        return {}


def collect_pmids_for_articles(titles, workers=8):
    """
    Phase 1 + 1b: fetch wikitext, extract PMIDs directly, then resolve
    DOIs and PMC IDs to additional PMIDs via the NCBI ID converter.
    Returns {title: [pmid, ...]}
    """
    import json

    print(f"\n[Phase 1] Fetching wikitext for {len(titles):,} articles...")
    batches = [titles[i:i+20] for i in range(0, len(titles), 20)]

    session = requests.Session()
    session.headers["User-Agent"] = UA

    # {title: {"pmids": [...], "dois": [...], "pmcs": [...]}}
    raw = {}
    done = [0]
    lock = threading.Lock()

    def process_batch(batch):
        texts = fetch_wikitext_batch(batch, session)
        time.sleep(0.3)
        result = {}
        for t in batch:
            wt = texts.get(t, "")
            dois, pmcs = extract_dois_pmcs(wt)
            result[t] = {
                "pmids": extract_pmids(wt),
                "dois":  dois,
                "pmcs":  pmcs,
            }
        return result

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(process_batch, b) for b in batches]
        for future in as_completed(futures):
            result = future.result()
            with lock:
                raw.update(result)
                done[0] += len(result)
                if done[0] % 5000 == 0:
                    print(f"  {done[0]:,}/{len(titles):,}", flush=True)

    direct_pmids = sum(1 for v in raw.values() if v["pmids"])
    all_dois     = sum(1 for v in raw.values() if v["dois"])
    all_pmcs     = sum(1 for v in raw.values() if v["pmcs"])
    print(f"  {direct_pmids:,} articles with direct PMIDs  |  "
          f"{all_dois:,} with DOIs  |  {all_pmcs:,} with PMC IDs", flush=True)

    # Phase 1b: resolve all unique DOIs + PMC IDs to PMIDs
    unique_dois = sorted({d for v in raw.values() for d in v["dois"]})
    unique_pmcs = sorted({p for v in raw.values() for p in v["pmcs"]})
    print(f"\n[Phase 1b] Resolving {len(unique_pmcs):,} PMC IDs via ID converter...",
          flush=True)

    conv_session = requests.Session()
    conv_session.headers["User-Agent"] = UA

    pmc_to_pmid = resolve_pmcs(unique_pmcs, conv_session)
    print(f"  {len(pmc_to_pmid):,} PMC IDs resolved", flush=True)

    print(f"  Resolving {len(unique_dois):,} DOIs via PubMed esearch...", flush=True)
    doi_to_pmid = resolve_dois(unique_dois, conv_session)
    print(f"  {len(doi_to_pmid):,} DOIs resolved", flush=True)

    # Merge resolved PMIDs back into per-article sets
    article_pmids = {}
    newly_added = 0
    for title, data in raw.items():
        pmid_set = set(data["pmids"])
        before = len(pmid_set)
        for doi in data["dois"]:
            p = doi_to_pmid.get(doi.lower())
            if p:
                pmid_set.add(p)
        for pmc in data["pmcs"]:
            p = pmc_to_pmid.get(pmc)
            if p:
                pmid_set.add(p)
        newly_added += len(pmid_set) - before
        article_pmids[title] = sorted(pmid_set)

    has_pmids    = sum(1 for v in article_pmids.values() if v)
    total_pmids  = sum(len(v) for v in article_pmids.values())
    unique_pmids = len({p for v in article_pmids.values() for p in v})
    print(f"  +{newly_added:,} PMIDs added via DOI/PMC resolution", flush=True)
    print(f"  {has_pmids:,} articles have >=1 PMID  |  "
          f"{total_pmids:,} total  |  {unique_pmids:,} unique", flush=True)

    checkpoint = "data/phase1_pmids.json"
    with open(checkpoint, "w", encoding="utf-8") as f:
        json.dump(article_pmids, f)
    print(f"  Checkpoint saved to {checkpoint}", flush=True)

    return article_pmids


# ── Phase 2: PubMed efetch → MeSH terms ──────────────────────────────────────

def efetch_mesh_batch(pmids, session, ncbi_key=None):
    """
    Query PubMed efetch for up to 200 PMIDs.
    Returns {pmid: [(ui, name, is_major), ...]}
    """
    params = {
        "db":      "pubmed",
        "id":      ",".join(pmids),
        "rettype": "xml",
        "retmode": "xml",
    }
    if ncbi_key:
        params["api_key"] = ncbi_key

    for attempt in range(3):
        try:
            r = session.post(EFETCH_URL, data=params, timeout=60)
            if r.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            if r.status_code != 200:
                return {}

            root = ET.fromstring(r.content)
            result = {}

            for article in root.findall(".//PubmedArticle"):
                pmid_el = article.find(".//PMID")
                if pmid_el is None:
                    continue
                pmid = pmid_el.text.strip()

                terms = []
                for heading in article.findall(".//MeshHeading"):
                    desc = heading.find("DescriptorName")
                    if desc is None:
                        continue
                    ui   = desc.get("UI", "")
                    name = desc.text or ""
                    # Descriptor OR any qualifier starred → major topic
                    is_major = desc.get("MajorTopicYN", "N") == "Y"
                    if not is_major:
                        is_major = any(
                            q.get("MajorTopicYN", "N") == "Y"
                            for q in heading.findall("QualifierName")
                        )
                    if ui:
                        terms.append((ui, name, is_major))

                result[pmid] = terms

            return result
        except Exception:
            if attempt < 2:
                time.sleep(1 + attempt)
    return {}


def fetch_all_pmid_mesh(all_pmids, ncbi_key=None, batch_size=200, workers=4):
    """
    Phase 2: fetch MeSH for every unique PMID across all articles.
    Returns {pmid: [(ui, name, is_major), ...]}
    """
    pmid_list = sorted(all_pmids)
    batches   = [pmid_list[i:i+batch_size] for i in range(0, len(pmid_list), batch_size)]
    print(f"\n[Phase 2] Fetching MeSH for {len(pmid_list):,} unique PMIDs "
          f"({len(batches)} PubMed requests)...")

    # Rate limit: 3/sec without key, 10/sec with key
    min_gap = 0.11 if ncbi_key else 0.34

    session = requests.Session()
    session.headers["User-Agent"] = UA

    cache = {}
    done  = [0]
    lock  = threading.Lock()

    def process_batch(batch):
        result = efetch_mesh_batch(batch, session, ncbi_key)
        time.sleep(min_gap)
        return result

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(process_batch, b) for b in batches]
        for future in as_completed(futures):
            result = future.result()
            with lock:
                cache.update(result)
                done[0] += 1
                if done[0] % 50 == 0:
                    print(f"  {done[0]:,}/{len(batches):,} batches done "
                          f"({len(cache):,} PMIDs resolved)", flush=True)

    resolved = sum(1 for v in cache.values() if v)
    print(f"  {resolved:,}/{len(pmid_list):,} PMIDs had MeSH indexing")
    return cache


# ── Phase 3: vote and select ──────────────────────────────────────────────────

def vote(pmids, pmid_mesh_cache):
    """
    Tally MeSH votes for one article's citation list.
    major-topic = 2 pts, minor-topic = 1 pt.
    Returns {ui: score}
    """
    scores = defaultdict(float)
    for pmid in pmids:
        for ui, _name, is_major in pmid_mesh_cache.get(pmid, []):
            scores[ui] += 2.0 if is_major else 1.0
    return dict(scores)


def select_winner(votes, title, preferred, synonyms, tree_depth, min_votes):
    """
    From vote tallies, pick the best MeSH term.

    Candidates must meet min_votes AND be within 80% of the top score.
    Among those, rank by (vote score, title/synonym match, tree depth).
    A term that exactly matches a MeSH synonym (e.g., "Heart Attack" →
    D009203 "Myocardial Infarction") scores 1.0 semantically.
    """
    if not votes:
        return None, None, 0.0

    top = max(votes.values())
    if top < min_votes:
        return None, None, 0.0

    threshold = max(min_votes, top * 0.80)
    candidates = [ui for ui, s in votes.items() if s >= threshold]

    def rank(ui):
        score    = votes[ui]
        pname    = preferred.get(ui, "")
        name_sim = token_similarity(title, pname)
        syn_hit  = 1.0 if normalize(title) in synonyms.get(ui, frozenset()) else 0.0
        sem      = max(name_sim, syn_hit)
        depth    = tree_depth.get(ui, 0)
        return (score, sem, depth)

    best = max(candidates, key=rank)
    return best, preferred.get(best, ""), votes[best]


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ncbi-key",    default=None,
                        help="Optional NCBI API key for 10 req/sec "
                             "(free at https://www.ncbi.nlm.nih.gov/account/)")
    parser.add_argument("--workers",     type=int, default=4)
    parser.add_argument("--min-votes",   type=float, default=2.0,
                        help="Minimum vote score to accept a match "
                             "(2 = one major-topic citation; default 2)")
    parser.add_argument("--also-upgrade", action="store_true",
                        help="Also re-examine Low/Broad confidence matches")
    args = parser.parse_args()

    preferred, synonyms, tree_depth = load_mesh(MESH_XML)

    df = pd.read_csv(DATA_PATH)
    print(f"\nLoaded {len(df):,} articles.")

    # Determine targets
    no_mesh = df["mesh_id"].isna()
    if args.also_upgrade and "mesh_confidence" in df.columns:
        low_broad = df["mesh_confidence"].isin(["Low", "Broad"])
        todo_mask = no_mesh | low_broad
        print(f"Targets: {no_mesh.sum():,} no-MeSH + {low_broad.sum():,} Low/Broad "
              f"= {todo_mask.sum():,} total")
    else:
        todo_mask = no_mesh
        print(f"Targets: {no_mesh.sum():,} articles with no MeSH ID")

    todo_titles = df[todo_mask]["title"].tolist()
    if not todo_titles:
        print("Nothing to do.")
        return

    # Phase 1: wikitext → PMIDs (resume from checkpoint if available)
    import json
    checkpoint = "data/phase1_pmids.json"
    if os.path.exists(checkpoint):
        print(f"Resuming from Phase 1 checkpoint: {checkpoint}")
        with open(checkpoint, encoding="utf-8") as f:
            article_pmids = json.load(f)
        print(f"  Loaded {len(article_pmids):,} articles from checkpoint.")
    else:
        article_pmids = collect_pmids_for_articles(todo_titles, workers=args.workers)

    # Phase 2: PubMed MeSH for all unique PMIDs
    all_unique_pmids = {p for pmids in article_pmids.values() for p in pmids}
    if not all_unique_pmids:
        print("\nNo PMIDs found in any article. Nothing to do.")
        return
    pmid_mesh = fetch_all_pmid_mesh(
        all_unique_pmids, ncbi_key=args.ncbi_key, workers=args.workers
    )

    # Phase 3: vote and assign
    print(f"\n[Phase 3] Voting on MeSH terms (min votes = {args.min_votes})...")
    idx_by_title = {row["title"]: i for i, row in df.iterrows()}
    new_hits = 0
    upgrades = 0
    no_pmids = 0
    no_winner = 0

    for title in todo_titles:
        pmids = article_pmids.get(title, [])
        if not pmids:
            no_pmids += 1
            continue

        votes = vote(pmids, pmid_mesh)
        best_id, best_name, best_score = select_winner(
            votes, title, preferred, synonyms, tree_depth, args.min_votes
        )

        if not best_id:
            no_winner += 1
            continue

        idx = idx_by_title[title]
        old_id = df.at[idx, "mesh_id"] if pd.notna(df.at[idx, "mesh_id"]) else None

        if not old_id:
            new_hits += 1
        else:
            upgrades += 1

        df.at[idx, "mesh_id"] = best_id
        if "pubmed_vote_score" not in df.columns:
            df["pubmed_vote_score"] = None
        df.at[idx, "pubmed_vote_score"] = round(best_score, 1)

    df.to_csv(DATA_PATH, index=False)
    after = df["mesh_id"].notna().sum()

    print(f"\n{'='*55}")
    print(f"Articles with no PMIDs:     {no_pmids:,}")
    print(f"PMIDs found but no winner:  {no_winner:,}")
    print(f"New MeSH assignments:       {new_hits:,}")
    print(f"Confidence upgrades:        {upgrades:,}")
    print(f"MeSH coverage now:          {after:,} / {len(df):,} "
          f"({after/len(df)*100:.1f}%)")

    if os.path.exists(SCORED_PATH):
        scored = pd.read_csv(SCORED_PATH)
        scored = scored.drop(columns=["mesh_id"], errors="ignore")
        scored = scored.merge(df[["title", "mesh_id"]], on="title", how="left")
        scored.to_csv(SCORED_PATH, index=False)
        print(f"Updated {SCORED_PATH}")

    print("\nDone. Run validate_mesh.py to refresh confidence scores.")


if __name__ == "__main__":
    main()
