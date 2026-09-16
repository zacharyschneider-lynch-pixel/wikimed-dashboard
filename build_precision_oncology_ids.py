"""
build_precision_oncology_ids.py
--------------------------------
Builds the precision oncology (PO) MeSH descriptor set used by the dashboard's
PO view and by the WIN Symposium analysis.

An article is precision-oncology-relevant if its assigned MeSH descriptor falls
into one of five pillars:

  1. biomarker_diagnostic  — tumor biomarkers, genomic / molecular diagnostics
  2. targeted_agent        — kinase inhibitors, therapeutic mAbs, checkpoint
                             inhibitors, angiogenesis / mTOR / HDAC inhibitors
  3. endocrine_targeted    — biomarker-directed endocrine therapy (ER/PR/AR),
                             the oldest form of biomarker-driven treatment
  4. precision_therapy     — molecular targeted therapy, immunotherapy,
                             precision medicine as clinical modalities
  5. hereditary_risk       — hereditary cancer predisposition syndromes

Deliberately EXCLUDED: classical cytotoxic chemotherapy (alkylating agents,
antimetabolites, antitumor antibiotics, phytogenic agents, topoisomerase
inhibitors). These are not biomarker-directed and would dilute the PO subset.

Descriptors are collected two ways:
  (a) MeSH tree prefix match — descriptor sits under a PO subtree
  (b) PharmacologicalAction  — drug descriptors MeSH links to a PO pharmacologic
                               role (Imatinib is D02 structurally but carries a
                               PharmacologicalAction link to Tyrosine Kinase Inhibitors)

Output: data/precision_oncology_mesh_ids.csv  (mesh_id, mesh_name, pillar, source)

Usage:  python build_precision_oncology_ids.py
"""

import xml.etree.ElementTree as ET
import pandas as pd

MESH_XML = "data/desc2026.xml"
OUT_PATH = "data/precision_oncology_mesh_ids.csv"

# ── Pillar definitions: MeSH tree prefixes ────────────────────────────────────
PILLAR_TREES = {
    "biomarker_diagnostic": [
        "D23.101.140",                  # Biomarkers, Tumor
        "D13.444.154.500",              # Circulating Tumor DNA
        "D13.444.308.425.500",          # Circulating Tumor DNA (alt tree)
        "E01.370.225.500.384.100.396",  # Liquid Biopsy
        "E05.200.500.384.100.396",      # Liquid Biopsy (alt tree)
        "E05.242.384.100.396",          # Liquid Biopsy (alt tree)
    ],
    "targeted_agent": [
        "D27.505.954.248.384",          # Antineoplastic Agents, Immunological
        "D27.505.519.389.755",          # Protein Kinase Inhibitors
        "D27.505.519.507",              # Immune Checkpoint Inhibitors
        "D12.776.543.750.655.500",      # Receptors, Chimeric Antigen
        "D12.776.826.387.500",          # Receptors, Chimeric Antigen (alt tree)
    ],
    "endocrine_targeted": [
        "D27.505.954.248.169",          # Antineoplastic Agents, Hormonal
    ],
    # NOTE: the broad Immunotherapy subtree (E02.095.465.425) is deliberately NOT
    # used here. It contains Vaccination, Immunization, Immunization Schedule,
    # COVID-19 Serotherapy, Sublingual Immunotherapy (allergy), Desensitization
    # and Graft Enhancement — none of which are precision oncology. The oncologic
    # members are named explicitly in PRECISION_THERAPY_UIS instead.
    "precision_therapy": [
        "E02.319.574",                  # Molecular Targeted Therapy
        "E02.782",                      # Precision Medicine
    ],
    "hereditary_risk": [
        "C04.700",                      # Neoplastic Syndromes, Hereditary
        "C16.320.700",                  # Neoplastic Syndromes, Hereditary (alt tree)
    ],
}

# Generic molecular-methods subtrees. These underpin precision oncology but are
# not oncologic in themselves: the same descriptors cover prenatal screening,
# behavioural epigenetics and population genomics. Descriptors captured here are
# written out with scope="conditional", and the consuming analysis admits them
# only when the ARTICLE is independently cancer-related. Leaving them
# unconditional pulled in Epigenetics, Genomics, Noninvasive prenatal testing,
# Celera Corporation and Project Manhigh.
CONDITIONAL_TREES = {
    "biomarker_diagnostic": [
        "E01.370.225.562",              # Genetic Testing (incl. Pharmacogenomic Testing)
        "E05.200.562",                  # Genetic Testing (alt tree)
        "E05.393.435",                  # Genetic Testing (alt tree)
        "E05.393.760.319",              # High-Throughput Nucleotide Sequencing
        "H01.158.273.343.750",          # Pharmacogenetics
        "H01.158.703.052",              # Pharmacogenetics (alt tree)
        "H02.628.479",                  # Pharmacogenetics (alt tree)
        "H01.158.273.180.350",          # Genomics
        "H01.158.273.343.350",          # Genomics (alt tree)
    ],
}

# ── Drug capture via PharmacologicalAction ───────────────────────────────────
# A drug is a precision ONCOLOGY agent only if it is both (a) antineoplastic and
# (b) molecularly targeted. Requiring both conditions is what keeps non-oncology
# kinase inhibitors and monoclonals out: upadacitinib (JAK inhibitor, rheumatoid
# arthritis), benralizumab (anti-IL5, asthma) and secukinumab (anti-IL17,
# psoriasis) all carry a targeted mechanism but no antineoplastic action.

# Any of these marks a descriptor as antineoplastic.
ANTINEOPLASTIC_PA = {
    "D000970",      # Antineoplastic Agents
    "D000903",      # Antibiotics, Antineoplastic
    "D018906",      # Antineoplastic Agents, Alkylating
    "D000964",      # Antimetabolites, Antineoplastic
    "D018931",      # Antineoplastic Agents, Hormonal
    "D000972",      # Antineoplastic Agents, Phytogenic
    "D000074322",   # Antineoplastic Agents, Immunological
}

# Targeted mechanisms that are NOT inherently oncologic — these require an
# antineoplastic action to co-occur before the drug counts as precision oncology.
TARGETED_PA_CONDITIONAL = {
    "D047428":    "targeted_agent",      # Protein Kinase Inhibitors
    "D000092004": "targeted_agent",      # Tyrosine Kinase Inhibitors
    "D020533":    "targeted_agent",      # Angiogenesis Inhibitors
    "D000091203": "targeted_agent",      # MTOR Inhibitors
    "D056572":    "targeted_agent",      # Histone Deacetylase Inhibitors
    "D004965":    "endocrine_targeted",  # Estrogen Antagonists
    "D047072":    "endocrine_targeted",  # Aromatase Inhibitors
    "D000726":    "endocrine_targeted",  # Androgen Antagonists
    "D006727":    "endocrine_targeted",  # Hormone Antagonists
}

# Mechanisms that are inherently oncologic — no co-occurrence required.
# Immune Checkpoint Inhibitors (D000082082) is NOT here: MeSH applies it to
# abatacept/belatacept, which are CTLA-4 *agonists* used for immunosuppression
# in transplant and rheumatoid arthritis — the opposite mechanism to
# pembrolizumab or nivolumab. It sits in the conditional set instead; the true
# checkpoint blockers all carry an antineoplastic action alongside it.
TARGETED_PA_UNCONDITIONAL = {
    "D000074322": "targeted_agent",      # Antineoplastic Agents, Immunological
}

# Explicitly oncologic immunotherapy / precision-therapy modalities.
PRECISION_THERAPY_UIS = {
    "D007167",   # Immunotherapy
    "D016219",   # Immunotherapy, Adoptive
    "D016233",   # Immunotherapy, Active
    "D016499",   # Radioimmunotherapy
    "D019264",   # Adoptive Transfer
    "D019496",   # Cancer Vaccines
    "D050130",   # Oncolytic Virotherapy
}

# Descriptors carrying a glucocorticoid action are excluded from the endocrine
# pillar. MeSH tags prednisolone and methylprednisolone as "Antineoplastic
# Agents, Hormonal" because steroids are used in haematologic malignancy, but
# they are not biomarker-directed therapy and do not belong in a PO subset.
GLUCOCORTICOID_PA = {"D005938"}

# Descriptors excluded outright. Noninvasive Prenatal Testing sits under the
# Liquid Biopsy subtree because it shares the cell-free DNA method, but it is
# obstetric rather than oncologic.
EXCLUDE_UIS = {"D000081182"}   # Noninvasive Prenatal Testing

# Pillar precedence when a descriptor matches more than one
PILLAR_PRIORITY = [
    "targeted_agent",
    "biomarker_diagnostic",
    "hereditary_risk",
    "endocrine_targeted",
    "precision_therapy",
]


def main() -> None:
    print(f"Parsing {MESH_XML} ...")
    root = ET.parse(MESH_XML).getroot()

    records = {}

    def assign(did, name, pillar, source, scope="oncologic"):
        if did in EXCLUDE_UIS:
            return
        prior = records.get(did)
        rec = {"mesh_name": name, "pillar": pillar, "source": source, "scope": scope}
        if prior is None:
            records[did] = rec
            return
        # An unconditional capture always beats a conditional one
        if prior["scope"] == "conditional" and scope == "oncologic":
            records[did] = rec
            return
        if prior["scope"] == scope and \
           PILLAR_PRIORITY.index(pillar) < PILLAR_PRIORITY.index(prior["pillar"]):
            records[did] = rec

    for desc in root.findall("DescriptorRecord"):
        did   = desc.findtext("DescriptorUI", "")
        name  = desc.findtext("DescriptorName/String", "")
        trees = [tn.text or "" for tn in desc.findall("TreeNumberList/TreeNumber")]

        for pillar, prefixes in PILLAR_TREES.items():
            if any(t == p or t.startswith(p + ".") for t in trees for p in prefixes):
                assign(did, name, pillar, "mesh_tree")

        for pillar, prefixes in CONDITIONAL_TREES.items():
            if any(t == p or t.startswith(p + ".") for t in trees for p in prefixes):
                assign(did, name, pillar, "mesh_tree", scope="conditional")

        if did in PRECISION_THERAPY_UIS:
            assign(did, name, "precision_therapy", "explicit_uid")

        pa_uis = {
            pa.findtext("DescriptorReferredTo/DescriptorUI", "")
            for pa in desc.findall("PharmacologicalActionList/PharmacologicalAction")
        }
        is_antineoplastic = bool(pa_uis & ANTINEOPLASTIC_PA)
        is_glucocorticoid = bool(pa_uis & GLUCOCORTICOID_PA)

        for pa_ui in pa_uis:
            if pa_ui in TARGETED_PA_UNCONDITIONAL:
                assign(did, name, TARGETED_PA_UNCONDITIONAL[pa_ui], "pharm_action")
            elif pa_ui in TARGETED_PA_CONDITIONAL and is_antineoplastic:
                pillar = TARGETED_PA_CONDITIONAL[pa_ui]
                if pillar == "endocrine_targeted" and is_glucocorticoid:
                    continue
                assign(did, name, pillar, "pharm_action")

    out = (
        pd.DataFrame([{"mesh_id": k, **v} for k, v in records.items()])
        .sort_values(["scope", "pillar", "mesh_id"])
        .reset_index(drop=True)
    )
    out.to_csv(OUT_PATH, index=False)

    print(f"\nWrote {len(out):,} precision oncology descriptors to {OUT_PATH}\n")
    print(out.groupby(["scope", "pillar", "source"]).size().to_string())

    # Sanity check: true positives must be captured, true negatives must not be
    print("\nSanity check - should be CAPTURED (precision oncology agents):")
    for probe in ["Trastuzumab", "Imatinib Mesylate", "Erlotinib Hydrochloride",
                  "Rituximab", "Bevacizumab", "Tamoxifen", "Everolimus"]:
        hit = out[out["mesh_name"] == probe]
        status = f"OK   {hit.iloc[0]['pillar']} ({hit.iloc[0]['source']})" if len(hit) else "MISS - not captured"
        print(f"  {probe:<26} {status}")

    print("\nSanity check - should be EXCLUDED (targeted but non-oncologic):")
    for probe in ["Upadacitinib", "Secukinumab", "Ustekinumab", "Tofacitinib",
                  "Adalimumab", "Abatacept", "Prednisolone", "Vaccination",
                  "Immunization", "Desensitization, Immunologic"]:
        hit = out[out["mesh_name"] == probe]
        status = f"LEAK - captured as {hit.iloc[0]['pillar']}" if len(hit) else "OK   excluded"
        print(f"  {probe:<26} {status}")


if __name__ == "__main__":
    main()
