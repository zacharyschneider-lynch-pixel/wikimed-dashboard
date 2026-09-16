"""Generate the WIN Symposium 2026 abstract as a .docx."""
from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH

OUT = r"C:\Users\zachs\OneDrive\Desktop\Wiki Dashboard Project\WIN Abstract_Precision Oncology_Zach Schneider-Lynch.docx"

TITLE_SHORT = ("WikiMed Article Recommender: Quantifying Reach and Readability Gaps "
               "in Public Precision Oncology Information")
TITLE_FULL = ("WikiMed Article Recommender: An Open-Source Dashboard Quantifying Reach "
              "and Readability Gaps in Publicly Accessible Precision Oncology Information")

VERSION_A = [
    ("Background:", "Wikipedia is the most accessed online health information resource and depends entirely upon volunteer editors, and is often the only free explanation of a biomarker report or targeted agent available outside academic cancer centres. General cancer content was shown over a decade ago to read at college level (Flesch-Kincaid grade 14.1 versus 9.6 for the NCI Physician Data Query database), but the precision oncology (PO) corpus has never been separately characterised, even as biomarker-driven care enters routine practice. We developed a customized algorithm and dashboard to address this unmet need."),
    ("Methods:", "An open-source web application was developed featuring dedicated Cancer and Precision Oncology dashboards. Medical Subject Headings (MeSH) descriptors were assigned to WikiProject Medicine-flagged articles through a custom seven-layer pipeline. PO articles were isolated using 128 MeSH descriptors spanning tumour biomarkers, molecular diagnostics, targeted and immunological agents, endocrine therapy, and hereditary cancer risk. Articles were scored using a normalized Impact-Need Score (0-100) combining pageview reach, importance labels, quality deficit, editor scarcity, and clickstream-derived search intent, with readability by Flesch-Kincaid (FK) grade."),
    ("Results:", "Among >53,000 WikiProject Medicine-tracked articles, 1,859 were cancer-specific and 131 PO-specific. PO articles drew a median 9,559 annual pageviews versus 2,432 for other cancer articles (p<0.001), yet were written at a higher median FK grade of 14.4 (IQR 12.3\u201316.1) versus 13.6 (p=0.020). Only 1 of 128 (0.8%) was readable at or below the eighth-grade level of the average US adult, while 78.9% exceeded twelfth grade. Median Impact-Need Score was 66.1 (IQR 59.4\u201374.0) versus 63.5 (p=0.008); 49.6% were Stub or Start quality, with one Good Article and none Featured."),
    ("Conclusions:", "Wikipedia is an ideal forum for widespread and unfettered information sharing. By repurposing open data standards such as MeSH, our tool provides a scalable, transparent pathway for directing volunteer editors toward the highest-impact gaps in publicly accessible precision oncology information. The concepts that increasingly determine treatment selection are among the most read and least readable cancer content on Wikipedia, a barrier falling hardest on those furthest from specialist care and propagating into the large language models now trained on this corpus. The dashboard is available at wikimed-dashboard.com under CC BY-NC-SA 4.0, open-source and auto-updated monthly."),
]

VERSION_B = [
    ("Background:", "Wikipedia is the most accessed online health information resource and depends entirely upon volunteer editors. For patients and clinicians outside academic cancer centres it is frequently the first freely available explanation of a biomarker report, a targeted agent, or an inherited cancer risk. General cancer content on Wikipedia was shown over a decade ago to read at college level (Flesch-Kincaid grade 14.1, versus 9.6 for the NCI Physician Data Query database), but the precision oncology (PO) corpus specifically has never been separately characterised, even as biomarker-driven care enters routine practice. We developed a customized algorithm and dashboard to address this unmet need."),
    ("Methods:", "An open-source web application was developed featuring dedicated Cancer and Precision Oncology dashboards. Medical Subject Headings (MeSH) descriptors were assigned to WikiProject Medicine-flagged articles through a custom seven-layer pipeline, and cancer-specific articles identified by filtering assigned descriptors against MeSH subtrees. PO articles were isolated using 128 descriptors spanning tumour biomarkers, molecular diagnostics, targeted and immunological antineoplastic agents, biomarker-directed endocrine therapy, and hereditary cancer predisposition, with drug capture requiring both an antineoplastic action and a molecularly targeted mechanism. Each article was scored using a normalized Impact-Need Score (0-100) combining pageview reach, editorial importance labels, quality deficit, editor scarcity, and clickstream-derived search intent. Readability was estimated by Flesch-Kincaid (FK) grade level, and PO articles compared against the remaining cancer corpus (Mann-Whitney U)."),
    ("Results:", "Among >53,000 WikiProject Medicine-tracked articles, 1,859 cancer-specific articles were identified, of which 131 were PO-specific. PO articles drew a median 9,559 annual pageviews versus 2,432 for other cancer articles (p<0.001; 2.96 million views in total), yet were written at a significantly higher median FK grade level of 14.4 (IQR 12.3\u201316.1) versus 13.6 (p=0.020). Only 1 of 128 PO articles (0.8%) was readable at or below the eighth-grade level of the average US adult, while 78.9% exceeded twelfth-grade level. Median Impact-Need Score was 66.1 (IQR 59.4\u201374.0) versus 63.5 (p=0.008); 49.6% were rated Stub or Start quality, with one Good Article and none Featured. Rare cancers showed the widest gap, drawing a median 15,497 annual views with 90.9% written above twelfth-grade level. The cancer-wide median of 13.6 closely matches the grade 14.1 reported for Wikipedia cancer content in 2011, indicating no readability improvement over fifteen years."),
    ("Conclusions:", "Wikipedia is an ideal forum for widespread and unfettered information sharing. By repurposing open data standards such as MeSH, our tool provides a scalable, transparent pathway for directing medical volunteer editors toward the highest-impact gaps in publicly accessible precision oncology information. The molecular concepts that increasingly determine treatment selection are among the most read and least readable cancer content on Wikipedia \u2014 a barrier that falls hardest on those already furthest from specialist care, and one that propagates into the large language models now trained on this corpus. The dashboard is available for public use at wikimed-dashboard.com, licensed CC BY-NC-SA 4.0, with all code, MeSH mapping files, and pipelines open-source on GitHub and auto-updated monthly. A pre-post survey study across seven partner medical schools is planned."),
]

NOTES = [
    ("The 82% MeSH coverage claim was removed \u2014 the data does not support it. ",
     "Actual coverage is 60.9% of the corpus (32,430 / 53,286) and has been since the initial "
     "commit, so 82% was never true of this dataset. Coverage is 89% among cancer articles and "
     "99% among PO articles, so a subset-specific figure can be substituted if a coverage number "
     "is wanted. The Methodology page of the live dashboard also states ~82% and needs the same "
     "correction."),
    ("No quality-distribution claim is made. ",
     "After excluding biographies misassigned clinical MeSH IDs, the Stub/Start difference is no "
     "longer statistically significant (chi-square 8.8, p=0.115). The 49.6% figure is therefore "
     "reported descriptively, with no between-group comparison attached."),
    ("Cancer-corpus statistics were replaced with PO-specific ones. ",
     "Relabelling the existing cancer figures alone would not have survived review."),
    ("Reviewer feedback applied. ",
     "WikiMed electives and edit-a-thons cut from Background; \u201cstructured student programs\u201d cut "
     "from Conclusions; the planned survey moved off the closing note so the abstract ends on "
     "equity and AI implications."),
    ("All p-values are two-sided Mann-Whitney U tests ",
     "comparing the 131 PO articles against the remaining 1,760 cancer articles."),
]

RESERVE = [
    "Median unique editors 4 vs 2 (p<0.001) \u2014 editor scarcity is not the problem for PO articles; "
    "they are comparatively well-attended, which strengthens rather than weakens the readability argument",
    "Paediatric cancers: 54 articles, median 926 annual views, 51.9% Stub/Start \u2014 the inverse "
    "problem of low visibility and low quality",
    "Targeted agents specifically: median Impact-Need 70.6, median 12,171 annual views",
    "Total PO readership: 2.96 million annual views",
]

LIMITS = [
    "Readability is computed from article lead sections only, not full articles",
    "Rare (n=12) and paediatric (n=54) subsets are small and reported descriptively",
    "MeSH gaps cut both ways: everolimus is missed because MeSH tags it immunosuppressive rather "
    "than antineoplastic",
    "Hereditary cancer predisposition is the largest single pillar (37 of 131); a reviewer could "
    "argue cancer genetics sits adjacent to, rather than within, precision oncology",
]


REFS = [
    ("Smith DA. Situating Wikipedia as a health information resource in various contexts: "
     "A scoping review. PLoS One. 2020;15(2):e0228786. doi:10.1371/journal.pone.0228786. PMC7028268.",
     "VERIFIED against full text. Supports the opening sentence directly: “English language "
     "medical content has received more unique pageviews than any other health information resource "
     "online,” and “accessed frequently, as much as or more than other free online health "
     "information sources, such as Medline Plus.” Also reports Wikipedia pages ranking highly in "
     "Google results, with ~93% of clicks arriving from Google."),
    ("Rajagopalan MS, Khanna VK, Leiter Y, Stott M, Showalter TN, Dicker AP, Lawrence YR. "
     "Patient-oriented cancer information on the internet: a comparison of Wikipedia and a "
     "professionally maintained database. J Oncol Pract. 2011;7(5):319-323. "
     "doi:10.1200/JOP.2010.000209. PMID 22211130.",
     "VERIFIED against PMC full text. Supports the grade 14.1 vs 9.6 comparison, 10 cancer types "
     "(5 common, 5 uncommon), and comparable accuracy (1 error in 80 statements). Cite as prior "
     "work — an unqualified novelty claim is untenable against it, which is why the claim is "
     "narrowed to the precision oncology corpus."),
    ("Kutner M, Greenberg E, Jin Y, Paulsen C. The Health Literacy of America’s Adults: Results "
     "From the 2003 National Assessment of Adult Literacy (NCES 2006-483). US Department of "
     "Education, National Center for Education Statistics; 2006.",
     "Underpins the eighth-grade benchmark for the average US adult used in Results."),
    ("American Medical Association / National Institutes of Health patient education readability "
     "guidance (commonly cited as ≤ 6th grade; NIH guidance sometimes cited as 6th–8th).",
     "A STRONGER benchmark than the NAAL population average: it is a normative standard, and the "
     "gap it implies is larger. Trace to the primary AMA/NIH document before citing — secondary "
     "sources disagree on the exact grade."),
]

NOT_USED = [
    ("IMS Institute for Healthcare Informatics. Engaging patients through social media. 2014.",
     "Source of the widely repeated “~50% of US physicians consult Wikipedia” figure. It is an "
     "industry report rather than peer-reviewed, and Smith (2020) states outright that “the "
     "evidence for professional use is more limited.” The physician clause was removed from the "
     "Background rather than rest on this."),
    ("Rössler B, Holldack H, Schebesta K. Influence of Wikipedia and other web resources on "
     "acute and critical care decisions: a web-based survey. Intensive Care Med Exp. "
     "2015;3(Suppl 1):A867.",
     "Reports 77% of interns, 74% of residents and 65% of consultants using Wikipedia — but it is "
     "a conference meeting abstract rather than a full paper, n=372, anaesthesia and critical care "
     "only, and Austrian/Australian rather than US. Not generalisable to the claim."),
]


def main():
    doc = Document()

    # Base style
    st = doc.styles["Normal"]
    st.font.name = "Calibri"
    st.font.size = Pt(11)
    st.paragraph_format.space_after = Pt(10)
    st.paragraph_format.line_spacing = 1.15

    for s in doc.sections:
        s.left_margin = s.right_margin = Inches(1.0)
        s.top_margin = s.bottom_margin = Inches(1.0)

    def heading(text, size=13, space_before=16):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(space_before)
        p.paragraph_format.space_after = Pt(4)
        r = p.add_run(text)
        r.bold = True
        r.font.size = Pt(size)
        return p

    def meta(text):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(10)
        r = p.add_run(text)
        r.italic = True
        r.font.size = Pt(9.5)
        r.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
        return p

    def abstract_body(sections):
        for label, text in sections:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            rl = p.add_run(label + " ")
            rl.bold = True
            p.add_run(text)

    # ── Header ────────────────────────────────────────────────────────────────
    h = doc.add_paragraph()
    h.paragraph_format.space_after = Pt(2)
    r = h.add_run("WIN Symposium 2026 \u2014 Poster Abstract")
    r.bold = True
    r.font.size = Pt(15)

    meta("Zach Schneider-Lynch, Brown University  \u00b7  Submission deadline: 17 September 2026  "
         "\u00b7  Precision Oncology: Innovation and Equity Across the Globe")

    # ── Titles ────────────────────────────────────────────────────────────────
    heading("Title options", space_before=8)

    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(2)
    p.add_run("Short (108 characters) \u2014 recommended if a title limit applies: ").bold = True
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Inches(0.25)
    p.add_run(TITLE_SHORT).italic = True

    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(2)
    p.add_run("Full (146 characters): ").bold = True
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Inches(0.25)
    p.add_run(TITLE_FULL).italic = True

    # ── Version A ─────────────────────────────────────────────────────────────
    heading("Version A \u2014 recommended")
    meta("338 words \u00b7 2,464 characters. Matches the length of the previously submitted abstract "
         "(330 words), so it fits whatever limit that version was written to. The submission "
         "portal does not publish a word or character limit publicly.")
    abstract_body(VERSION_A)

    doc.add_page_break()

    # ── Version B ─────────────────────────────────────────────────────────────
    heading("Version B \u2014 fuller treatment", space_before=0)
    meta("460 words \u00b7 3,338 characters. Use only if the portal allows roughly 500 words. Adds the "
         "rare-cancer finding, the total readership figure, the drug-capture rule, and the planned "
         "multi-school survey.")
    abstract_body(VERSION_B)

    doc.add_page_break()

    # ── Notes ─────────────────────────────────────────────────────────────────
    heading("Changes from the previous version", space_before=0)
    for lead, rest in NOTES:
        p = doc.add_paragraph(style="List Bullet")
        p.paragraph_format.space_after = Pt(6)
        p.add_run(lead).bold = True
        p.add_run(rest)

    heading("Figures held in reserve (defensible, not in the abstract)")
    for item in RESERVE:
        p = doc.add_paragraph(item, style="List Bullet")
        p.paragraph_format.space_after = Pt(4)

    heading("Known limitations, if asked")
    for item in LIMITS:
        p = doc.add_paragraph(item, style="List Bullet")
        p.paragraph_format.space_after = Pt(4)

    doc.add_page_break()
    heading("References supporting the Background", space_before=0)
    meta("Each Background claim was checked against the literature. Items flagged VERIFIED were "
         "confirmed against full text; the remainder were identified via search and should be "
         "confirmed before submission.")
    for i, (cite, note) in enumerate(REFS, 1):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(2)
        p.add_run(f"{i}. ").bold = True
        p.add_run(cite)
        q = doc.add_paragraph()
        q.paragraph_format.left_indent = Inches(0.3)
        q.paragraph_format.space_after = Pt(10)
        r = q.add_run(note)
        r.italic = True
        r.font.size = Pt(9.5)
        r.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

    heading("Considered and deliberately not used")
    for cite, note in NOT_USED:
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(2)
        p.add_run(cite)
        q = doc.add_paragraph()
        q.paragraph_format.left_indent = Inches(0.3)
        q.paragraph_format.space_after = Pt(10)
        r = q.add_run(note)
        r.italic = True
        r.font.size = Pt(9.5)
        r.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

    doc.save(OUT)
    print("Saved:", OUT)


if __name__ == "__main__":
    main()
