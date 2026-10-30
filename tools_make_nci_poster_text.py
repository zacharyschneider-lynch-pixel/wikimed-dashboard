"""Generate the NCI Data to Discovery poster text as a .docx (and .md)."""
import io
import time
import os
from docx import Document
from docx.shared import Pt, RGBColor, Inches

BASE = r"C:\Users\zachs\OneDrive\Desktop\Wiki Dashboard Project"
OUT = BASE + r"\NCI Poster Text_Cancer Dashboard_Zach Schneider-Lynch.docx"
OUT_MD = BASE + r"\NCI_poster_text_cancer_dashboard.md"

TITLE = ("WikiMed Article Recommender: An Open-Source Dashboard for Data-Driven "
         "Prioritization of Cancer-Related Wikipedia Article Editing")
AUTHORS = "Zach Schneider-Lynch, Ed.M.; Jeremy Warner, MD, MS, FAMIA, FASCO"
AFFIL = ("Warren Alpert Medical School of Brown University; "
         "Center for Clinical Cancer Informatics and Data Science (CCIDS)")

SECTIONS = [
    ("ABSTRACT", [
        "Wikipedia is among the most accessed health information sources and depends entirely "
        "upon volunteer editors. Medical trainees have contributed meaningful edits through "
        "WikiMed electives and edit-a-thons but have lacked data-driven tools to identify "
        "articles with the greatest reach and the greatest need for improvement. We developed "
        "an open-source web application featuring a dedicated Cancer Dashboard. Medical Subject "
        "Headings (MeSH) descriptors were assigned to WikiProject Medicine-flagged articles "
        "through a custom pipeline, and cancer-specific articles identified by filtering those "
        "descriptors against MeSH subtrees. Each article was scored using a normalized "
        "Impact-Need Score (0-100) combining pageview reach, editorial importance labels, "
        "quality deficit, editor scarcity, and clickstream-derived search intent. Among 1,859 "
        "cancer-related articles, the median Impact-Need Score was 63.7 (IQR 55.1-71.9), 57.5% "
        "were rated Stub or Start quality, and the median Flesch-Kincaid reading grade was 13.6 "
        "(IQR 11.6-15.7). The dashboard is available at wikimed-dashboard.com under CC BY-NC-SA "
        "4.0, with all code and pipelines open-source and auto-updated monthly.",
    ]),
    ("INTRODUCTION", [
        "Wikipedia is among the most consulted health information resources in the world. Its "
        "medical content drew an estimated 6.5 billion page views in 2013 across all language "
        "editions, exceeding the traffic of the NIH, WebMD, Mayo Clinic, NHS, WHO, and UpToDate "
        "on comparable measures [1]. It is equally prominent at the point of search, appearing "
        "among the first ten results for 71-85% of health queries tested across major search "
        "engines, ahead of MedlinePlus and NHS Direct Online, and ranking highest of all for "
        "rare diseases [2]. A scoping review across patient, student, and clinician populations "
        "found it consistently prominent as a health information resource [3].",
        "That content is written entirely by volunteers, and its quality is uneven. Audits have "
        "repeatedly found Wikipedia's medical articles substantively accurate but difficult to "
        "read. A comparison of ten cancer topics against the National Cancer Institute's "
        "Physician Data Query database found errors rare in both sources, but Wikipedia written "
        "at Flesch-Kincaid grade 14.1 against PDQ's 9.6 [4]. Comparable audits exist for drug "
        "information [5] and for the growth of medical content over time [6].",
        "WikiProject Medicine (WPM) volunteers assign each article two ratings: editorial "
        "quality (Stub to Featured Article) and clinical importance (Low to Top) [7]. These "
        "labels provide a rough signal of need, but browsing category trees does not scale "
        "across 53,286 articles, and the articles with the largest gap between readership and "
        "quality are not visible from category pages.",
        "Prior work has therefore characterised Wikipedia's medical content retrospectively and "
        "within bounded disease areas. What has been missing is a prospective, corpus-wide tool "
        "that ranks articles by where editorial effort would reach the most readers. We "
        "developed a customized algorithm and dashboard to address this unmet need, with a "
        "dedicated Cancer Dashboard as the first domain-specific application.",
    ]),
    ("METHODS", [
        "__Article metadata.__ Five sequential Wikipedia and Wikimedia API phases supplied "
        "quality class, importance label, watcher count, article length, 12-month pageviews, "
        "and unique editor counts for all 53,286 WPM articles [7].",
        "__Supplemental signals.__ Separate pipelines added inbound link counts, 3-month "
        "pageview totals for traffic velocity, and search-intent fractions derived from the May "
        "2026 Wikimedia clickstream dataset [10]. TF-IDF scores computed from article lead "
        "sections were matched against the 2026 NLM MeSH vocabulary [8] to produce a Medical "
        "Relevance Score (1-10).",
        "__MeSH assignment.__ A seven-layer cascade assigned MeSH descriptors [8], ordered by "
        "data reliability rather than coverage, with match confidence retained as metadata. "
        "[Figure 1]",
        "__Cancer identification.__ Assigned descriptors were filtered against the MeSH C04 "
        "(Neoplasms) subtree and against antineoplastic agent descriptors reached through MeSH "
        "PharmacologicalAction links [8], which capture drugs classified by chemical structure "
        "rather than clinical use. A title-keyword fallback covered articles without a MeSH "
        "assignment.",
        "__Scoring.__ A normalized Impact-Need Score (0-100) combined pageview reach (30%), "
        "importance (25%), quality deficit (25%), editor scarcity (10%), and search intent "
        "(10%). All components were percentile-ranked within the full corpus before weighting. "
        "Readability was estimated by Flesch-Kincaid (FK) grade level [9] from article lead "
        "sections.",
        "__Dashboard.__ Built in Python (Streamlit, Plotly, pandas) and deployed on Streamlit "
        "Community Cloud, with a monthly GitHub Actions workflow re-fetching signals and "
        "recomputing all scores automatically.",
    ]),
    ("RESULTS", [
        "__Corpus and identification.__ Of 53,286 WPM articles, 1,859 were identified as "
        "cancer-related: 1,266 (68%) through the MeSH C04 subtree, 168 (9%) through "
        "antineoplastic agent descriptors, and 425 (23%) through the title-keyword fallback. "
        "MeSH coverage reached 89% across the cancer subset. [Figure 2]",
        "__Editorial need.__ Median Impact-Need Score was 63.7 (IQR 55.1-71.9). 57.5% of cancer "
        "articles were rated Stub or Start quality, compared with 67.7% corpus-wide; 17 of 1,859 "
        "(0.9%) had reached Good or Featured Article status. [Figure 3]",
        "__Where the gap sits.__ Clinical importance and editorial quality are already partly "
        "aligned. Of the 65 articles rated High or Top importance, 43 (66%) were B class or "
        "better and only 4 were Stub or Start. The editorial gap instead sits in the long tail: "
        "1,060 Stub or Start articles rated Low or Mid importance, which together drew 5.67 "
        "million views over 12 months, 14% of all cancer article readership, at a median of "
        "1,365 views each. [Figure 4]",
        "__Readability.__ Median FK grade level was 13.6 (IQR 11.6-15.7). 68.0% of cancer "
        "articles were written above grade 12, and 1.4% at or below the eighth-grade level of "
        "the average US adult. [Figure 5]",
    ]),
    ("DISCUSSION", [
        "The Impact-Need Score surfaces the intersection of public reach and editorial gap, not "
        "the worst-quality articles alone. The cancer results show why that distinction matters. "
        "WikiProject Medicine volunteers have already brought most high-importance cancer "
        "articles to B class or better [7], so a prioritization strategy resting on importance "
        "labels alone would direct student effort toward the articles needing the least work. "
        "The articles with the largest remaining gap are individually rated Low or Mid "
        "importance but collectively reach millions of readers each year, a pattern visible only "
        "when readership is measured directly rather than inferred from editorial labels. "
        "Wikipedia's search visibility is already known to be highest for rare and less common "
        "conditions [2], which is consistent with a long tail carrying more traffic than its "
        "importance labels imply.",
        "Readability is a parallel and largely independent gap. The median cancer article sits "
        "at Flesch-Kincaid grade 13.6 [9], above the eighth-grade level at which the average US "
        "adult reads [11] and well above the sixth-grade ceiling commonly recommended for "
        "patient-facing material [12]. This closely matches the grade 14.1 reported for "
        "Wikipedia cancer content against the National Cancer Institute's Physician Data Query "
        "database in 2011 [4], indicating that readability has not materially improved in the "
        "fifteen years since. Raising an article from Stub to C class does not by itself make it "
        "more accessible.",
        "__Limitations.__ Quality and importance ratings are volunteer-assigned and may lag "
        "actual article content [7]. The MeSH C04 subtree includes benign neoplasms [8], so the "
        "corpus is neoplasm-related rather than strictly malignant. Readability is computed from "
        "lead sections rather than full articles. The scoring weights are theoretically "
        "motivated and have not yet been validated against editing outcomes.",
    ]),
    ("CONCLUSIONS", [
        "* Identified 1,859 cancer-related articles from 53,286 WikiProject Medicine articles "
        "using the MeSH C04 subtree, antineoplastic PharmacologicalAction links, and a keyword "
        "fallback, achieving 89% MeSH coverage across the subset",
        "* Derived a normalized Impact-Need Score combining readership, clinical importance, "
        "quality deficit, editor scarcity, and clickstream search intent",
        "* Found the editorial gap concentrated not in high-importance articles, 66% of which "
        "are already B class or better, but in a 1,060-article long tail drawing 5.67 million "
        "annual views",
        "* Measured a median reading grade of 13.6, with 68% of cancer articles written above "
        "grade 12 and 1.4% readable by the average US adult",
        "* Deployed a public dashboard with automated monthly refresh at wikimed-dashboard.com, "
        "licensed CC BY-NC-SA 4.0, with all code and pipelines open-source on GitHub",
        "* A pre-post survey study across seven partner medical schools to gauge utility, "
        "usability, and usefulness is planned",
    ]),
]

REFERENCES = [
    ("Heilman JM, West AG. Wikipedia and medicine: quantifying readership, editors, and the "
     "significance of natural language. J Med Internet Res. 2015;17(3):e62. doi:10.2196/jmir.4069",
     "VERIFIED against PMC full text. Supports the 6.5 billion page view figure and the "
     "comparison set (NIH, WebMD, Mayo Clinic, NHS, WHO, UpToDate). Analysed all language "
     "editions. Note the traffic data is from 2013; the authors hedge ('appears to be the most "
     "utilized')."),
    ("Laurent MR, Vickers TJ. Seeking health information online: does Wikipedia matter? "
     "J Am Med Inform Assoc. 2009;16(4):471-479. doi:10.1197/jamia.M3059",
     "VERIFIED. Supports the 71-85% top-ten search ranking, outperforming MedlinePlus and NHS "
     "Direct Online, and the rare-disease finding, which sets up the long-tail result in "
     "Results. CORRECTION: the WIN poster lists this DOI as 10.1197/jamia.M2823, which is "
     "wrong. The correct DOI is 10.1197/jamia.M3059."),
    ("Smith DA. Situating Wikipedia as a health information resource in various contexts: a "
     "scoping review. PLoS One. 2020;15(2):e0228786. doi:10.1371/journal.pone.0228786",
     "VERIFIED against full text. Cited only for prominence across populations. The review "
     "states that evidence for professional (clinician) use is 'more limited', so the poster "
     "makes no claim about a specific share of physicians using Wikipedia."),
    ("Rajagopalan MS, Khanna VK, Leiter Y, Stott M, Showalter TN, Dicker AP, Lawrence YR. "
     "Patient-oriented cancer information on the internet: a comparison of Wikipedia and a "
     "professionally maintained database. J Oncol Pract. 2011;7(5):319-323. "
     "doi:10.1200/JOP.2010.000209",
     "VERIFIED against PMC full text. Ten cancer types (five common, five uncommon); 1 error in "
     "80 statements; Wikipedia FK 14.1 vs PDQ 9.6. Our cancer-wide median of 13.6 closely "
     "matches their 14.1, which independently corroborates the readability result across a "
     "fifteen-year gap. Worth saying aloud at the poster."),
    ("Kraenbring J, Monzon Penza T, Gutmann J, et al. Accuracy and completeness of drug "
     "information in Wikipedia: a comparison with standard textbooks of pharmacology. PLoS One. "
     "2014;9(9):e106930. doi:10.1371/journal.pone.0106930",
     "Carried over from the WIN poster reference list. Cited as an example of a bounded-domain "
     "audit. Not independently re-verified here."),
    ("Shafee T, Masukume G, Kipersztok L, Das D, Haggstrom M, Heilman J. Evolution of "
     "Wikipedia's medical content: past, present and future. J Epidemiol Community Health. "
     "2017;71(11):1122-1129. doi:10.1136/jech-2016-208601",
     "Carried over from the WIN poster reference list. Cited for growth of medical content over "
     "time. Not independently re-verified here."),
    ("Wikipedia. WikiProject Medicine. "
     "https://en.wikipedia.org/wiki/Wikipedia:WikiProject_Medicine",
     "Source for the two rating scales (quality, importance) and the tagged corpus."),
    ("National Library of Medicine. Medical Subject Headings (MeSH). Bethesda, MD: NLM; 2026. "
     "https://www.nlm.nih.gov/mesh/",
     "Methods: the 2026 descriptor file used for the cascade, the C04 subtree, and "
     "PharmacologicalAction links."),
    ("Kincaid JP, Fishburne RP Jr, Rogers RL, Chissom BS. Derivation of new readability "
     "formulas for Navy Enlisted Personnel. Research Branch Report 8-75. Memphis, TN: Naval "
     "Technical Training, US Naval Air Station; 1975.",
     "Methods: the Flesch-Kincaid grade level formula."),
    ("Wikimedia Foundation. Wikipedia clickstream data. May 2026. "
     "https://dumps.wikimedia.org/other/clickstream/",
     "Methods: source of the search-intent component of the Impact-Need Score."),
    ("Kutner M, Greenberg E, Jin Y, Paulsen C. The Health Literacy of America's Adults: "
     "Results From the 2003 National Assessment of Adult Literacy (NCES 2006-483). "
     "US Department of Education, National Center for Education Statistics; 2006.",
     "Underpins the eighth-grade benchmark for the average US adult. A population mean rather "
     "than a recommended standard, which is why reference 12 is cited alongside it."),
    ("American Medical Association / National Institutes of Health patient education "
     "readability guidance, commonly cited as a sixth-grade ceiling (NIH guidance is sometimes "
     "reported as sixth to eighth grade).",
     "NOT INDEPENDENTLY VERIFIED. Widely repeated across the readability literature, but "
     "secondary sources disagree on the exact grade and none of those consulted cite a single "
     "primary document. Trace it to the primary AMA or NIH publication before final submission, "
     "or drop the clause and rest the argument on reference 11 alone."),
]

CAPTIONS = [
    ("METHODS", "Figure 1", "fig1_mesh_cascade.png",
     "MeSH descriptor assignment cascade. Seven layers run in order of data reliability, each "
     "processing only the articles the layers above it could not resolve, from human-curated "
     "Wikidata properties through to NLM Medical Text Indexer inference. The cascade assigned "
     "a descriptor to 32,430 of 53,286 WikiProject Medicine articles (60.9%) and to 89% of the "
     "cancer subset analysed here."),
    ("RESULTS", "Figure 2", "fig2_identification.png",
     "Cancer-related articles identified (n = 1,859). MeSH C04 (Neoplasms) subtree membership "
     "accounted for 1,266 articles (68%); antineoplastic agent descriptors reached through MeSH "
     "PharmacologicalAction links for 168 (9%); and a title-keyword fallback for the 425 "
     "articles (23%) lacking a usable MeSH assignment."),
    ("RESULTS", "Figure 3", "fig3_impact_vs_attention.png",
     "Editorial need against current readership. Each point is one cancer article, positioned "
     "by Impact-Need Score and Wiki Attention Score and coloured by editorial quality. The "
     "upper right quadrant, heavily read articles carrying a large quality gap, is the "
     "recommendation target. Quality is collapsed to three classes for legibility; Good and "
     "Featured Articles together account for 17 of 1,859 articles."),
    ("RESULTS", "Figure 4", "fig4_priority_matrix.png",
     "Priority matrix. Cancer articles by editorial quality and clinical importance. Articles "
     "rated High or Top importance are already predominantly B class or better (43 of 65), so "
     "importance labels alone would direct effort toward the articles needing least work. The "
     "editorial gap sits in the Low and Mid importance rows, where 1,060 Stub or Start articles "
     "drew 5.67 million views over 12 months."),
    ("RESULTS", "Figure 5", "fig5_readability.png",
     "Readability distribution. Flesch-Kincaid grade level for the 1,683 cancer articles with "
     "lead sections long enough to score. Median grade was 13.6 (IQR 11.6-15.7); 68.0% exceeded "
     "grade 12, and 1.4% fell at or below the eighth-grade level of the average US adult."),
    ("RESULTS", "Table 1", "table1_top_articles.csv",
     "Highest-priority cancer articles by Impact-Need Score, restricted to those rated High or "
     "Top clinical importance. The unrestricted ranking is dominated by benign dermatologic "
     "neoplasms, which fall within MeSH C04 but read as out of scope on a cancer poster."),
]

NOTES = [
    ("MeSH coverage is reported as 89% (cancer subset), not 82% (corpus). ",
     "The submitted abstract states 82% corpus-wide coverage. The data does not support that "
     "figure: actual corpus coverage is 60.9% (32,430 / 53,286), and has been since the initial "
     "commit. The 43,700 figure on the WIN poster is exactly 82% x 53,286, derived from the "
     "percentage rather than counted. Cancer-subset coverage of 89% is accurate, higher, and "
     "more relevant to this poster, so it is used here. The dashboard Methodology page also "
     "states ~82% and needs the same correction."),
    ("The priority-matrix finding differs from the WIN poster framing. ",
     "The WIN poster describes top-left cells (high importance x low quality) as the biggest "
     "unmet need. For the cancer subset that is not what the data shows: only 4 of 65 High/Top "
     "importance articles are Stub or Start. Presenting the long-tail finding instead is both "
     "accurate and a stronger informatics result, since it is only visible by measuring "
     "readership directly."),
    ("Biographies remain in the cancer corpus. ",
     "Henrietta Lacks (802,455 views) and Joseph Merrick (598,243) are among the ten most-read "
     "articles in the cancer subset, and Belatacept, a transplant immunosuppressant, ranks "
     "second by Impact-Need. The MeSH pipeline matches titles against descriptor names, so "
     "surnames collide with eponymous syndromes. A detector exists (fetch_is_biography.py) but "
     "has only been run against 147 precision-oncology articles. Running it corpus-wide before "
     "the meeting would clean the live dashboard behind the poster's URL."),
    ("Figure palettes were validated for colour-vision deficiency. ",
     "The dashboard's six-class quality ramp fails adjacent-pair separation under normal vision "
     "on two pairs (Start/C = 12.8, GA/FA = 13.5, against a floor of 15), and six near-blues are "
     "unreadable at poster viewing distance. Quality is collapsed to three validated classes in "
     "Figure 4 (worst-case CVD separation 18.7). GA and FA together account for only 17 of 1,859 "
     "articles, so nothing material is lost."),
]



def save_docx(doc, path, attempts=6):
    """Write the document, retrying through OneDrive sync locks.

    A Word window holding the file will not release it, so after the retries
    are exhausted say so plainly rather than surfacing a bare PermissionError.
    """
    for i in range(attempts):
        try:
            doc.save(path)
            return
        except PermissionError:
            if i == attempts - 1:
                raise SystemExit(
                    "Cannot write " + path
                    + " -- the file is open in Word. Close it and re-run."
                )
            time.sleep(0.8)


def build_docx():
    doc = Document()
    st = doc.styles["Normal"]
    st.font.name = "Calibri"
    st.font.size = Pt(11)
    st.paragraph_format.space_after = Pt(8)
    st.paragraph_format.line_spacing = 1.12
    for s in doc.sections:
        s.left_margin = s.right_margin = Inches(0.9)
        s.top_margin = s.bottom_margin = Inches(0.9)

    def head(text, size=13, before=15):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(before)
        p.paragraph_format.space_after = Pt(4)
        r = p.add_run(text)
        r.bold = True
        r.font.size = Pt(size)

    def muted(text, size=9.5):
        p = doc.add_paragraph()
        r = p.add_run(text)
        r.italic = True
        r.font.size = Pt(size)
        r.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

    def body(text):
        """Supports __bold lead-ins__ and * bullets."""
        if text.startswith("* "):
            p = doc.add_paragraph(style="List Bullet")
            p.paragraph_format.space_after = Pt(5)
            p.add_run(text[2:])
            return
        p = doc.add_paragraph()
        parts = text.split("__")
        for i, seg in enumerate(parts):
            if not seg:
                continue
            r = p.add_run(seg)
            r.bold = (i % 2 == 1)

    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(2)
    r = p.add_run("NCI Data to Discovery Symposium - Poster Text")
    r.bold = True
    r.font.size = Pt(15)
    muted("Cancer Dashboard. Figures in poster_figures/. Generated by "
          "tools_make_nci_poster_text.py; edit that script rather than this file.")

    head("Title", 12, before=10)
    body(TITLE)
    body(AUTHORS)
    muted(AFFIL, 10)

    for name, paras in SECTIONS:
        head(name)
        for t in paras:
            body(t)

    head("REFERENCES")
    muted("Numbering matches the [n] markers in the Introduction. Items marked VERIFIED were "
          "confirmed against full text while drafting.")
    for n, (cite, note) in enumerate(REFERENCES, 1):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(1)
        p.add_run(str(n) + ". ").bold = True
        rc = p.add_run(cite)
        rc.font.size = Pt(10)
        q = doc.add_paragraph()
        q.paragraph_format.left_indent = Inches(0.28)
        q.paragraph_format.space_after = Pt(8)
        rn = q.add_run(note)
        rn.italic = True
        rn.font.size = Pt(9)
        rn.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

    doc.add_page_break()
    head("FIGURE CAPTIONS", 13, before=0)
    muted("Paste each caption beneath its figure. Figure 1 belongs in Methods; Figures 2-5 and "
          "Table 1 belong in Results, in the order the text references them. Image files are in "
          "poster_figures/.")
    for section, num, fname, cap in CAPTIONS:
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(9)
        p.paragraph_format.space_after = Pt(1)
        p.add_run(num + ". ").bold = True
        p.add_run(cap)
        q = doc.add_paragraph()
        q.paragraph_format.left_indent = Inches(0.28)
        q.paragraph_format.space_after = Pt(6)
        r = q.add_run(section + "  -  " + fname)
        r.italic = True
        r.font.size = Pt(9)
        r.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

    head("Decisions made, and why")
    for lead, rest in NOTES:
        p = doc.add_paragraph(style="List Bullet")
        p.paragraph_format.space_after = Pt(7)
        p.add_run(lead).bold = True
        p.add_run(rest)

    save_docx(doc, OUT)
    print("Saved:", OUT)


def build_md():
    L = ["# NCI Data to Discovery Symposium - Poster Text\n",
         "Cancer Dashboard. Figures in `poster_figures/`.\n",
         "> Generated by `tools_make_nci_poster_text.py`; edit that script, not this file.\n",
         "---\n", "## Title\n", TITLE + "\n", AUTHORS + "\n", f"*{AFFIL}*\n", "---\n"]
    for name, paras in SECTIONS:
        L.append(f"## {name}\n")
        for t in paras:
            L.append(t.replace("__", "**") + "\n")
        L.append("")
    L.append("---")
    L.append("## REFERENCES")
    L.append("")
    L.append("Numbering matches the [n] markers in the Introduction. Items marked "
             "VERIFIED were confirmed against full text while drafting.")
    L.append("")
    for n, (cite, note) in enumerate(REFERENCES, 1):
        L.append(str(n) + ". " + cite)
        L.append("   - *" + note + "*")
        L.append("")
    L.append("---")
    L.append("## FIGURE CAPTIONS")
    L.append("")
    L.append("Paste each caption beneath its figure. Figure 1 belongs in Methods; "
             "Figures 2-5 and Table 1 belong in Results, in the order the text "
             "references them. Image files are in `poster_figures/`.")
    L.append("")
    for section, num, fname, cap in CAPTIONS:
        L.append("**" + num + ".** " + cap)
        L.append("  *" + section + " - `" + fname + "`*")
        L.append("")
    L.append("## Decisions made, and why\n")
    for lead, rest in NOTES:
        L.append(f"- **{lead.strip()}** {rest}")
    io.open(OUT_MD, "w", encoding="utf-8").write("\n".join(L))
    print("Saved:", OUT_MD)
    wc = sum(len(t.split()) for _, ps in SECTIONS for t in ps)
    print(f"  poster body: {wc} words across {len(SECTIONS)} sections")
    for name, ps in SECTIONS:
        print(f"    {name:<14}{sum(len(t.split()) for t in ps):>4} words")


if __name__ == "__main__":
    build_docx()
    build_md()
