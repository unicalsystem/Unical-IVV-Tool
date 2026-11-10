"""Sections from the document's table of contents; locations written as 'Page N, Section x.y Title'."""
import pymupdf

from core.document_parser import parse_document
from core.evidence_assessor import EvidenceAssessor
from core.refs import humanise, location, page_ref
from core.review_engine import run_rule

PAGES = [
    "Plan for Software Aspects of Certification\nDocument No: TU-PSAC-0001 Version: 1.0 Date: 01/10/2026",
    "Table of Contents\nIntroduction ........................ 3\nPurpose ........................ 3\nScope ........................ 3\n"
    "Software Overview ........................ 4\nTool Qualification ........................ 4\n"
    "Schedule ........................ 5\nTable 1: Tools ........................ 4",
    "1 Introduction\n1.1 Purpose\nThis plan describes the certification approach for the test unit software.\n"
    "1.2 Scope\nThe scope covers the software level A items of the test unit.",
    "2 Software Overview\nThe software runs on a single processor with a cyclic executive.\n"
    "2.1 Tool Qualification\nThe coverage analysis tool VectorCAST is qualified at TQL-5 per DO-330 and a tool "
    "qualification plan is produced.",
    "3 Schedule\nSOI-1 is planned in month 1 and SOI-2 in month 4. Revision History is kept in the SCM tool.",
]


def _pdf(path):
    d = pymupdf.open()
    for t in PAGES:
        d.new_page().insert_text((50, 60), t, fontsize=8)
    d.save(str(path))
    d.close()
    return path


def test_sections_come_from_table_of_contents(tmp_path):
    doc = parse_document(_pdf(tmp_path / "toc.pdf"))
    assert [(e.number, e.title, e.page) for e in doc.toc] == [
        ("1", "Introduction", 3), ("1.1", "Purpose", 3), ("1.2", "Scope", 3), ("2", "Software Overview", 4),
        ("2.1", "Tool Qualification", 4), ("3", "Schedule", 5)]
    assert [s.label for s in doc.sections][:3] == ["1 Introduction", "1.1 Purpose", "1.2 Scope"]
    assert doc.section_for(4, 200).title == "Tool Qualification"
    assert doc.section_for(4, 0).title == "Software Overview"


def test_evidence_location_written_as_page_and_section(tmp_path):
    doc = parse_document(_pdf(tmp_path / "toc.pdf"))
    v = EvidenceAssessor(doc, "PSAC").assess({"ref": "X", "sheet": "F", "question": "Each qualified tool is "
                                              "identified with its TQL and tool qualification plan.",
                                              "expected_evidence": ""})
    assert v.page_ref.startswith("Page 4, Section 2")
    assert "p." not in v.page_ref and "Sec." not in v.page_ref
    state, obs, quote, ref = run_rule("revision_history", doc)
    assert ref == "Page 5, Section 3 Schedule"


def test_reference_format():
    assert page_ref(7) == "Page 7" and page_ref(1, 3) == "Pages 1-3"
    assert location(29, type("S", (), {"number": "3.8", "title": "Fault Tolerance"})()) == \
        "Page 29, Section 3.8 Fault Tolerance"
    assert humanise("Partly addressed in p.29, Sec. 3.8 Fault Tolerance; see p.1-3") == \
        "Partly addressed in Page 29, Section 3.8 Fault Tolerance; see Pages 1-3"
