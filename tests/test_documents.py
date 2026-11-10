"""Document upload validation, parsing and identification (section 16)."""
from pathlib import Path

import pytest

from core.document_classifier import check_relevance, classify
from core.document_parser import parse_document
from core.document_validator import validate_file
from tests.factory import HR_TEXT, PSAC_TEXT, SDD_TEXT, make_docx, make_pdf, make_scanned_pdf, make_txt


# ---------------------------------------------------------------- upload validation
def test_valid_pdf(tmp_path):
    r = validate_file(make_pdf(tmp_path / "a.pdf", PSAC_TEXT))
    assert r.ok and r.info["pages"] >= 1 and len(r.info["sha256"]) == 64


def test_valid_docx(tmp_path):
    assert validate_file(make_docx(tmp_path / "a.docx", PSAC_TEXT)).ok


def test_valid_xlsx(tmp_path):
    from tests.factory import make_user_checklist_xlsx
    assert validate_file(make_user_checklist_xlsx(tmp_path / "c.xlsx")).ok


def test_valid_txt(tmp_path):
    assert validate_file(make_txt(tmp_path / "a.txt", PSAC_TEXT)).ok


def test_corrupted_pdf(tmp_path):
    p = tmp_path / "bad.pdf"
    p.write_bytes(b"%PDF-1.7\n garbage garbage")
    r = validate_file(p)
    assert not r.ok and r.errors


def test_wrong_extension_pdf(tmp_path):
    p = tmp_path / "fake.pdf"
    p.write_bytes(b"PK\x03\x04 not a pdf")
    assert not validate_file(p).ok


def test_corrupted_docx(tmp_path):
    p = tmp_path / "bad.docx"
    p.write_bytes(b"not a zip")
    r = validate_file(p)
    assert not r.ok and "corrupted" in r.errors[0]


def test_empty_file(tmp_path):
    p = tmp_path / "empty.pdf"
    p.write_bytes(b"")
    r = validate_file(p)
    assert not r.ok and "empty" in r.errors[0]


def test_unsupported_file(tmp_path):
    p = tmp_path / "x.exe"
    p.write_bytes(b"MZ")
    r = validate_file(p)
    assert not r.ok and "Unsupported" in r.errors[0]


def test_password_protected_pdf(tmp_path):
    r = validate_file(make_pdf(tmp_path / "enc.pdf", PSAC_TEXT, password="secret"))
    assert not r.ok and "password" in r.errors[0].lower()


def test_scanned_pdf_detected(tmp_path):
    r = validate_file(make_scanned_pdf(tmp_path / "scan.pdf"))
    assert r.ok and r.info.get("scanned") and r.warnings
    doc = parse_document(tmp_path / "scan.pdf", use_ocr=False)
    assert doc.scanned_pages == [1] and doc.warnings and not doc.has_text


# ------------------------------------------------------------------------ parsing
@pytest.mark.parametrize("maker,ext", [(make_pdf, "pdf"), (make_docx, "docx"), (make_txt, "txt")])
def test_parse_metadata(tmp_path, maker, ext):
    doc = parse_document(maker(tmp_path / f"p.{ext}", PSAC_TEXT))
    assert doc.doc_number == "TU-PSAC-0001"
    assert doc.version.startswith("1")
    assert doc.dal_mentions == ["A"]
    assert "DO-178C" in doc.standard_mentions
    assert any("System Overview" in s.title for s in doc.sections)


def test_parse_xlsx(tmp_path):
    from tests.factory import make_user_checklist_xlsx
    doc = parse_document(make_user_checklist_xlsx(tmp_path / "c.xlsx"))
    assert "software level" in doc.text.lower() and doc.sections


# ------------------------------------------------------------------ identification
SAMPLES = {
    "PSAC": PSAC_TEXT,
    "SDP": "Software Development Plan\nDocument No: X-1\n1 Development Environment\nCompiler and requirements process, "
           "design process, coding process, integration process, transition criteria.\nDO-178C software level A "
           "certification verification configuration baseline requirements",
    "SVP": "Software Verification Plan\n1 Independence\nStructural coverage, robustness, test cases, reverification, "
           "verification environment, partitioning.\nDO-178C software level A certification configuration requirements",
    "SCMP": "Software Configuration Management Plan\n1 Configuration Identification\nBaseline, change control, problem "
            "report, archive, status accounting, load control, control categories.\nDO-178C certification verification",
    "SQAP": "Software Quality Assurance Plan\n1 SQA Authority\nQuality assurance audit, conformity review, SQA records, "
            "independence, transition criteria.\nDO-178C certification verification configuration requirements",
    "SRD": "Software Requirements Data\n1 Interface Requirements\nHigh-level requirement HLR-001 shall... derived "
           "requirement shall. DO-178C certification verification baseline traceability software level",
    "SDD": SDD_TEXT + "\nDO-178C certification verification requirements baseline traceability",
    "SVCP": "Software Verification Cases and Procedures\n1 Test Cases\nTest case TC-1 input, expected result, pass/fail "
            "criteria, test procedure. DO-178C certification verification requirements traceability",
    "SAS": "Software Accomplishment Summary\n1 Software Status\nCompliance statement, software characteristics, change "
           "history. DO-178C certification verification configuration requirements",
}


@pytest.mark.parametrize("code", list(SAMPLES))
def test_identification(tmp_path, code):
    doc = parse_document(make_txt(tmp_path / "Project_X_Document_001.txt", SAMPLES[code]))
    assert classify(doc).best == code


def test_incorrect_classification_reported(tmp_path):
    doc = parse_document(make_txt(tmp_path / "d.txt", SAMPLES["SDD"]))
    rel = check_relevance(doc, "PSAC", "SOI-1", "DO-178C", "B")
    assert not rel.type_matches_selection and any("SDD" in m for m in rel.messages)


def test_irrelevant_document_rejected(tmp_path):
    doc = parse_document(make_txt(tmp_path / "hr.txt", HR_TEXT))
    assert not check_relevance(doc, "PSAC", "SOI-1", "DO-178C", "A").ok


def test_dal_conflict_flagged(tmp_path):
    doc = parse_document(make_txt(tmp_path / "p.txt", PSAC_TEXT))
    rel = check_relevance(doc, "PSAC", "SOI-1", "DO-178C", "C")
    assert rel.dal_conflict
