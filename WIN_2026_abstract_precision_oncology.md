# WIN Symposium 2026 — Poster Abstract (revised for precision oncology)

Deadline: **17 September 2026**. Portal: mcigroup-winsymposium2026.eventsairsite.com

The portal does not publish a word or character limit publicly, so both versions below are
verified by count. **Version A matches the length of the abstract you already submitted (330
words), so it fits whatever limit you were working to.** Version B is the fuller treatment if the
portal allows ~500.

---

## Title

**Short (108 characters):**
WikiMed Article Recommender: Quantifying Reach and Readability Gaps in Public Precision Oncology Information

**Full (146 characters):**
WikiMed Article Recommender: An Open-Source Dashboard Quantifying Reach and Readability Gaps in Publicly Accessible Precision Oncology Information

---

## Version A — 338 words, 2,464 characters (recommended)

**Background:** Wikipedia is among the most accessed health information sources and depends
entirely upon volunteer editors, and is often the only free explanation of a biomarker report or
targeted agent available outside academic cancer centres. As biomarker-driven care enters routine
practice, the readability of this precision oncology (PO) content becomes consequential for
equitable access, yet has never been systematically characterised. We developed a customized
algorithm and dashboard to address this unmet need.

**Methods:** An open-source web application was developed featuring dedicated Cancer and
Precision Oncology dashboards. Medical Subject Headings (MeSH) descriptors were assigned to
WikiProject Medicine-flagged articles through a custom seven-layer pipeline. PO articles were
isolated using 128 MeSH descriptors spanning tumour biomarkers, molecular diagnostics, targeted
and immunological agents, endocrine therapy, and hereditary cancer risk. Articles were scored
using a normalized Impact-Need Score (0-100) combining pageview reach, importance labels,
quality deficit, editor scarcity, and clickstream-derived search intent, with readability by
Flesch-Kincaid (FK) grade.

**Results:** Among >53,000 WikiProject Medicine-tracked articles, 1,859 were cancer-specific and
131 PO-specific. PO articles drew a median 9,559 annual pageviews versus 2,432 for other cancer
articles (p<0.001), yet were written at a higher median FK grade of 14.4 (IQR 12.3–16.1) versus
13.6 (p=0.020). Only 1 of 128 (0.8%) was readable at or below the eighth-grade level of the average
US adult, while 78.9% exceeded twelfth grade. Median Impact-Need Score was 66.1 (IQR 59.4–74.0)
versus 63.5 (p=0.008); 49.6% were Stub or Start quality, with one Good Article and none Featured.

**Conclusions:** Wikipedia is an ideal forum for widespread and unfettered information sharing. By
repurposing open data standards such as MeSH, our tool provides a scalable, transparent pathway
for directing volunteer editors toward the highest-impact gaps in publicly accessible precision
oncology information. The concepts that increasingly determine treatment selection are among the
most read and least readable cancer content on Wikipedia, a barrier falling hardest on those
furthest from specialist care and propagating into the large language models now trained on this
corpus. The dashboard is available at wikimed-dashboard.com under CC BY-NC-SA 4.0, open-source
and auto-updated monthly.

---

## Version B — 460 words, 3,338 characters

**Background:** Wikipedia is among the most accessed health information sources and depends
entirely upon volunteer editors. For patients and clinicians without access to subscription
resources or academic cancer centres, it is often the first and only free explanation of a biomarker
report, a targeted agent, or an inherited cancer risk. As biomarker-driven care enters routine
practice, the quality and readability of this freely available precision oncology (PO) content
becomes consequential for equitable access, yet has never been systematically characterised. We
developed a customized algorithm and dashboard to address this unmet need.

**Methods:** An open-source web application was developed featuring dedicated Cancer and
Precision Oncology dashboards. Medical Subject Headings (MeSH) descriptors were assigned to
WikiProject Medicine-flagged articles through a custom seven-layer pipeline, and cancer-specific
articles identified by filtering assigned descriptors against MeSH subtrees. PO articles were
isolated using 128 descriptors spanning tumour biomarkers, molecular diagnostics, targeted and
immunological antineoplastic agents, biomarker-directed endocrine therapy, and hereditary cancer
predisposition, with drug capture requiring both an antineoplastic action and a molecularly
targeted mechanism. Each article was scored using a normalized Impact-Need Score (0-100)
combining pageview reach, editorial importance labels, quality deficit, editor scarcity, and
clickstream-derived search intent. Readability was estimated by Flesch-Kincaid (FK) grade level,
and PO articles compared against the remaining cancer corpus (Mann-Whitney U).

**Results:** Among >53,000 WikiProject Medicine-tracked articles, 1,859 cancer-specific articles
were identified, of which 131 were PO-specific. PO articles drew a median 9,559 annual pageviews
versus 2,432 for other cancer articles (p<0.001; 2.96 million views in total), yet were written at a
significantly higher median FK grade level of 14.4 (IQR 12.3–16.1) versus 13.6 (p=0.020). Only 1 of
128 PO articles (0.8%) was readable at or below the eighth-grade level of the average US adult,
while 78.9% exceeded twelfth-grade level. Median Impact-Need Score was 66.1 (IQR 59.4–74.0)
versus 63.5 (p=0.008); 49.6% were rated Stub or Start quality, with one Good Article and none
Featured. Rare cancers showed the widest gap, drawing a median 15,497 annual views with 90.9%
written above twelfth-grade level.

**Conclusions:** Wikipedia is an ideal forum for widespread and unfettered information sharing. By
repurposing open data standards such as MeSH, our tool provides a scalable, transparent pathway
for directing medical volunteer editors toward the highest-impact gaps in publicly accessible
precision oncology information. The molecular concepts that increasingly determine treatment
selection are among the most read and least readable cancer content on Wikipedia — a barrier that
falls hardest on those already furthest from specialist care, and one that propagates into the large
language models now trained on this corpus. The dashboard is available for public use at
wikimed-dashboard.com, licensed CC BY-NC-SA 4.0, with all code, MeSH mapping files, and
pipelines open-source on GitHub and auto-updated monthly. A pre-post survey study across seven
partner medical schools is planned.

---

## Changes from the previous version, and why

- **The 82% MeSH coverage claim was removed — it is not supported by the data.** Actual coverage
  is 60.9% of the full corpus (32,430 / 53,286), and has been since the initial commit, so the 82%
  figure was never true of this dataset. Coverage is 89% among cancer articles and 99% among PO
  articles, so a subset-specific figure can be substituted if a coverage number is wanted. **This
  also needs correcting on the Methodology page of the dashboard**, which states ~82%.
- **Cancer-corpus statistics were replaced with PO-specific ones**, since relabelling alone would
  not have survived review.
- **WikiMed electives and edit-a-thons** cut from Background, **"structured student programs"**
  cut from Conclusions, per reviewer feedback.
- **No quality-distribution claim is made.** After excluding biographies the difference is no longer
  significant (chi-square 8.8, p=0.115), so the 49.6% Stub/Start figure is reported descriptively
  with no between-group comparison attached.
- **Every p-value is a two-sided Mann-Whitney U test** of the 131 PO articles against the remaining
  1,760 cancer articles.

## Figures held in reserve (defensible, not in the abstract)

- Median unique editors 4 vs 2 (p<0.001) — editor scarcity is *not* the problem for PO articles;
  they are comparatively well-attended, which strengthens rather than weakens the readability
  argument
- Paediatric cancers: 54 articles, median 926 annual views, 51.9% Stub/Start — the inverse
  problem of low visibility *and* low quality
- Targeted agents specifically: median Impact-Need 70.6, median 12,171 annual views
- Total PO readership: 2.96 million annual views

## Known limitations, if asked

- Readability is computed from lead sections only, not full articles
- Rare (n=12) and paediatric (n=54) subsets are small; descriptive only
- MeSH gaps cut both ways: everolimus is missed because MeSH tags it immunosuppressive rather
  than antineoplastic
- Hereditary cancer predisposition is the largest single pillar (37 of 131); a reviewer could argue
  cancer genetics sits adjacent to, rather than within, precision oncology
