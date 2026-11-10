# DO-178B knowledge base

The DO-178B objective table (Annex A, 66 objectives) is **not encoded yet**,
because no copy of RTCA DO-178B was available when this tool was built. The
tool does not guess objective applicability.

Until a copy is added:
- DO-178B checklists are derived from the DO-178C checklists. Items for content
  that is new in DO-178C are removed: supplements DO-330/331/332/333, Parameter
  Data Item (6.6, 11.22) and Trace Data as a separate data item (11.21).
- DAL filtering uses each checklist item's own "Level Applicability" value.
- Every DO-178B checklist is marked `"validated": false` in its JSON header. The
  Checklist Manager shows this status.

**To complete:** add `annex_a.json` here in the same format as
`../do178c/annex_a.json`. Then have the IV&V Lead re-check the section
references in `checklists/DO-178B/`.
