"""Checklist engine, review engine, severity, AI agent guard-rails (section 16)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from core import standards
from core.ai_agent import LocalAIAgent
from core.checklist_engine import (applicability_for, combine, import_unical_workbook, list_builtin, load_builtin,
                                   read_user_checklist)
from core.document_parser import parse_document
from core.review_engine import ReviewEngine, overall_recommendation, run_rule
from core.severity_classifier import SeverityClassifier
from tests.factory import PSAC_TEXT, SDD_TEXT, make_docx, make_pdf, make_txt, make_user_checklist_xlsx


# --------------------------------------------------------------------- knowledge base
def test_annex_a_counts():
    c = standards.objective_counts("DO-178C")
    assert [c[d]["applicable"] for d in "ABCD"] == [71, 69, 62, 26]
    assert c["A"]["independence"] == 30


def test_builtin_checklists_present():
    cats = {(c["standard"], c["soi"], c["document_type"]) for c in list_builtin()}
    for doc in ("PSAC", "SDP", "SVP", "SCMP", "SQAP", "SRS", "SDS", "SCS", "IVVP"):
        assert ("DO-178C", "SOI-1", doc) in cats
    for soi, doc in (("SOI-2", "SRD"), ("SOI-2", "SDD"), ("SOI-3", "SVCP"), ("SOI-3", "SVR"), ("SOI-4", "SAS"),
                     ("SOI-4", "SCI")):
        assert ("DO-178C", soi, doc) in cats and ("DO-178B", soi, doc) in cats


def test_do178b_checklists_have_no_178c_only_content():
    for c in list_builtin():
        if c["standard"] != "DO-178B":
            continue
        cl = load_builtin("DO-178B", c["soi"], c["document_type"])
        assert cl["validated"] is False
        text = json.dumps(cl["items"])
        assert "DO-330" not in text and "Parameter Data Item" not in text and "DO-178C" not in text


def test_checklists_are_document_specific():
    q = {d: {i["question"] for i in load_builtin("DO-178C", s, d)["items"] if i["sheet"] in "BF"}
         for s, d in (("SOI-2", "SRD"), ("SOI-2", "SDD"), ("SOI-4", "SAS"))}
    assert not (q["SRD"] & q["SDD"]) and not (q["SDD"] & q["SAS"])


def test_dal_applicability():
    item = {"dal": "A, B", "applicability": "Mandatory"}
    assert applicability_for(item, "A")[0] and not applicability_for(item, "C")[0]
    assert not applicability_for({"dal": "All"}, "E")[0]


# ---------------------------------------------------------------------- checklists
def test_user_checklist_xlsx_preserves_wording(tmp_path):
    cl = read_user_checklist(make_user_checklist_xlsx(tmp_path / "u.xlsx"))
    assert [i["ref"] for i in cl["items"]] == ["UC-1", "UC-2"]
    assert cl["items"][0]["question"] == "Does the PSAC state the software level for each software item?"
    assert cl["items"][1]["dal"] == "A, B"


def test_user_checklist_docx(tmp_path):
    from docx import Document
    d = Document()
    t = d.add_table(rows=2, cols=3)
    for c, v in zip(t.rows[0].cells, ("ID", "Checklist Item", "Reference")):
        c.text = v
    for c, v in zip(t.rows[1].cells, ("D1", "Is the revision history complete?", "Template")):
        c.text = v
    p = tmp_path / "u.docx"
    d.save(str(p))
    cl = read_user_checklist(p)
    assert cl["items"][0]["ref"] == "D1" and cl["items"][0]["question"] == "Is the revision history complete?"


def test_user_checklist_pdf(tmp_path):
    p = make_pdf(tmp_path / "u.pdf", "1.1 Is the document number on every page?\n1.2 Is the software level declared?")
    cl = read_user_checklist(p)
    assert [i["ref"] for i in cl["items"]] == ["1.1", "1.2"]


def test_unreadable_checklist(tmp_path):
    p = make_txt(tmp_path / "x.pdf", "")
    with pytest.raises(Exception):
        read_user_checklist(make_pdf(tmp_path / "blank.pdf", "no numbered lines here"))


def test_combined_checklist(tmp_path):
    user = read_user_checklist(make_user_checklist_xlsx(tmp_path / "u.xlsx"))
    builtin = load_builtin("DO-178C", "SOI-1", "PSAC")
    comb = combine(builtin, user, "Combined")
    assert comb["items"][0]["ref"] == "UC-1" and len(comb["items"]) > len(user["items"])
    assert len(combine(builtin, user, "User")["items"]) == 2
    assert len(combine(builtin, user, "Built-in")["items"]) == len(builtin["items"])


def test_import_unical_workbook_ignores_previous_verdicts(tmp_path):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "A. Document Control"
    ws.append(["title"])
    ws.append(["Check ID", "Clause", "Criterion", "Reference", "Level", "Verdict", "Observation"])
    ws.append(["1.1 Cover"])
    ws.append(["A-01", "Cover", "Aeron cover carries the title", "Template p.1", "All", "NC", "secret project note"])
    p = tmp_path / "w.xlsx"
    wb.save(p)
    cl = import_unical_workbook(p, "DO-178C", "SOI-1", "PSAC")
    item = cl["items"][0]
    assert item["question"] == "the applicant cover carries the title" and "secret" not in json.dumps(cl)
    assert item["group"] == "1.1 Cover"


# ------------------------------------------------------------------------ engine
def _psac(tmp_path, text=PSAC_TEXT):
    return parse_document(make_pdf(tmp_path / "psac.pdf", text))


def test_rules_on_complete_document(tmp_path):
    doc = _psac(tmp_path)
    for rule in ("doc_number", "version_date", "states_dal", "signatories", "revision_history", "abbreviations",
                 "references"):
        assert run_rule(rule, doc)[0].startswith("Present"), rule


def test_missing_section_identified(tmp_path):
    text = "\n".join(l for l in PSAC_TEXT.splitlines() if "Revision History" not in l)
    state, obs, *_ = run_rule("revision_history", _psac(tmp_path, text))
    assert state == "Not Present"


def test_incomplete_section_identified(tmp_path):
    text = PSAC_TEXT.replace("Reviewed by: B. Reviewer   Approved by: C. Approver", "")
    assert run_rule("signatories", _psac(tmp_path, text))[0] == "Present-Incomplete"


def test_placeholders_found(tmp_path):
    doc = _psac(tmp_path, PSAC_TEXT + "\nThe value is TBD. Error! Reference source not found.")
    state, obs, quote, ref = run_rule("no_placeholders", doc)
    assert state == "Present-Inconsistent" and "TBD" in quote


def test_engine_findings_traceable_and_justified(tmp_path):
    text = "\n".join(l for l in PSAC_TEXT.splitlines() if "Revision History" not in l and "Software Level" not in l
                     and "software level" not in l.lower())
    doc = parse_document(make_pdf(tmp_path / "p.pdf", text))
    cl = load_builtin("DO-178C", "SOI-1", "SRS")  # authored checklist with rule items
    res = ReviewEngine().run(doc, "SRS", "DO-178C", "A", "SOI-1", cl)
    assert res.findings
    for f in res.findings:
        assert f.checks and f.rationale and f.recommendation and f.severity in ("Major", "Minor", "Observation")
        a = res.assessments[f.checks[0]]
        assert a.verdict in ("NC", "PC") and f.observation.startswith(f"[{a.item['ref']}]")
    dal_f = [f for f in res.findings if "states_dal" == res.assessments[f.checks[0]].item.get("rule")]
    assert dal_f and dal_f[0].severity == "Major"


def test_not_applicable_items(tmp_path):
    doc = _psac(tmp_path)
    cl = load_builtin("DO-178C", "SOI-3", "SVR")
    res = ReviewEngine().run(doc, "SVR", "DO-178C", "D", "SOI-3", cl)
    na = [a for a in res.assessments if a.verdict == "NA"]
    assert na and all(a.na_reason for a in na)
    assert any("MC/DC" in a.item["question"] or "modified condition" in a.item["question"] for a in na)


def test_dal_e_no_findings(tmp_path):
    res = ReviewEngine().run(_psac(tmp_path), "PSAC", "DO-178C", "E", "SOI-1", load_builtin("DO-178C", "SOI-1", "PSAC"))
    assert not res.findings and any("level E" in n for n in res.notes)


def test_unverifiable_items_stay_not_verified(tmp_path):
    res = ReviewEngine().run(_psac(tmp_path), "PSAC", "DO-178C", "A", "SOI-1", load_builtin("DO-178C", "SOI-1", "PSAC"))
    no_rule = [a for a in res.assessments if not a.item.get("rule") and a.applicable]
    assert no_rule and all(a.verdict == "NR" for a in no_rule)  # rule mode never claims compliance by keyword


def test_cross_document_inconsistency(tmp_path):
    psac = parse_document(make_txt(tmp_path / "p.txt", PSAC_TEXT))
    sdd = parse_document(make_txt(tmp_path / "s.txt", SDD_TEXT))  # states Level B, not quoted in PSAC
    res = ReviewEngine().run(psac, "PSAC", "DO-178C", "A", "SOI-1", load_builtin("DO-178C", "SOI-1", "PSAC"),
                             companions=[("SDD", sdd)])
    topics = {(c.topic, c.status) for c in res.consistency}
    assert ("dal", "Inconsistent") in topics
    assert any("Software level" in f.observation for f in res.findings)


def test_severity_rationale_not_keyword_based():
    sc = SeverityClassifier()
    sev, why = sc.classify({"sheet": "C", "reference": "Table A-7 obj.5"}, "NC", "A")
    assert sev == "Major" and "objective" in why
    sev2, why2 = sc.classify({"sheet": "C", "applicability": "Conditional", "condition": "If PDI used"}, "NC", "A")
    assert sev2 == "Minor" and "conditional" in why2
    assert sc.classify({"sheet": "F"}, "NC", "C")[0] == "Minor" and sc.classify({"sheet": "F"}, "NC", "A")[0] == "Major"


def test_overall_recommendation():
    assert overall_recommendation([{"severity": "Major", "status": "Open"}], {"C": 10}) == "NOT ACCEPTABLE"
    assert overall_recommendation([{"severity": "Minor", "status": "Open"}], {"C": 10}) == "ACCEPTABLE WITH COMMENTS"
    assert overall_recommendation([], {"C": 10}) == "ACCEPTABLE"
    assert overall_recommendation([], {"C": 1, "NR": 9}) == "REVIEW INCOMPLETE"


# ---------------------------------------------------------------------- local AI agent
class _FakeOllama(BaseHTTPRequestHandler):
    reply: dict = {}

    def log_message(self, *a):
        pass

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps({"models": [{"name": "test-model:latest"}]}).encode())

    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps({"response": json.dumps(_FakeOllama.reply)}).encode())


@pytest.fixture
def fake_ai():
    srv = HTTPServer(("127.0.0.1", 0), _FakeOllama)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield LocalAIAgent({"enabled": True, "model_name": "test-model", "endpoint": f"http://127.0.0.1:{srv.server_port}",
                        "timeout_seconds": 5})
    srv.shutdown()


def test_ai_rejects_remote_endpoint():
    with pytest.raises(ValueError):
        LocalAIAgent({"endpoint": "https://api.example.com"})


def test_ai_unavailable_falls_back_to_rules(tmp_path):
    agent = LocalAIAgent({"enabled": True, "model_name": "x", "endpoint": "http://127.0.0.1:9", "timeout_seconds": 1})
    res = ReviewEngine(ai_agent=agent).run(_psac(tmp_path), "PSAC", "DO-178C", "A", "SOI-1",
                                           load_builtin("DO-178C", "SOI-1", "SRS"), use_ai=True)
    assert res.analysis_mode == "Rule-based" and any("unavailable" in n for n in res.notes)


def test_ai_verified_quote_accepted(fake_ai, tmp_path):
    _FakeOllama.reply = {"verdict": "C", "evidence_state": "Present", "quote": "Software Level A applies.",
                         "page": "1", "section": "1", "observation": "Level stated", "recommendation": "",
                         "confidence": 0.9, "reasoning": "quoted"}
    doc = _psac(tmp_path)
    a = fake_ai.assess({"ref": "X", "question": "level?"}, "PSAC", "DO-178C", "A", "SOI-1", [("p.1", doc.text)], doc.text)
    assert a.verdict == "C" and a.verified_quote


def test_ai_invented_quote_rejected(fake_ai, tmp_path):
    _FakeOllama.reply = {"verdict": "C", "evidence_state": "Present", "quote": "This sentence is not in the document.",
                         "confidence": 0.95}
    doc = _psac(tmp_path)
    a = fake_ai.assess({"ref": "X", "question": "q"}, "PSAC", "DO-178C", "A", "SOI-1", [("p.1", doc.text)], doc.text)
    assert a.verdict == "PMR" and not a.verified_quote


def test_ai_low_confidence_pending_manual_review(fake_ai, tmp_path):
    _FakeOllama.reply = {"verdict": "NC", "evidence_state": "Not Present", "quote": "", "confidence": 0.2}
    doc = _psac(tmp_path)
    a = fake_ai.assess({"ref": "X", "question": "q"}, "PSAC", "DO-178C", "A", "SOI-1", [("p.1", doc.text)], doc.text)
    assert a.verdict == "PMR"


def test_ai_mode_in_engine(fake_ai, tmp_path):
    _FakeOllama.reply = {"verdict": "PC", "evidence_state": "Present-Incomplete", "quote": "Transition criteria shall be defined.",
                         "observation": "Criteria named but not defined", "recommendation": "Define the criteria.",
                         "confidence": 0.8}
    res = ReviewEngine(ai_agent=fake_ai).run(_psac(tmp_path), "PSAC", "DO-178C", "A", "SOI-1",
                                             load_builtin("DO-178C", "SOI-1", "SQAP"), use_ai=True)
    assert res.analysis_mode == "AI-assisted"
    ai = [a for a in res.assessments if a.origin == "AI"]
    assert ai and all(a.verdict == "PC" for a in ai)
    assert any(f.origin == "AI" for f in res.findings)
