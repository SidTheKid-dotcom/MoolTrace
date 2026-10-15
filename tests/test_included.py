"""Included-trial evidence from PMC JATS, and the hop-count rule."""

from mooltrace.clients import CallStats
from mooltrace.contexts import pmc_included_studies, pmc_sentences_for
from mooltrace.reliance import (
    WEIGHTS,
    choose_reliance,
    classify_sentence,
    is_flattened_table_header,
    prefer_included,
)

ABBAS_DOI = "10.1016/j.jogoh.2018.10.023"
ABBAS_ROB_HEADER = (
    "Authors Randomization process Deviations from intended interventions "
    "Bias in measurement of outcome Bias to missing outcome data Bias in "
    "selecting the reported results Overall bias Abbas et al."
)
OTHER_DOI = "10.1000/excluded-trial"
COLLISION_DOI = "10.1000/abbas-2020"

# PLOS-style: characteristics table uses "1-Abbas et al (2019)" with no xref.
# The retracted paper's Crossref year is 2018; the review cites it as 2019.
PLOS_XML = """<?xml version="1.0"?>
<article>
  <body>
    <sec>
      <title>Results</title>
      <table-wrap id="t001">
        <label>Table 1</label>
        <caption><title>Demographic data of the retained studies.</title></caption>
        <table>
          <thead><tr><th>Authors (year)</th><th>Country</th></tr></thead>
          <tbody>
            <tr><td><bold>1-Abbas et al (2019)</bold></td><td>Egypt</td></tr>
            <tr><td>2-Lee et al (2023)</td><td>Singapore</td></tr>
          </tbody>
        </table>
      </table-wrap>
      <table-wrap id="t002">
        <label>Table 2</label>
        <caption><title>Risk of bias 2 assessment of the included studies.</title></caption>
        <table>
          <thead>
            <tr>
              <th>Authors</th><th>Randomization process</th>
              <th>Overall bias</th>
            </tr>
          </thead>
          <tbody>
            <tr><td>Abbas et al.</td><td>Low risk</td><td>Low risk</td></tr>
          </tbody>
        </table>
      </table-wrap>
      <table-wrap id="t099">
        <label>Table S1</label>
        <caption><title>Characteristics of excluded studies.</title></caption>
        <table>
          <tbody>
            <tr><td>OtherAuthor et al (2017)</td><td>wrong population</td></tr>
          </tbody>
        </table>
      </table-wrap>
    </sec>
  </body>
  <back>
    <ref-list>
      <title>References</title>
      <ref id="pone.ref024">
        <label>24</label>
        <element-citation>
          <person-group><name><surname>Abbas</surname><given-names>AM</given-names></name></person-group>
          <year>2019</year>
          <pub-id pub-id-type="doi">10.1016/j.jogoh.2018.10.023</pub-id>
        </element-citation>
      </ref>
      <ref id="pone.ref099">
        <label>99</label>
        <element-citation>
          <person-group><name><surname>OtherAuthor</surname></name></person-group>
          <year>2017</year>
          <pub-id pub-id-type="doi">10.1000/excluded-trial</pub-id>
        </element-citation>
      </ref>
    </ref-list>
  </back>
</article>
"""

# MDPI-style: caption (not title), parent section, xref + ext-link DOI, hyphenated surname.
MDPI_XML = """<?xml version="1.0"?>
<article>
  <body>
    <sec>
      <title>3. Results</title>
      <sec>
        <title>3.2. Characteristics of Included Studies</title>
        <table-wrap id="t001">
          <label>Table 1</label>
          <caption>Baseline characteristics of included randomized controlled trials.</caption>
          <table>
            <thead>
              <tr><th>Author, Year [Ref]</th><th>Objective</th></tr>
            </thead>
            <tbody>
              <tr>
                <td>Abd-Elsalam et al., 2020 [23], NCT04353336</td>
                <td>To evaluate HCQ.<xref ref-type="bibr" rid="B23-jcm">23</xref></td>
              </tr>
            </tbody>
          </table>
        </table-wrap>
      </sec>
    </sec>
  </body>
  <back>
    <ref-list>
      <ref id="B23-jcm">
        <label>23.</label>
        <mixed-citation>
          <named-content content-type="citation-string">Abd-Elsalam S., Esmail E.S. Hydroxychloroquine in the Treatment of COVID-19. Am. J. Trop. Med. Hyg. 2020;103:1635-1639. doi: 10.4269/ajtmh.20-0873.</named-content>
          <ext-link ext-link-type="doi" href="10.4269/ajtmh.20-0873" />
        </mixed-citation>
      </ref>
      <ref id="B33-jcm">
        <label>33.</label>
        <mixed-citation>
          <named-content content-type="citation-string">Axfors C., Abd-Elsalam S., et al. Mortality outcomes. 2021. doi: 10.1000/axfors.</named-content>
          <ext-link ext-link-type="doi" href="10.1000/axfors" />
        </mixed-citation>
      </ref>
    </ref-list>
  </back>
</article>
"""

COLLISION_XML = """<?xml version="1.0"?>
<article>
  <body>
    <sec>
      <title>Risk of bias of included studies</title>
      <p>Overall bias Abbas et al. was judged low without a year.</p>
      <table-wrap>
        <label>Table 2</label>
        <caption><title>Risk of bias of the included studies.</title></caption>
        <table>
          <tbody><tr><td>Abbas et al.</td><td>Low</td></tr></tbody>
        </table>
      </table-wrap>
    </sec>
  </body>
  <back>
    <ref-list>
      <ref id="r1">
        <label>1</label>
        <element-citation>
          <person-group><name><surname>Abbas</surname></name></person-group>
          <year>2018</year>
          <pub-id pub-id-type="doi">10.1016/j.jogoh.2018.10.023</pub-id>
        </element-citation>
      </ref>
      <ref id="r2">
        <label>2</label>
        <element-citation>
          <person-group><name><surname>Abbas</surname></name></person-group>
          <year>2020</year>
          <pub-id pub-id-type="doi">10.1000/abbas-2020</pub-id>
        </element-citation>
      </ref>
    </ref-list>
  </back>
</article>
"""

PRISMA_XML = """<?xml version="1.0"?>
<article>
  <body>
    <sec>
      <title>Study selection</title>
      <p>Twelve randomised trials were included in the meta-analysis
      <xref ref-type="bibr" rid="r1">1</xref>.</p>
    </sec>
  </body>
  <back>
    <ref-list>
      <ref id="r1">
        <label>1</label>
        <element-citation>
          <person-group><name><surname>Boldt</surname></name></person-group>
          <year>1996</year>
          <pub-id pub-id-type="doi">10.1007/bf01699231</pub-id>
        </element-citation>
      </ref>
    </ref-list>
  </back>
</article>
"""


def test_rob_table_header_is_not_a_citation_sentence():
    assert is_flattened_table_header(ABBAS_ROB_HEADER)
    picked = choose_reliance(
        [(ABBAS_ROB_HEADER, "pmc_html")],
        cited_doi=ABBAS_DOI,
        cited_author="Abbas",
        cited_year=2018,
    )
    assert picked is None


def test_included_listing_class_is_strongest():
    sentence = "Listed among included studies (Table 1: Demographic data of the retained studies)"
    kind, weight = classify_sentence(sentence, cited_author="Abbas", cited_doi=ABBAS_DOI)
    assert kind == "included"
    assert weight == WEIGHTS["included"]
    assert weight == 1.0


def test_plos_characteristics_table_maps_abbas_year_mismatch_via_ref():
    found = pmc_included_studies(
        "PMC12510581",
        [ABBAS_DOI, OTHER_DOI],
        CallStats(),
        xml_text=PLOS_XML,
    )
    assert ABBAS_DOI in found
    hit = found[ABBAS_DOI]
    assert hit.reliance == "included"
    assert hit.weight == 1.0
    assert hit.sentence.startswith("Listed among included studies")
    assert "Table 1" in hit.sentence
    assert "retained studies" in hit.sentence.lower()
    assert "Overall bias" not in hit.sentence
    assert "Abbas et al." not in hit.sentence
    assert hit.evidence_from == "https://pmc.ncbi.nlm.nih.gov/articles/PMC12510581/"
    assert OTHER_DOI not in found


def test_excluded_studies_table_is_not_included():
    found = pmc_included_studies(
        "PMC1",
        [OTHER_DOI],
        CallStats(),
        xml_text=PLOS_XML,
    )
    assert OTHER_DOI not in found


def test_mdpi_xref_and_ext_link_doi_map_hyphenated_author():
    doi = "10.4269/ajtmh.20-0873"
    found = pmc_included_studies(
        "PMC8201261",
        [doi, "10.1000/axfors"],
        CallStats(),
        xml_text=MDPI_XML,
    )
    assert doi in found
    assert found[doi].reliance == "included"
    assert "Table 1" in found[doi].sentence
    assert "included" in found[doi].sentence.lower()
    assert "10.1000/axfors" not in found


def test_surname_alone_does_not_pick_among_two_abbas_years():
    found = pmc_included_studies(
        "PMC9",
        [ABBAS_DOI, COLLISION_DOI],
        CallStats(),
        xml_text=COLLISION_XML,
    )
    assert ABBAS_DOI not in found
    assert COLLISION_DOI not in found


def test_prisma_included_sentence_maps_via_xref():
    found = pmc_included_studies(
        "PMC2",
        ["10.1007/bf01699231"],
        CallStats(),
        xml_text=PRISMA_XML,
    )
    assert "10.1007/bf01699231" in found
    assert found["10.1007/bf01699231"].reliance == "included"
    assert "Study selection" in found["10.1007/bf01699231"].sentence


def test_xml_paragraph_sentences_are_not_the_rob_header():
    mapped = pmc_sentences_for("PMC12510581", [ABBAS_DOI], CallStats(), xml_text=PLOS_XML)
    blob = " ".join(mapped.get(ABBAS_DOI) or [])
    assert "Overall bias" not in blob


def test_prefer_included_loses_to_scholarly_exclusion():
    from mooltrace.reliance import Reliance

    included = Reliance(
        "included",
        1.0,
        "Listed among included studies (Table 1: retained studies)",
        "https://pmc.ncbi.nlm.nih.gov/articles/PMC1/",
    )
    critical = Reliance(
        "critical",
        0.0,
        "Abbas 2019 was excluded after an expression of concern.",
        "pmc_full_text",
    )
    assert prefer_included(critical, included) is critical
    assert prefer_included(None, included) is included
    mention = Reliance("mention", 0.55, "See Abbas et al., 2019.", "pmc_html")
    assert prefer_included(mention, included) is included
