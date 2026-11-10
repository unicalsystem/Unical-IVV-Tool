"""Synthetic test documents (no project data)."""
from __future__ import annotations

from pathlib import Path

PSAC_TEXT = """Plan for Software Aspects of Certification of Test Unit Software for Test Platform
Document No: TU-PSAC-0001   Version: 1.0   Date: 01/10/2026
Prepared by: A. Author   Reviewed by: B. Reviewer   Approved by: C. Approver
Revision History
Table of Contents
1 Introduction ........ 3
2 System Overview ........ 4
3 Software Overview ........ 5
4 Certification Considerations ........ 6
Acronyms and Abbreviations
PSAC Plan for Software Aspects of Certification. SDP Software Development Plan. SVP Software Verification Plan.
Reference Documents
SDP TU-SDP-0002 Version 1.0. SVP TU-SVP-0003 Version 1.0.
1 Introduction
This Plan for Software Aspects of Certification is submitted to the certification authority (RCMA).
The software is developed to RTCA DO-178C. Software Level A applies. Stage of Involvement SOI-1 to SOI-4 will be held.
2 System Overview
The system provides attitude data. The software level is Level A. Certification liaison with the authority shall be held.
3 Software Overview
The software shall run on a single-core processor. Means of compliance are described in the SVP.
4 Certification Considerations
The certification basis shall be agreed with the authority. Additional considerations are none.
5 Software Life Cycle
The software life cycle processes shall follow the SDP. Transition criteria shall be defined. Verification shall be
independent. Configuration management shall follow the SCMP. Quality assurance shall follow the SQAP.
6 Schedule
SOI-1 is planned in Month 1. Page 1 of 3
"""

SDD_TEXT = """Software Design Description of Test Unit
Document No: TU-SDD-0009 Version: 2.0 Date: 05/10/2026
Prepared by: Designer   Approved by: Lead
1 Architecture
The software architecture uses a cyclic executive. Data flow and control flow are shown in Figure 1.
2 Low-Level Requirements
LLR-001 The module shall compute heading. Traces to HLR-010.
3 Resource Usage
Memory map and timing margins are measured with the target analyser. Software Level B.
"""

HR_TEXT = """Employee Leave Policy
Employees can apply for annual leave through the HR portal. Sick leave requires a medical certificate.
Holidays are listed every January. Contact HR for queries about payroll and benefits.
"""


def make_docx(path: Path, text: str, headings: bool = True) -> Path:
    from docx import Document
    d = Document()
    for line in text.strip().splitlines():
        import re
        m = re.match(r"^(\d+)\s+([A-Z].*)$", line)
        if headings and m and "...." not in line:
            d.add_heading(line, level=1)
        else:
            d.add_paragraph(line)
    sec = d.sections[0]
    sec.footer.paragraphs[0].text = "TU-PSAC-0001  Page"
    d.save(str(path))
    return path


def make_pdf(path: Path, text: str, password: str | None = None) -> Path:
    import pymupdf
    doc = pymupdf.open()
    lines = text.strip().splitlines()
    for i in range(0, len(lines), 30):
        page = doc.new_page()
        page.insert_text((50, 60), "\n".join(lines[i:i + 30]), fontsize=9)
    if password:
        doc.save(str(path), encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw=password, user_pw=password)
    else:
        doc.save(str(path))
    doc.close()
    return path


def make_scanned_pdf(path: Path) -> Path:
    import pymupdf
    doc = pymupdf.open()
    page = doc.new_page()
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 200, 100), False)
    pix.set_rect(pix.irect, (255, 255, 255))
    page.insert_image(pymupdf.Rect(50, 50, 250, 150), pixmap=pix)
    doc.save(str(path))
    doc.close()
    return path


def make_txt(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def make_user_checklist_xlsx(path: Path) -> Path:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["S.No", "Section", "Review Question", "Expected Evidence", "Reference", "Level"])
    ws.append(["UC-1", "1", "Does the PSAC state the software level for each software item?", "Level statement",
               "DO-178C 11.1", "All"])
    ws.append(["UC-2", "6", "Is the SOI schedule given with dates?", "Schedule with dates", "DO-178C 11.1.i", "A, B"])
    wb.save(str(path))
    return path
