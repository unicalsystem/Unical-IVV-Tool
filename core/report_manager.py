"""Excel and Word review reports built on the Unical templates (Phase 7).

Excel: the Unical review checklist workbook (Instructions, Summary, Findings, sheets A-F)
is loaded as the base; sheet names, columns, header formats, colours, validations,
print settings and the Summary formula structure are kept and the rows refilled.
Word: the Unical review report is loaded as the base; cover, header/footer, styles,
tables and section structure are kept and the content replaced.
Only findings approved by a reviewer are reported.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import logging
import re
import zipfile
from datetime import datetime
from pathlib import Path

from core.app_context import AppContext, bundled_resource
from core.refs import humanise
from core.constants import DOCUMENT_TYPES, RECOMMENDATIONS, SHEETS, VERDICTS, doc_full_name
from database.db_manager import DatabaseManager

log = logging.getLogger(__name__)
SHEET_ORDER = ["A", "B", "C", "D", "E", "F"]
TEMPLATE_SHEETS = {"A": "A. Document Control", "B": "B. Template Compliance", "C": "C. DO-178C Objectives",
                   "D": "D. Traceability", "E": "E. Auditability", "F": "F. Content Depth"}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_filename(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_\-]+", "_", text).strip("_")[:80] or "Review"


def _human(row: dict) -> dict:
    """Write locations as 'Page 29, Section 3.8 ...' (also for reviews saved by older versions)."""
    row = dict(row)
    for k in ("page_ref", "observation", "recommendation"):
        if row.get(k):
            row[k] = humanise(row[k])
    return row


class ReportContext:
    """Everything the two reports need, read once from the database."""

    def __init__(self, ctx: AppContext, db: DatabaseManager, session_id: int):
        self.ctx, self.db, self.sid = ctx, db, session_id
        self.session = db.get_session(session_id)
        if not self.session:
            raise ValueError(f"Review session {session_id} not found.")
        self.documents = db.get_documents(session_id)
        self.primary = next((d for d in self.documents if d["role"] == "primary"), {})
        self.assessments = [_human(a) for a in db.get_assessments(session_id)]
        self.findings = [_human(f) for f in db.get_findings(session_id, approved_only=True)]
        self.results = json.loads(self.session.get("results_json") or "{}")
        rep = ctx.config.get("report", {})
        self.signatories = rep.get("signatories", {
            "prepared": {"name": "", "designation": "IV&V Engineer"},
            "checked": {"name": "", "designation": "IV&V Lead"},
            "approved": {"name": "", "designation": "IV&V Manager"}})
        self.company = ctx.config.get("company", "Unical Systems")
        s = self.session
        self.doc_type = s["document_type"]
        self.doc_name = doc_full_name(self.doc_type)
        self.customer = s.get("customer") or rep.get("default_customer", "the applicant")
        self.project = s.get("project") or "-"
        self.date = datetime.now().strftime("%d-%m-%Y")
        self.report_no = s.get("report_doc_no") or (
            f"UNI-RR-{safe_filename(self.project)[:12].upper()}-{self.doc_type}-{session_id:04d}-R{s['review_version']}")
        self.classification = rep.get("classification") or f"{self.company} & {self.customer} - Confidential"

    @property
    def counts_by_sheet(self) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {}
        for a in self.assessments:
            sh = a["sheet"] if a["sheet"] in SHEET_ORDER else "U"
            d = out.setdefault(sh, {})
            d[a["verdict"]] = d.get(a["verdict"], 0) + 1
            d["total"] = d.get("total", 0) + 1
        return out

    def severity_counts(self) -> dict[str, int]:
        c = {"Major": 0, "Minor": 0, "Observation": 0}
        for f in self.findings:
            c[f["severity"]] = c.get(f["severity"], 0) + 1
        return c


# ===================================================================================== Excel
def _logo_image():
    from openpyxl.drawing.image import Image as XLImage
    p = bundled_resource("assets/unical_logo.png")
    if not p.exists():
        return None
    img = XLImage(str(p))
    img.width, img.height = 170, 43
    return img


def _copy_style(src, dst) -> None:
    if src.has_style:
        dst.font = copy.copy(src.font)
        dst.fill = copy.copy(src.fill)
        dst.border = copy.copy(src.border)
        dst.alignment = copy.copy(src.alignment)
        dst.number_format = src.number_format
        dst.protection = copy.copy(src.protection)


def _strip_rich_logo(path: Path) -> bytes:
    """Remove the in-cell (richData) picture parts that openpyxl cannot keep, so the
    workbook loads cleanly; the logo is re-inserted as a normal picture."""
    buf = io.BytesIO()
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.startswith("xl/richData/") or item.filename == "xl/metadata.xml":
                continue
            if item.filename == "[Content_Types].xml":
                data = re.sub(rb'<Override[^>]*(richData|metadata)[^>]*/>', b"", data)
            if item.filename == "xl/_rels/workbook.xml.rels":
                data = re.sub(rb'<Relationship[^>]*(richData|metadata|richValue)[^>]*/>', b"", data)
            if item.filename.startswith("xl/worksheets/sheet") and item.filename.endswith(".xml"):
                data = re.sub(rb'(<c r="A1"[^>]*?) vm="\d+"', rb"\1", data)
                data = re.sub(rb'<c r="A1"([^>]*?) t="e"([^>]*)><v>#VALUE!</v></c>', rb'<c r="A1"\1\2/>', data)
            zout.writestr(item, data)
    return buf.getvalue()


def build_excel(rc: ReportContext, out_path: Path) -> Path:
    from openpyxl import load_workbook
    from openpyxl.worksheet.datavalidation import DataValidation

    tpl = bundled_resource("templates/excel/Unical_Review_Checklist_Template_REFERENCE.xlsx")
    wb = load_workbook(io.BytesIO(_strip_rich_logo(tpl)))
    std = rc.session["standard"]
    dt = rc.doc_type

    def put_logo(ws):
        ws["A1"].value = None
        img = _logo_image()
        if img:
            ws.add_image(img, "A1")

    # ---------------------------------------------------------------- checklist sheets
    by_sheet: dict[str, list[dict]] = {k: [] for k in SHEET_ORDER + ["U"]}
    for a in rc.assessments:
        by_sheet[a["sheet"] if a["sheet"] in SHEET_ORDER else "U"].append(a)
    if by_sheet["U"]:
        src = wb[TEMPLATE_SHEETS["F"]]
        u = wb.copy_worksheet(src)
        u.title = "U. User Checklist"
    ranges: dict[str, tuple[str, int, int]] = {}
    for code in SHEET_ORDER + (["U"] if by_sheet["U"] else []):
        ws = wb[TEMPLATE_SHEETS[code]] if code != "U" else wb["U. User Checklist"]
        if code == "C":
            ws.title = f"C. {std} Objectives"
        put_logo(ws)
        title = SHEETS.get(code, "User Checklist").upper()
        ws["A2"].value = f"{code} - {title}  ({dt} {rc.primary.get('doc_number', '')}, {std} Level {rc.session['dal']})"
        for col in ("B3", "G3"):
            if ws[col].value:
                ws[col].value = re.sub(r"\bSQAP\b", dt, str(ws[col].value))
        group_proto = [copy.copy(ws.cell(4, c)) for c in range(1, 12)]
        item_proto = [copy.copy(ws.cell(5, c)) for c in range(1, 12)]
        item_height = 60
        for rng in list(ws.merged_cells.ranges):
            if rng.min_row >= 4:
                ws.unmerge_cells(str(rng))
        ws.delete_rows(4, ws.max_row)
        r = 4
        group = None
        first_item = None
        for a in by_sheet[code]:
            g = a["group_title"] or ""
            if g != group:
                group = g
                if g:
                    for c in range(1, 12):
                        _copy_style(group_proto[c - 1], ws.cell(r, c))
                    ws.cell(r, 1).value = g
                    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=9)
                    ws.row_dimensions[r].height = 19.5
                    r += 1
            vals = [a["checklist_ref"], a["section_number"], a["review_question"], a["reference"],
                    a["dal_applicability"] if a["applicability"] != "Conditional" else a["condition_text"],
                    a["verdict"], " ".join(x for x in (a["observation"], ("Evidence: " + a["evidence"]) if a["evidence"]
                                                       else "", ("[" + a["page_ref"] + "]") if a["page_ref"] else "") if x),
                    "", a.get("finding_nos") or "", a["recommendation"] or "", ""]
            sev = ""
            if a.get("finding_nos"):
                for f in rc.findings:
                    if f["finding_no"] in (a["finding_nos"] or ""):
                        sev = f["severity"]
                        break
            vals[7] = sev
            for c, v in enumerate(vals, 1):
                cell = ws.cell(r, c)
                _copy_style(item_proto[c - 1], cell)
                cell.value = v
            ws.row_dimensions[r].height = max(item_height, min(300, 15 * (1 + len(str(vals[2])) // 60)))
            first_item = first_item or r
            r += 1
        last = max(r - 1, 5)
        ranges[code] = (ws.title, first_item or 5, last)
        # validations: refresh ranges to the new rows
        ws.data_validations.dataValidation = []
        dv1 = DataValidation(type="list", formula1='"C,PC,NC,NA,NR,PCL,PMR"', allow_blank=True)
        dv2 = DataValidation(type="list", formula1='"Major,Minor,Observation,NA"', allow_blank=True)
        ws.add_data_validation(dv1)
        ws.add_data_validation(dv2)
        dv1.add(f"F4:F{last}")
        dv2.add(f"H4:H{last}")
        cf_rules = []
        for cf in ws.conditional_formatting:
            cf_rules.extend(cf.rules)
        from openpyxl.formatting.formatting import ConditionalFormattingList
        ws.conditional_formatting = ConditionalFormattingList()
        for rule in cf_rules:
            ws.conditional_formatting.add(f"F4:F{last}", rule)
        rr = last + 2
        ws.cell(rr, 1).value = "Classification"
        ws.cell(rr, 3).value = rc.classification
        ws.cell(rr, 1).font = copy.copy(group_proto[0].font)

    # ------------------------------------------------------------------- findings
    ws = wb["Findings"]
    put_logo(ws)
    ws["A2"].value = (f"OBSERVATION REGISTER - {rc.customer} {dt} {rc.primary.get('doc_number', '')} "
                      f"({rc.project})")
    ws["M3"].value = f"{rc.customer} Remark"
    proto = [copy.copy(ws.cell(4, c)) for c in range(1, 14)]
    for rng in list(ws.merged_cells.ranges):
        if rng.min_row >= 4:
            ws.unmerge_cells(str(rng))
    ws.delete_rows(4, ws.max_row)
    round_label = {1: "1st review", 2: "2nd review", 3: "3rd review"}.get(rc.session.get("review_round") or 1,
                                                                         f"Review {rc.session.get('review_round')}")
    r = 4
    for f in rc.findings:
        refs = [x.strip() for x in (f.get("checklist_refs") or "").split(",") if x.strip()]
        cols = refs[:6] + [""] * (6 - len(refs[:6]))
        if len(refs) > 6:
            cols[5] = ", ".join(refs[5:])
        text = f["observation"]
        if f.get("evidence"):
            text += f"\nEvidence: {f['evidence']}" + (f" [{f['page_ref']}]" if f.get("page_ref") else "")
        text += f"\nRecommendation: {f['recommendation']}"
        vals = [f["finding_no"], f["severity"], text, f"=COUNTA(E{r}:J{r})", *cols, round_label, f["status"],
                f.get("customer_response") or ""]
        for c, v in enumerate(vals, 1):
            cell = ws.cell(r, c)
            _copy_style(proto[c - 1], cell)
            cell.value = v
        ws.row_dimensions[r].height = min(400, 15 * (2 + len(text) // 90))
        r += 1
    last_f = max(r - 1, 4)
    ws.data_validations.dataValidation = []
    dv = DataValidation(type="list", formula1='"Major,Minor,Observation"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"B4:B{last_f}")
    dv2 = DataValidation(type="list", formula1='"Open,Closed,Closed with comment,Not Closed,Pending Clarification,'
                                                'Withdrawn"', allow_blank=True)
    ws.add_data_validation(dv2)
    dv2.add(f"L4:L{last_f}")
    ws.cell(last_f + 2, 1).value = "Classification"
    ws.cell(last_f + 2, 3).value = rc.classification

    # ------------------------------------------------------------------- summary
    ws = wb["Summary"]
    put_logo(ws)
    labels = {"A": "1. Document Control", "B": "2. Template Compliance", "C": f"3. {std} Objectives",
              "D": "4. Inter-Plan Traceability", "E": "5. Editorial & Auditability", "F": "6. Content Depth"}
    for i, code in enumerate(SHEET_ORDER):
        row = 5 + i
        name, a, b = ranges[code]
        q = f"'{name}'"
        ws.cell(row, 1).value = labels[code]
        for col, v in ((2, "C"), (3, "PC"), (4, "NC")):
            ws.cell(row, col).value = f'=COUNTIF({q}!$F${a}:$F${b},"{v}")'
        ws.cell(row, 5).value = f'=COUNTIF({q}!$A${a}:$A${b},"{code}-*")'
    extra = ""
    if "U" in ranges:
        name, a, b = ranges["U"]
        q = f"'{name}'"
        extra = (f'+COUNTIF({q}!$F${a}:$F${b},"{{v}}")')
        ws.cell(12, 1).value = "of which: User checklist"
        for col, v in ((2, "C"), (3, "PC"), (4, "NC")):
            ws.cell(12, col).value = f'=COUNTIF({q}!$F${a}:$F${b},"{v}")'
        ws.cell(12, 5).value = f'=COUNTA({q}!$F${a}:$F${b})'
    for col, v in ((2, "C"), (3, "PC"), (4, "NC")):
        L = "BCD"[col - 2]
        ws.cell(11, col).value = f"=SUM({L}5:{L}10)" + (extra.replace("{v}", v) if extra else "")
    ws.cell(11, 5).value = "=SUM(E5:E10)" + (f"+E12" if "U" in ranges else "")
    for row, sev in ((14, "Major"), (15, "Minor"), (16, "Observation")):
        ws.cell(row, 2).value = f'=COUNTIF(Findings!B4:B{last_f},"{sev}")'
    for row, sev in ((21, "Major"), (22, "Minor"), (23, "Observation")):
        parts = [f"COUNTIF('{ranges[c][0]}'!$H${ranges[c][1]}:$H${ranges[c][2]},\"{sev}\")" for c in ranges]
        ws.cell(row, 2).value = "=" + "+".join(parts)
    ws.cell(20, 1).value = "Checks not yet concluded (NR / PCL / PMR)"
    rec = rc.session.get("recommendation") or ""
    ws.cell(27, 2).value = f"{rec}: " + RECOMMENDATIONS.get(rec, "").format(doc=dt) if rec else ""
    sig = rc.signatories
    ws.cell(30, 2).value = f"{sig['checked']['name']}, {sig['checked']['designation']} - {rc.date}"
    ws.cell(31, 2).value = f"{sig['approved']['name']}, {sig['approved']['designation']} - {rc.date}"
    ws.cell(33, 2).value = rc.classification

    # --------------------------------------------------------------- instructions
    ws = wb["Instructions"]
    put_logo(ws)
    ws["A2"].value = f"UNICAL  |  IV&V REVIEW CHECKLIST - {rc.doc_name.upper()}"
    ws["A3"].value = f"Reviewed item: {rc.customer} {dt} {rc.primary.get('doc_number', '')} ({rc.project})"
    ws["B7"].value = f"{std} Objectives"
    if ws["D7"].value:
        ws["D7"].value = f"RTCA/{std} + Annex A tables"
    for cell in ("B22", "B23"):
        if ws[cell].value:
            ws[cell].value = re.sub(r"\bSQAP\b", dt, str(ws[cell].value))
    rows = [(f"{dt} document no. under review", rc.primary.get("doc_number") or "-"),
            (f"{dt} issue / revision & date", f"{rc.primary.get('doc_version') or '-'}"
                                             f" / {rc.results.get('document', {}).get('date', '')}"),
            ("LRU / System name", rc.session.get("system_lru") or rc.project),
            ("Software criticality level (DAL)", f"{std} Level {rc.session['dal']}"),
            ("Unical review report no.", rc.report_no),
            ("Reviewer(s) name & designation", f"{sig['prepared']['name']}, {sig['prepared']['designation']}\n"
                                               f"{rc.company}"),
            ("Review start / completion date", f"{rc.session['started_at'][:10]} / "
                                               f"{(rc.session.get('completed_at') or '')[:10] or rc.date}")]
    for i, (k, v) in enumerate(rows):
        ws.cell(27 + i, 1).value = k
        ws.cell(27 + i, 2).value = v
    ws.cell(35, 2).value = rc.classification
    ws.cell(37, 1).value = "Additional verdict codes used by the review tool"
    for i, code in enumerate(("C", "NA", "NR", "PCL", "PMR")):
        ws.cell(38 + i, 1).value = code
        ws.cell(38 + i, 2).value = VERDICTS[code]
    ws.cell(43, 1).value = (f"Analysis mode: {rc.session.get('analysis_mode')}. Only reviewer-approved findings are "
                            "reported. Generated by the Unical DO-178 IV&V Review Tool.")

    label = f"Unical IV&V - {dt} Review Checklist ({rc.project})"
    for ws in wb.worksheets:
        for hf in (ws.oddHeader, ws.oddFooter, ws.evenHeader, ws.evenFooter, ws.firstHeader, ws.firstFooter):
            for part in (hf.left, hf.center, hf.right):
                if part.text and re.search(r"SQAP|GLO-MSU|Aeron|Review Checklist", part.text):
                    part.text = label
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    return out_path


# ===================================================================================== Word
def _set_cell(cell, text: str, para_index: int | None = None) -> None:
    """Replace a cell's text keeping the first run's formatting."""
    paras = cell.paragraphs
    if para_index is not None:
        if para_index < len(paras):
            _set_para(paras[para_index], text)
        return
    _set_para(paras[0], text)
    for p in paras[1:]:
        p._element.getparent().remove(p._element)


def _set_para(p, text: str) -> None:
    runs = p.runs
    lines = str(text).split("\n")
    if runs:
        runs[0].text = lines[0]
        for r in runs[1:]:
            r._element.getparent().remove(r._element)
        run = runs[0]
    else:
        run = p.add_run(lines[0])
    for line in lines[1:]:
        run.add_break()
        run.add_text(line)


def _clone_row(table, proto_tr):
    new = copy.deepcopy(proto_tr)
    table._tbl.append(new)
    from docx.table import _Row
    return _Row(new, table)


def _rebuild_rows(table, header_rows: int, rows: list[list[str]], proto_index: int | None = None) -> None:
    proto_index = header_rows if proto_index is None else proto_index
    proto = copy.deepcopy(table.rows[proto_index]._tr)
    for r in list(table.rows)[header_rows:]:
        r._tr.getparent().remove(r._tr)
    for values in rows:
        row = _clone_row(table, proto)
        cells = row.cells
        seen = []
        for i, v in enumerate(values):
            if i < len(cells) and cells[i]._tc not in seen:
                _set_cell(cells[i], v)
                seen.append(cells[i]._tc)


def _body_blocks(doc):
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    for child in doc.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            yield Paragraph(child, doc)
        elif tag == "tbl":
            yield Table(child, doc)


def _replace_section_text(doc, heading_text: str, paragraphs: list[str]) -> None:
    """Replace the Normal paragraphs that follow a heading (up to the next table/heading)."""
    from docx.text.paragraph import Paragraph
    blocks = list(_body_blocks(doc))
    for i, b in enumerate(blocks):
        if isinstance(b, Paragraph) and b.style.name.startswith("Heading") and b.text.strip().startswith(heading_text):
            body = []
            for nb in blocks[i + 1:]:
                if not isinstance(nb, Paragraph) or nb.style.name.startswith("Heading"):
                    break
                body.append(nb)
            if not body:
                return
            proto = body[0]
            for p in body[1:]:
                p._element.getparent().remove(p._element)
            _set_para(proto, paragraphs[0] if paragraphs else "")
            anchor = proto._element
            for text in paragraphs[1:]:
                new = copy.deepcopy(proto._element)
                anchor.addnext(new)
                _set_para(Paragraph(new, proto._parent), text)
                anchor = new
            return


def _toc_field(doc) -> None:
    """Replace the static contents list with a Word TOC field (updated on open)."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.text.paragraph import Paragraph
    blocks = list(_body_blocks(doc))
    start = next((i for i, b in enumerate(blocks) if isinstance(b, Paragraph) and b.text.strip() == "CONTENTS"), None)
    if start is None:
        return
    toc_paras = []
    for b in blocks[start + 1:]:
        if not isinstance(b, Paragraph) or b.style.name.startswith("Heading"):
            break
        if "\t" in b.text or re.match(r"^\d+(\.\d+)*\s", b.text):
            toc_paras.append(b)
        elif b.text.strip():
            break
    if not toc_paras:
        return
    first = toc_paras[0]
    for p in toc_paras[1:]:
        p._element.getparent().remove(p._element)
    for r in first.runs:
        r._element.getparent().remove(r._element)
    run = first.add_run()
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = 'TOC \\o "1-2" \\h \\z \\u'
    fld_sep = OxmlElement("w:fldChar")
    fld_sep.set(qn("w:fldCharType"), "separate")
    txt = OxmlElement("w:t")
    txt.text = "Right-click and choose 'Update Field' to refresh the table of contents."
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    for el in (fld_begin, instr, fld_sep, txt, fld_end):
        run._r.append(el)
    settings = doc.settings.element
    upd = settings.find(qn("w:updateFields"))
    if upd is None:
        upd = OxmlElement("w:updateFields")
        settings.append(upd)
    upd.set(qn("w:val"), "true")


def build_word(rc: ReportContext, out_path: Path) -> Path:
    from docx import Document
    tpl = bundled_resource("templates/word/Unical_Review_Report_Template_REFERENCE.docx")
    doc = Document(str(tpl))
    s, dt, std, dal = rc.session, rc.doc_type, rc.session["standard"], rc.session["dal"]
    sig = rc.signatories
    prim = rc.primary
    res = rc.results
    dinfo = res.get("document", {})
    t = doc.tables
    sev = rc.severity_counts()
    total_checks = len(rc.assessments)
    rec = s.get("recommendation") or "REVIEW INCOMPLETE"

    # ---------------- cover
    _set_cell(t[0].rows[0].cells[2], rc.report_no)
    _set_cell(t[0].rows[1].cells[2], f"{s.get('review_round') or 1}.0")
    _set_cell(t[0].rows[1].cells[3], f"Issue Date: {rc.date}")
    _set_cell(t[0].rows[2].cells[3], "No. of Pages: see footer")
    title_cell = t[1].rows[1].cells[0]
    for i, txt in enumerate(["REVIEW REPORT", "on the", rc.doc_name.upper(), f"of {s.get('system_lru') or rc.project}",
                             f"submitted by {rc.customer} (Design Agency)"]):
        _set_cell(title_cell, txt, i)
    _set_cell(t[1].rows[1].cells[1], f"IV&V of {rc.project}")
    _set_cell(t[1].rows[2].cells[1], s.get("part_number") or "-", 1)
    _set_cell(t[1].rows[3].cells[1], f"{std} Level {dal}", 1)
    _set_cell(t[1].rows[4].cells[1], f"{dt} under review (No., Iss/Rev, date):", 0)
    _set_cell(t[1].rows[4].cells[1], f"No: {prim.get('doc_number') or '-'}, {prim.get('doc_version') or '-'}, "
                                     f"{dinfo.get('date', '')}", 1)
    for row, key in zip(t[2].rows[1:4], ("prepared", "checked", "approved")):
        _set_cell(row.cells[1], f"{sig[key]['name']}, {sig[key]['designation']}", 0)
        _set_cell(row.cells[1], f"{rc.company} (IV&V)", 1)
    _rebuild_rows(t[3], 1, [["01", "Head of Design Agency", rc.customer],
                            ["02", "Certification Authority", s.get("certification_basis") or "As applicable"],
                            ["03", "Project Leader / Design Representative", rc.customer],
                            ["04", "IV&V", rc.company]])
    _rebuild_rows(t[4], 1, [[f"0{s.get('review_round') or 1}, 00", rc.date, "NA",
                             "Initial issue" if (s.get("review_round") or 1) == 1 else "Closure re-review",
                             "NA", "NA", rc.date]])
    _toc_field(doc)

    # ---------------- section 1
    _replace_section_text(doc, "1.1", [
        f"This report records the outcome of the independent review carried out by {rc.company}, acting as the "
        f"Independent Verification and Validation (IV&V) agency, of the {rc.doc_name} ({dt}) prepared and submitted "
        f"by {rc.customer} (Design Agency), document No. {prim.get('doc_number') or '-'}, for {rc.project}.",
        f"It records {rc.company}'s observations and the recommendation on whether the {dt} is fit to be baselined and "
        f"submitted to the certification authority. Customer responses and closure verification are recorded in "
        f"later issues of this report."])
    companions = res.get("companions", [])
    _replace_section_text(doc, "1.2", [
        f"The {dt} was reviewed against:",
        f"(a) Format and content compliance with the applicable authority template and RTCA/{std} Section 11 "
        f"({DOCUMENT_TYPES.get(dt, ('', '', '-'))[2] if std == 'DO-178C' else DOCUMENT_TYPES.get(dt, ('', '', '', '-'))[3]});",
        f"(b) Content adequacy against the {std} objectives applicable at software level {dal};",
        "(c) Consistency with the companion documents" + (f" supplied for this review ({', '.join(c['type'] for c in companions)})"
                                                          if companions else " (none supplied - cross-checks recorded as 'could not verify')") + ";",
        "(d) Engineering depth and auditability against accepted practice.",
        "This is a review document only. It does not constitute an assessment of the software product or of the "
        "processes as actually performed."])
    _replace_section_text(doc, "1.3", ["The following documents were used or referenced during this review."])
    refs = [["1", prim.get("doc_title") or rc.doc_name, prim.get("doc_number") or "-", prim.get("doc_version") or "-",
             dinfo.get("date", "")],
            ["2", "Software Considerations in Airborne Systems and Equipment Certification", f"RTCA/{std}", "-",
             "13 Dec 2011" if std == "DO-178C" else "1 Dec 1992"]]
    if std == "DO-178C":
        refs.append(["3", "Software Tool Qualification Considerations", "RTCA/DO-330", "-", "13 Dec 2011"])
    refs.append([str(len(refs) + 1), f"Unical {dt} Review Checklist", res.get("checklist", {}).get("name", "-"), "1.0",
                 rc.date])
    for c in companions:
        refs.append([str(len(refs) + 1), f"{doc_full_name(c['type'])} (companion)", c.get("doc_number") or "-",
                     c.get("version") or "-", ""])
    _rebuild_rows(t[5], 1, refs)

    # ---------------- section 2
    rows6 = [[f"{dt} document number", prim.get("doc_number") or "-"],
             ["Title", prim.get("doc_title") or "-"],
             ["Issue / Revision and date", f"{prim.get('doc_version') or '-'}, {dinfo.get('date', '')}"],
             ["Number of pages", str(prim.get("page_count") or "-")],
             ["File reviewed (SHA-256)", f"{prim.get('file_name', '')} ({(prim.get('sha256') or '')[:16]}...)"],
             ["Declared software level(s)", ", ".join(dinfo.get("dal_mentions") or []) or "Not stated"],
             ["Review round", {1: "First review", 2: "Second review (closure)"}.get(s.get("review_round") or 1,
                                                                                 f"Round {s.get('review_round')}")]]
    _rebuild_rows(t[6], 0, rows6)

    # ---------------- section 3
    _replace_section_text(doc, "3.1", [
        f"The review was carried out clause by clause using the Unical {dt} Review Checklist ({total_checks} checks in "
        f"the sheets Document Control, Template Compliance, {std} Objectives, Traceability, Auditability and Content "
        f"Depth). Each check received a verdict (C, PC, NC, NA, NR). The Unical DO-178 IV&V Review Tool was used in "
        f"{s.get('analysis_mode', 'Rule-based')} mode to locate evidence; every verdict and finding was confirmed by "
        f"the reviewer before inclusion in this report."])
    _rebuild_rows(t[7], 1, [[str(i + 1), sig[k]["name"], sig[k]["designation"], rc.company, rc.date]
                            for i, k in enumerate(("prepared", "checked", "approved"))])
    _replace_section_text(doc, "3.3", [
        f"The {dt} is recommended for acceptance when every applicable check carries a verdict, no Major observation "
        "remains open, and Minor observations are either closed or accepted with a recorded justification."])

    # ---------------- section 4
    by = rc.counts_by_sheet
    names = {"A": "1. Document Control", "B": "2. Template Compliance", "C": f"3. {std} Objectives",
             "D": "4. Traceability", "E": "5. Auditability", "F": "6. Content Depth", "U": "7. User Checklist"}
    rows8 = []
    tot = {"C": 0, "PC": 0, "NC": 0, "total": 0}
    for code in SHEET_ORDER + ["U"]:
        if code in by:
            d = by[code]
            rows8.append([names[code], str(d.get("C", 0)), str(d.get("PC", 0)), str(d.get("NC", 0)), str(d["total"])])
            for k in tot:
                tot[k] += d.get(k, 0)
    rows8.append(["TOTAL", str(tot["C"]), str(tot["PC"]), str(tot["NC"]), str(tot["total"])])
    _rebuild_rows(t[8], 1, rows8)
    n_f = len(rc.findings)
    _rebuild_rows(t[9], 1, [["Major", str(sev["Major"]), "", str(sev["Major"])],
                            ["Minor", str(sev["Minor"]), "", str(sev["Minor"])],
                            ["Observation", str(sev["Observation"]), "", str(sev["Observation"])],
                            ["Total", str(n_f), "", str(n_f)]])
    from docx.text.paragraph import Paragraph
    for b in _body_blocks(doc):
        if isinstance(b, Paragraph) and b.text.strip().startswith("*The "):
            _set_para(b, f"*The {n_f} findings are derived from the {total_checks} checklist items reviewed.")
            break
    majors = [f for f in rc.findings if f["severity"] == "Major"]
    principal = [f"The review raised {sev['Major']} Major, {sev['Minor']} Minor and {sev['Observation']} Observation "
                 f"finding(s)."]
    for f in (majors or rc.findings)[:6]:
        obs = re.sub(r"^\[[^\]]+\]\s*", "", f["observation"])[:300]
        principal.append(f"{f['finding_no']} ({f['severity']}): {obs}")
    if res.get("not_supplied"):
        principal.append("Companion documents referred to but not supplied (cross-references not verified): "
                         + ", ".join(res["not_supplied"]) + ".")
    _replace_section_text(doc, "4.3", principal)
    W14 = "http://schemas.microsoft.com/office/word/2010/wordml"
    WNS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    for row in t[10].rows:
        key = row.cells[0].text.strip()
        if key not in RECOMMENDATIONS:
            continue
        chosen = key == rec
        for el in row._tr.iter(f"{{{W14}}}checked"):
            el.set(f"{{{W14}}}val", "1" if chosen else "0")
        for sdt in row._tr.iter(f"{{{WNS}}}sdt"):
            for tnode in sdt.iter(f"{{{WNS}}}t"):
                if tnode.text in ("☐", "☑", "☒"):
                    tnode.text = "☑" if chosen else "☐"
        _set_cell(row.cells[1], RECOMMENDATIONS[key].format(doc=dt))

    # ---------------- section 5 observation register
    t11 = t[11]
    _set_cell(t11.rows[0].cells[0], f"OBSERVATION REGISTER - {rc.customer} {dt} {prim.get('doc_number') or ''}")
    round_label = {1: "1st Review", 2: "2nd Review"}.get(s.get("review_round") or 1, f"Review {s.get('review_round')}")
    rows11 = []
    for f in rc.findings:
        text = f["observation"]
        if f.get("evidence"):
            text += f"\nEvidence: {f['evidence'][:400]}" + (f" [{f['page_ref']}]" if f.get("page_ref") else "")
        text += f"\nRecommendation: {f['recommendation']}"
        rows11.append([f["finding_no"], f["severity"], text, str(f.get("n_checks") or 0), round_label, f["status"]])
    if not rows11:
        rows11 = [["-", "-", "No findings raised.", "0", round_label, "-"]]
    _rebuild_rows(t11, 2, rows11)
    # replace 'SQAP' / customer leftovers in the fixed definition tables
    for tb in (t[12], t[13], t[14]):
        for row in tb.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    if re.search(r"\bSQAP\b|Aeron", p.text):
                        _set_para(p, re.sub(r"\bSQAP\b", dt, p.text).replace("Aeron", rc.customer))
    _rebuild_rows(t[15], 1, [[sig["checked"]["name"], "Reviewer - Unical IV&V", "", ""],
                             [sig["approved"]["name"], "IV&V Lead - Unical", "", ""],
                             ["", f"Acknowledged - {rc.customer} Project Leader", "", ""]])
    for p in doc.paragraphs:
        if re.search(r"\bSQAP\b|Aeron", p.text) and not p.style.name.startswith("Heading"):
            _set_para(p, re.sub(r"\bSQAP\b", dt, p.text).replace("Aeron", rc.customer))

    # ---------------- footers
    for sec in doc.sections:
        for tb in sec.footer.tables:
            for row in tb.rows:
                for cell in row.cells:
                    txt = cell.text
                    if txt.startswith("Doc No."):
                        _set_cell(cell, f"Doc No.  {rc.report_no}")
                    elif txt.startswith("Date:"):
                        _set_cell(cell, f"Date:{rc.date}")
                    elif txt.startswith("Issue:"):
                        _set_cell(cell, f"Issue:0{s.get('review_round') or 1}")
            names_row = tb.rows[1] if len(tb.rows) > 1 else None
            if names_row:
                for i, key in enumerate(("prepared", "checked", "approved")):
                    if i < len(names_row.cells) and not names_row.cells[i].text.startswith(("Issue", "Page")):
                        _set_cell(names_row.cells[i], sig[key]["name"].split(",")[0])
    doc.core_properties.title = f"Review Report on the {dt} - {rc.project}"
    doc.core_properties.author = rc.company
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))
    return out_path


# ===================================================================================== API
def default_filename(rc: ReportContext, ext: str) -> str:
    s = rc.session
    return (f"{safe_filename(rc.project)}_{s['standard'].replace('-', '')}_DAL{s['dal']}_{s['soi_stage'].replace('-', '')}_"
            f"{s['document_type']}_Review_Report_v{s['review_version']}.{ext}")


def generate_reports(ctx: AppContext, db: DatabaseManager, session_id: int, out_dir: Path, username: str,
                     overwrite: bool = False) -> list[Path]:
    rc = ReportContext(ctx, db, session_id)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for ext, builder, kind in (("xlsx", build_excel, "Excel"), ("docx", build_word, "Word")):
        target = out_dir / default_filename(rc, ext)
        n = 2
        while target.exists() and not overwrite:  # protect earlier reports
            target = out_dir / default_filename(rc, ext).replace(f".{ext}", f"_{n}.{ext}")
            n += 1
        builder(rc, target)
        db.add_report(session_id, kind, str(target), _sha(target), username)
        paths.append(target)
    db.audit(username, "REPORTS_GENERATED", f"session {session_id}: " + ", ".join(p.name for p in paths))
    return paths
