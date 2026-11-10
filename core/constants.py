"""Shared vocabulary: standards, DAL, SOI stages, document types, verdicts, severities."""
from __future__ import annotations

STANDARDS = ("DO-178B", "DO-178C")
DALS = ("A", "B", "C", "D", "E")
SOI_STAGES = ("SOI-1", "SOI-2", "SOI-3", "SOI-4")
SOI_TITLES = {
    "SOI-1": "Planning Review",
    "SOI-2": "Development Review",
    "SOI-3": "Verification Review",
    "SOI-4": "Final Certification Review",
}

# code -> (full name, SOI, DO-178C section, DO-178B section)
DOCUMENT_TYPES: dict[str, tuple[str, str, str, str]] = {
    "PSAC": ("Plan for Software Aspects of Certification", "SOI-1", "11.1", "11.1"),
    "SDP": ("Software Development Plan", "SOI-1", "11.2", "11.2"),
    "SVP": ("Software Verification Plan", "SOI-1", "11.3", "11.3"),
    "SCMP": ("Software Configuration Management Plan", "SOI-1", "11.4", "11.4"),
    "SQAP": ("Software Quality Assurance Plan", "SOI-1", "11.5", "11.5"),
    "SRS": ("Software Requirements Standards", "SOI-1", "11.6", "11.6"),
    "SDS": ("Software Design Standards", "SOI-1", "11.7", "11.7"),
    "SCS": ("Software Code Standards", "SOI-1", "11.8", "11.8"),
    "IVVP": ("Independent Verification and Validation Plan", "SOI-1", "-", "-"),
    "SRD": ("Software Requirements Data", "SOI-2", "11.9", "11.9"),
    "SDD": ("Software Design Description", "SOI-2", "11.10", "11.10"),
    "CODE": ("Source Code / Code Review Records", "SOI-2", "11.11", "11.11"),
    "TRACE": ("Trace Data", "SOI-2", "11.21", "-"),
    "SVCP": ("Software Verification Cases and Procedures", "SOI-3", "11.13", "11.13"),
    "SVR": ("Software Verification Results", "SOI-3", "11.14", "11.14"),
    "PR": ("Problem Reports", "SOI-3", "11.17", "11.17"),
    "SCI": ("Software Configuration Index", "SOI-4", "11.16", "11.16"),
    "SECI": ("Software Life Cycle Environment Configuration Index", "SOI-4", "11.15", "11.15"),
    "SAS": ("Software Accomplishment Summary", "SOI-4", "11.20", "11.20"),
    "SCMR": ("Software Configuration Management Records", "SOI-4", "11.18", "11.18"),
    "SQAR": ("Software Quality Assurance Records", "SOI-4", "11.19", "11.19"),
}

# Document types that may legitimately be presented at more than one SOI
ALSO_AT = {"SVR": ("SOI-4",), "PR": ("SOI-2", "SOI-4"), "TRACE": ("SOI-3", "SOI-4"), "SVCP": ("SOI-4",)}


def doc_types_for(soi: str, standard: str = "DO-178C") -> list[str]:
    out = [k for k, v in DOCUMENT_TYPES.items() if v[1] == soi or soi in ALSO_AT.get(k, ())]
    if standard == "DO-178B":
        out = [k for k in out if DOCUMENT_TYPES[k][3] != "-" or k == "IVVP"]
    return out


def doc_full_name(code: str) -> str:
    return DOCUMENT_TYPES.get(code, (code,))[0]


VERDICTS = {
    "C": "Compliant",
    "PC": "Partially Compliant",
    "NC": "Non-Compliant",
    "NA": "Not Applicable",
    "NR": "Not Verified",
    "PCL": "Pending Clarification",
    "PMR": "Pending Manual Review",
}
EVIDENCE_STATES = ("Present", "Present-Incomplete", "Present-Inconsistent", "Not Present", "Cannot Verify",
                   "Not Applicable")
SEVERITIES = ("Major", "Minor", "Observation")
FINDING_STATUSES = ("Open", "Closed", "Closed with comment", "Not Closed", "Pending Clarification",
                    "Not Applicable", "Withdrawn")
SESSION_STATUSES = ("Draft", "In Progress", "Pending Manual Review", "Completed", "Cancelled")

SHEETS = {
    "A": "Document Control",
    "B": "Template Compliance",
    "C": "DO-178 Objectives",
    "D": "Traceability",
    "E": "Auditability",
    "F": "Content Depth",
}

RECOMMENDATIONS = {
    "ACCEPTABLE": "The {doc} is acceptable as submitted. No observations remain open.",
    "ACCEPTABLE WITH COMMENTS": "The {doc} is acceptable subject to incorporation of the Minor observations and "
                                "Observations in the next issue. No Major observation is open.",
    "NOT ACCEPTABLE": "One or more Major observations are open. The {doc} shall be revised and re-submitted for "
                      "review before it is baselined or submitted to the certification authority.",
    "REVIEW INCOMPLETE": "The review could not be completed. Checks remain not verified or pending manual review; "
                         "the reasons are stated in Section 4.",
}
