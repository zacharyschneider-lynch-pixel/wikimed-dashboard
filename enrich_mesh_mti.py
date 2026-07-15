"""
Tier 3 MeSH enrichment via NLM's Medical Text Indexer (MTI).

Selection strategy (avoids the "every term in the paragraph" problem):
  Pass 1 — send ONLY the article title to MTI. Low noise: MTI returns
            concepts for what the title means, not what the text mentions.
  Pass 2 — if Pass 1 yields no confident match, send title + first sentence
            for more context. Candidates are still scored vs. the TITLE.

For each MTI response, picks the best-matching term by:
  combined = mti_score * max(title_similarity, synonym_match)

  synonym_match = 1.0 if the article title exactly matches any MeSH entry
  term (synonym) from desc2026.xml — catches e.g. "Heart Attack" → D009203
  "Myocardial Infarction" which would otherwise have poor title overlap.

Targets:
  1. Articles with no MeSH ID (~27 K)
  2. With --also-upgrade: also re-processes Low/Broad confidence matches

Requires a free UMLS API key: https://uts.nlm.nih.gov
Usage:
  python enrich_mesh_mti.py --api-key YOUR_UMLS_KEY
  python enrich_mesh_mti.py --api-key YOUR_UMLS_KEY --also-upgrade
"""

import os
import re
import time
import argparse
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import xml.etree.ElementTree as ET

import requests
import pandas as pd

DATA_PATH   = "data/wikiproject_medicine.csv"
SCORED_PATH = "data/scored_articles.csv"
MESH_XML    = "data/desc2026.xml"
MTI_URL     = "https://ii.nlm.nih.gov/cgi-bin/II/II.pl"
UA          = "WikiMedDashboard/1.0 (zachary_schneider-lynch@brown.edu)"


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


# ── MeSH synonym index ────────────────────────────────────────────────────────

def load_mesh_synonyms(xml_path):
    """
    Returns:
      preferred: {UI -> preferred_name}
      synonyms:  {UI -> frozenset of normalized entry terms}

    Loading synonyms lets us detect "Heart Attack" → D009203 even though
    'heart attack' doesn't appear in the preferred name 'Myocardial Infarction'.
    """
    print("Loading MeSH synonyms from XML...")
    tree = ET.parse(xml_path)
    root = tree.getroot()
    preferred = {}
    synonyms  = {}

    for rec in root.findall("DescriptorRecord"):
        ui   = rec.findtext("DescriptorUI", "").strip()
        name = rec.findtext("DescriptorName/String", "").strip()
        if not ui or not name:
            continue
        preferred[ui] = name

        terms = {normalize(name)}
        for term_elem in rec.iter("Term"):
            s = term_elem.findtext("String", "").strip()
            if s:
                terms.add(normalize(s))
        synonyms[ui] = frozenset(terms)

    print(f"  Loaded synonyms for {len(preferred):,} descriptors.")
    return preferred, synonyms


# ── Wikipedia first sentence ──────────────────────────────────────────────────

def fetch_first_sentence(title, session):
    """Return the first sentence of a Wikipedia article, or '' on failure."""
    try:
        r = session.get("https://en.wikipedia.org/w/api.php", params={
            "action":      "query",
            "prop":        "extracts",
            "titles":      title,
            "exintro":     True,
            "explaintext": True,
            "exsentences": 2,
            "format":      "json",
        }, timeout=20)
        for page in r.json()["query"]["pages"].values():
            extract = page.get("extract", "").strip()
            # First sentence only — avoids pulling in adjacent concepts
            sentences = re.split(r"(?<=[.!?])\s+", extract)
            return sentences[0] if sentences else ""
    except Exception:
        pass
    return ""


# ── MTI API ───────────────────────────────────────────────────────────────────

def call_mti(text, api_key, email, session):
    """
    POST text to MTI. Returns [(mesh_id, mesh_name, score), ...] sorted by
    score descending. Score is 0-1000 (NLM's own confidence metric).
    """
    try:
        r = session.post(MTI_URL, data={
            "API_KEY":        api_key,
            "Email":          email,
            "Batch":          "N",
            "SilentEmail":    "Y",
            "SkipIndicators": "Y",
            "Indexcat":       text,
        }, timeout=60)
        if r.status_code != 200:
            return []

        results = []
        for line in r.text.strip().split("\n"):
            parts = line.strip().split("|")
            if len(parts) < 4:
                continue
            mesh_id   = parts[1].strip()
            if not re.match(r"^[DC]\d{6}$", mesh_id):
                continue
            try:
                score = int(parts[2].strip())
            except ValueError:
                continue
            mesh_name = parts[3].strip().strip('"')
            results.append((mesh_id, mesh_name, score))

        return sorted(results, key=lambda x: -x[2])
    except Exception:
        return []


# ── Candidate selection ───────────────────────────────────────────────────────

def best_candidate(title, candidates, synonyms, min_mti_score=600):
    """
    Pick the MeSH term that best represents the article topic.

    For each top-15 MTI result:
      sem = max(title_token_similarity, synonym_exact_match)
      combined = mti_score * (0.5 + 0.5 * sem)

    We always compare against the ARTICLE TITLE, never the submitted text,
    so the selection stays on-topic regardless of what we fed MTI.

    Returns (mesh_id, mesh_name, combined_score, sem) or (None, None, 0, 0).
    """
    best_id, best_name, best_combined, best_sem = None, None, 0.0, 0.0

    for mesh_id, mesh_name, mti_score in candidates[:15]:
        if mti_score < min_mti_score:
            break

        name_sim  = token_similarity(title, mesh_name)
        syn_exact = 1.0 if normalize(title) in synonyms.get(mesh_id, frozenset()) else 0.0
        sem       = max(name_sim, syn_exact)
        combined  = mti_score * (0.5 + 0.5 * sem)

        if combined > best_combined:
            best_id       = mesh_id
            best_name     = mesh_name
            best_combined = combined
            best_sem      = sem

    # Reject if there's no real semantic connection to the title
    if best_sem < 0.25:
        return None, None, 0.0, 0.0

    return best_id, best_name, best_combined, best_sem


# ── Per-article pipeline ──────────────────────────────────────────────────────

def process_article(title, api_key, email, synonyms, session):
    """
    Two-pass selection:
      Pass 1: title alone → low noise, fast
      Pass 2: title + first sentence if pass 1 < 0.4 semantic confidence
    """
    # Pass 1: title only
    candidates = call_mti(title, api_key, email, session)
    mesh_id, mesh_name, score, sem = best_candidate(
        title, candidates, synonyms, min_mti_score=700
    )

    if mesh_id and sem >= 0.4:
        return mesh_id, mesh_name, score

    # Pass 2: add first sentence for context
    first_sent = fetch_first_sentence(title, session)
    if first_sent and normalize(first_sent) != normalize(title):
        time.sleep(0.3)
        augmented  = f"{title}. {first_sent}"
        candidates2 = call_mti(augmented, api_key, email, session)
        # Still score all results vs. the TITLE (not the augmented text)
        mesh_id2, mesh_name2, score2, sem2 = best_candidate(
            title, candidates2, synonyms, min_mti_score=600
        )
        if mesh_id2 and sem2 > sem:
            return mesh_id2, mesh_name2, score2

    return mesh_id, mesh_name, score


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", required=True,
                        help="UMLS API key (free at https://uts.nlm.nih.gov)")
    parser.add_argument("--email",   default="zachary_schneider-lynch@brown.edu")
    parser.add_argument("--workers", type=int, default=3,
                        help="Parallel workers (keep ≤5 to respect MTI rate limits)")
    parser.add_argument("--also-upgrade", action="store_true",
                        help="Re-process Low/Broad confidence matches in addition to no-MeSH")
    args = parser.parse_args()

    preferred, synonyms = load_mesh_synonyms(MESH_XML)

    df = pd.read_csv(DATA_PATH)
    print(f"\nLoaded {len(df):,} articles.")

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

    idx_by_title = {row["title"]: i for i, row in df.iterrows()}
    lock         = threading.Lock()
    completed    = [0]
    new_hits     = [0]
    upgrades     = [0]

    def worker(title):
        s = requests.Session()
        s.headers.update({"User-Agent": UA})
        time.sleep(0.4)  # space out MTI calls across workers
        return title, *process_article(title, args.api_key, args.email, synonyms, s)

    print(f"\nProcessing {len(todo_titles):,} articles ({args.workers} workers)...\n")

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(worker, t): t for t in todo_titles}

        for future in as_completed(futures):
            title = futures[future]
            try:
                _, mesh_id, mesh_name, score = future.result()
                idx = idx_by_title[title]

                with lock:
                    old_id = df.at[idx, "mesh_id"] if pd.notna(df.at[idx, "mesh_id"]) else None
                    if mesh_id:
                        if not old_id:
                            new_hits[0] += 1
                        else:
                            upgrades[0] += 1
                        df.at[idx, "mesh_id"] = mesh_id
                        if "mti_score" not in df.columns:
                            df["mti_score"] = None
                        df.at[idx, "mti_score"] = round(score)

                    completed[0] += 1
                    if completed[0] % 100 == 0:
                        df.to_csv(DATA_PATH, index=False)
                        pct = completed[0] / len(todo_titles) * 100
                        print(f"  [{completed[0]:,}/{len(todo_titles):,}  {pct:.0f}%]  "
                              f"+{new_hits[0]:,} new  +{upgrades[0]:,} upgraded  "
                              f"(checkpoint saved)", flush=True)

            except Exception as e:
                print(f"  Error on {title!r}: {e}")

    df.to_csv(DATA_PATH, index=False)
    after = df["mesh_id"].notna().sum()
    print(f"\n{'='*55}")
    print(f"New matches:   {new_hits[0]:,}")
    print(f"Upgrades:      {upgrades[0]:,}")
    print(f"Coverage now:  {after:,} / {len(df):,} ({after/len(df)*100:.1f}%)")

    if os.path.exists(SCORED_PATH):
        scored = pd.read_csv(SCORED_PATH)
        scored = scored.drop(columns=["mesh_id"], errors="ignore")
        scored = scored.merge(df[["title", "mesh_id"]], on="title", how="left")
        scored.to_csv(SCORED_PATH, index=False)
        print(f"Updated {SCORED_PATH}")

    print("\nDone. Run validate_mesh.py to refresh confidence scores.")


if __name__ == "__main__":
    main()
