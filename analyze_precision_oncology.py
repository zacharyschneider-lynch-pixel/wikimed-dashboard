"""
analyze_precision_oncology.py
------------------------------
Descriptive analysis of the precision oncology (PO) Wikipedia article subset,
for the WIN Symposium 2026 abstract.

Reports, for each corpus stratum: N, Impact-Need Score (median + IQR),
% Stub/Start quality, Flesch-Kincaid reading grade (median + IQR), pageviews,
and unique editors.

Strata:
  - All WikiProject Medicine
  - All cancer-related
  - Precision oncology (PO)
  - PO by pillar
  - PO rare diseases
  - Pediatric cancers

Usage:  python analyze_precision_oncology.py
"""

import os
import re
import pandas as pd
import numpy as np

DATA = "data/scored_articles.csv"

# ── Cancer identification (mirrors pages/Cancer_Dashboard.py) ─────────────────
CANCER_KW = [
    "cancer", "carcinoma", "tumor", "tumour", "malignant", "malignancy",
    "leukemia", "leukaemia", "lymphoma", "sarcoma", "melanoma", "neoplasm",
    "oncology", "glioma", "blastoma", "adenoma", "mesothelioma", "myeloma",
    "metastasis", "metastatic",
]

# ── PO title-keyword fallback (for the ~18% of articles lacking a MeSH ID) ────
# Targeted-agent stem patterns: kinase inhibitors (-nib), monoclonal antibodies
# (-mab), PARP (-parib), CDK4/6 (-ciclib), PI3K (-lisib), proteasome (-zomib).
PO_DRUG_STEMS = re.compile(
    r"\b\w{3,}(?:tinib|nib|mab|parib|ciclib|lisib|zomib|degib|rafenib)\b", re.I
)
PO_BIOMARKERS = re.compile(
    r"\b(?:brca[12]?|egfr|alk|ros1|kras|nras|braf|her2|erbb2|pd-?l?1|ctla-?4|"
    r"ntrk|pik3ca|idh[12]|flt3|jak2|bcr-?abl|vegf|mtor|parp|tp53|pten|"
    r"msi-?h|tmb|alk-?positive)\b", re.I
)
PO_CONCEPTS = [
    "targeted therapy", "targeted therapies", "immunotherapy", "checkpoint inhibitor",
    "car-t", "car t-cell", "chimeric antigen receptor", "tumor marker", "tumour marker",
    "biomarker", "molecular profiling", "genomic profiling", "liquid biopsy",
    "circulating tumor", "circulating tumour", "companion diagnostic",
    "precision medicine", "personalized medicine", "personalised medicine",
    "precision oncology", "pharmacogenom", "pharmacogenetic",
    "next-generation sequencing", "tumor mutational burden", "microsatellite instability",
    "oncogene", "tumor suppressor", "tumour suppressor", "monoclonal antibody",
    "molecular targeted", "tyrosine kinase inhibitor",
]

# ── Pediatric cancer identification ──────────────────────────────────────────
PEDS_MESH = {
    "D009447": "Neuroblastoma",
    "D009396": "Wilms Tumor",
    "D012175": "Retinoblastoma",
    "D008527": "Medulloblastoma",
    "D012208": "Rhabdomyosarcoma",
    "D018197": "Hepatoblastoma",
    "D012512": "Sarcoma, Ewing",
    "D012516": "Osteosarcoma",
    "D054198": "Precursor Cell Lymphoblastic Leukemia-Lymphoma",
    "D015464": "Leukemia, Myeloid, Acute",
    "D018232": "Neuroectodermal Tumors, Primitive",
    "D002282": "Carcinoma, Embryonal",
    "D018236": "Germinoma",
    "D009373": "Nephroblastoma",
}
PEDS_KW = re.compile(
    r"\b(?:pediatric|paediatric|childhood|juvenile|infantile|neuroblastoma|"
    r"wilms|retinoblastoma|medulloblastoma|rhabdomyosarcoma|hepatoblastoma|"
    r"ewing|nephroblastoma|germinoma)\b", re.I
)


def load() -> pd.DataFrame:
    df = pd.read_csv(DATA)
    for c in ["impact_need_score", "wiki_attention_score", "reading_level",
              "medical_relevance", "pageviews_12mo", "unique_editors"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    if "is_rare_disease" in df.columns:
        df["is_rare_disease"] = (
            df["is_rare_disease"].astype(str).str.lower()
            .map({"true": True, "false": False, "1": True, "0": False})
            .fillna(False)
        )
    return df


def mark_cancer(df: pd.DataFrame) -> pd.Series:
    c04 = set()
    tx = set()
    if os.path.exists("data/cancer_mesh_ids.csv"):
        c04 = set(pd.read_csv("data/cancer_mesh_ids.csv")["mesh_id"].dropna())
    if os.path.exists("data/cancer_treatment_mesh_ids.csv"):
        tx = set(pd.read_csv("data/cancer_treatment_mesh_ids.csv")["mesh_id"].astype(str))
    mesh = df["mesh_id"].astype(str)
    mesh_hit = mesh.isin(c04) | mesh.isin(tx)
    kw_hit = df["title"].str.lower().str.contains("|".join(CANCER_KW), regex=True, na=False)
    return mesh_hit | (~mesh_hit & kw_hit)


def mark_po(df: pd.DataFrame, is_cancer: pd.Series):
    """Returns (is_po, pillar_series).

    The title-keyword fallback is gated on cancer-relatedness. Without that gate
    the -mab / -nib stems sweep in every monoclonal and kinase inhibitor
    regardless of indication (upadacitinib for RA, benralizumab for asthma,
    secukinumab for psoriasis), which would inflate the subset with drugs that
    have nothing to do with oncology.
    """
    po = pd.read_csv("data/precision_oncology_mesh_ids.csv")
    pillar_map = dict(zip(po["mesh_id"].astype(str), po["pillar"].astype(str)))

    mesh = df["mesh_id"].astype(str)
    mesh_hit = mesh.isin(pillar_map.keys())

    title_lower = df["title"].str.lower().fillna("")
    kw_raw = (
        df["title"].str.contains(PO_DRUG_STEMS, na=False)
        | df["title"].str.contains(PO_BIOMARKERS, na=False)
        | title_lower.apply(lambda s: any(k in s for k in PO_CONCEPTS))
    )
    kw_hit = kw_raw & is_cancer & ~mesh_hit

    is_po = mesh_hit | kw_hit
    pillar = mesh.map(pillar_map)
    pillar = pillar.where(mesh_hit, other=np.where(kw_hit, "title_keyword", None))
    return is_po, pillar


def stats(sub: pd.DataFrame, label: str) -> dict:
    n = len(sub)
    if n == 0:
        return {"Stratum": label, "N": 0}
    ins = sub["impact_need_score"]
    rl = sub["reading_level"]
    stub_start = sub["quality_class"].isin(["Stub", "Start"]).sum()
    return {
        "Stratum": label,
        "N": n,
        "Impact-Need median": round(ins.median(), 1),
        "Impact-Need IQR": f"{ins.quantile(.25):.1f}-{ins.quantile(.75):.1f}",
        "% Stub/Start": round(stub_start / n * 100, 1),
        "FK grade median": round(rl.median(), 1) if rl.notna().any() else None,
        "FK grade IQR": (f"{rl.quantile(.25):.1f}-{rl.quantile(.75):.1f}"
                         if rl.notna().any() else None),
        "% FK >12": (round((rl > 12).sum() / rl.notna().sum() * 100, 1)
                     if rl.notna().any() else None),
        "Pageviews median": int(sub["pageviews_12mo"].median()),
        "Editors median": int(sub["unique_editors"].median()),
    }


def main() -> None:
    df = load()
    df["is_cancer"] = mark_cancer(df)
    df["is_po"], df["po_pillar"] = mark_po(df, df["is_cancer"])
    df["is_peds"] = (
        df["mesh_id"].astype(str).isin(PEDS_MESH.keys())
        | df["title"].str.contains(PEDS_KW, na=False)
    ) & df["is_cancer"]

    cancer = df[df["is_cancer"]]
    po     = df[df["is_po"]]
    po_onc = df[df["is_po"] & df["is_cancer"]]

    rows = [
        stats(df,     "All WikiProject Medicine"),
        stats(cancer, "All cancer-related"),
        stats(po,     "Precision oncology (all)"),
        stats(po_onc, "Precision oncology  AND  cancer"),
    ]
    for pillar in ["biomarker_diagnostic", "targeted_agent", "endocrine_targeted",
                   "precision_therapy", "hereditary_risk", "title_keyword"]:
        sub = df[df["po_pillar"] == pillar]
        if len(sub):
            rows.append(stats(sub, f"    - {pillar}"))

    rows.append(stats(df[df["is_po"] & df["is_rare_disease"]], "PO rare diseases"))
    rows.append(stats(df[df["is_peds"]], "Pediatric cancers"))
    rows.append(stats(cancer[~cancer["is_po"]], "Cancer, non-PO (comparator)"))

    out = pd.DataFrame(rows)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 50)
    print("\n" + "=" * 150)
    print("PRECISION ONCOLOGY SUBSET ANALYSIS — WIN Symposium 2026")
    print("=" * 150 + "\n")
    print(out.to_string(index=False))

    # MeSH coverage
    print("\n" + "-" * 150)
    print("MeSH coverage:")
    for lbl, sub in [("All WPM", df), ("Cancer", cancer), ("PO", po)]:
        cov = sub["mesh_id"].notna().sum() / len(sub) * 100
        print(f"  {lbl:<10} {cov:5.1f}% of articles carry a MeSH descriptor")

    # Quality distribution for PO
    print("\nPO quality distribution:")
    qorder = ["Stub", "Start", "C", "B", "GA", "FA"]
    qc = po["quality_class"].value_counts().reindex(qorder).fillna(0).astype(int)
    for q, c in qc.items():
        print(f"  {q:<6} {c:>5,}  ({c/len(po)*100:5.1f}%)")

    # Reading level bands for PO
    print("\nPO reading level bands (of those with data):")
    rl = po["reading_level"]
    bands = [("<=8 (avg US adult)", rl <= 8), ("9-12 (high school)", (rl > 8) & (rl <= 12)),
             ("13-16 (college)", (rl > 12) & (rl <= 16)), ("17+ (graduate)", rl > 16)]
    tot = rl.notna().sum()
    for lbl, m in bands:
        print(f"  {lbl:<22} {m.sum():>5,}  ({m.sum()/tot*100:5.1f}%)")

    # Top PO articles by impact-need
    print("\nTop 15 PO articles by Impact-Need Score:")
    top = po.nlargest(15, "impact_need_score")[
        ["title", "quality_class", "impact_need_score", "reading_level", "pageviews_12mo", "po_pillar"]
    ]
    print(top.to_string(index=False))

    # ── Comparative statistics: PO vs the rest of the cancer corpus ───────────
    from scipy import stats as sps

    other = cancer[~cancer["is_po"]]
    print("\n" + "-" * 150)
    print("PO vs cancer-non-PO  (Mann-Whitney U, two-sided):")

    for col, label in [("reading_level", "FK reading grade"),
                       ("pageviews_12mo", "Pageviews (12mo)"),
                       ("impact_need_score", "Impact-Need Score"),
                       ("unique_editors", "Unique editors")]:
        a = po[col].dropna()
        b = other[col].dropna()
        u, p = sps.mannwhitneyu(a, b, alternative="two-sided")
        print(f"  {label:<20} PO median {a.median():>8.1f}  vs  {b.median():>8.1f}   "
              f"U={u:,.0f}  p={p:.3g}")

    # Quality distribution: PO vs rest of cancer
    qorder = ["Stub", "Start", "C", "B", "GA", "FA"]
    tbl = pd.DataFrame({
        "PO":    po["quality_class"].value_counts().reindex(qorder).fillna(0),
        "other": other["quality_class"].value_counts().reindex(qorder).fillna(0),
    })
    chi2, pq, _, _ = sps.chi2_contingency(tbl.T.values)
    print(f"  {'Quality distribution':<20} chi2={chi2:.1f}  p={pq:.3g}")

    # Headline numbers for the abstract
    rl_po = po["reading_level"].dropna()
    print("\n" + "=" * 150)
    print("HEADLINE NUMBERS FOR THE ABSTRACT")
    print("=" * 150)
    print(f"  PO articles identified                 {len(po):,}")
    print(f"  ... of {len(cancer):,} cancer articles in {len(df):,} WikiProject Medicine articles")
    print(f"  Median Impact-Need Score               {po['impact_need_score'].median():.1f} "
          f"(IQR {po['impact_need_score'].quantile(.25):.1f}-{po['impact_need_score'].quantile(.75):.1f})")
    print(f"  Stub or Start quality                  {po['quality_class'].isin(['Stub','Start']).sum()} "
          f"({po['quality_class'].isin(['Stub','Start']).mean()*100:.1f}%)")
    print(f"  Featured Articles                      {(po['quality_class']=='FA').sum()}")
    print(f"  Good Articles                          {(po['quality_class']=='GA').sum()}")
    print(f"  Median FK reading grade                {rl_po.median():.1f} "
          f"(IQR {rl_po.quantile(.25):.1f}-{rl_po.quantile(.75):.1f})")
    print(f"  Written above 12th-grade level         {(rl_po>12).sum()}/{rl_po.notna().sum()} "
          f"({(rl_po>12).mean()*100:.1f}%)")
    print(f"  At or below 8th grade (avg US adult)   {(rl_po<=8).sum()}/{rl_po.notna().sum()} "
          f"({(rl_po<=8).mean()*100:.1f}%)")
    print(f"  Median annual pageviews                {po['pageviews_12mo'].median():,.0f} "
          f"(vs {other['pageviews_12mo'].median():,.0f} for other cancer articles)")
    print(f"  Total annual pageviews across subset   {po['pageviews_12mo'].sum():,.0f}")
    print(f"  Median unique editors (12mo)           {po['unique_editors'].median():.0f}")

    out.to_csv("data/po_analysis_summary.csv", index=False)
    po_cols = ["title", "quality_class", "importance_label", "impact_need_score",
               "reading_level", "pageviews_12mo", "unique_editors", "mesh_id",
               "po_pillar", "is_rare_disease"]
    po[po_cols].sort_values("impact_need_score", ascending=False).to_csv(
        "data/po_articles.csv", index=False)
    print("\nSaved summary to data/po_analysis_summary.csv")
    print("Saved full PO article list to data/po_articles.csv")


if __name__ == "__main__":
    main()
