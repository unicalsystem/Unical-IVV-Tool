"""Authored checklist content for data items not covered by the imported Unical plan checklists.

Basis: RTCA DO-178C Section 11 data-item content (11.6-11.22), Annex A objectives,
and Unical IV&V practice. Each tuple: (section/clause, question, expected evidence,
reference, DAL applicability, review guidance).
Applicability: 'All' unless a level list is given; 'If ...' marks Conditional items.
"""

# ---------------------------------------------------------------- generic sheets
GENERIC_A = [
    ("Cover", "The cover page carries the data-item title, the system / LRU name, the software item name and the platform.",
     "Cover page with full title and identification of the system, LRU and software.", "Unical IV&V practice / CEMILAC template front matter", "All",
     "Check that the title states the data item (e.g. 'Software Design Description') and the product it covers.", "cover_title"),
    ("Ident.", "A unique document number is shown on the cover and in every page header or footer.",
     "Document number on the cover and repeated on each page.", "DO-178C 7.2.1 (configuration identification)", "All",
     "The number must match the number quoted in the SCI and in companion documents.", "doc_number"),
    ("Ident.", "Issue / revision and issue date are stated and agree between the cover, the header and the revision history.",
     "Issue or version identifier and date on the cover and in the revision history.", "DO-178C 7.2.1, 7.2.2", "All",
     "Look for conflicting versions (e.g. 'Rev 01' in the header but 'v1.0' on the cover).", "version_date"),
    ("Ident.", "The software level (DAL) of the software item is declared.",
     "Explicit statement of the software level in the identification block or introduction.", "DO-178C 2.3 / 11.1", "All",
     "The DAL must agree with the PSAC.", "states_dal"),
    ("Approval", "The signatory block identifies the author, reviewer and approver with name, designation and date.",
     "Prepared / reviewed / approved block with names and roles.", "DO-178C 7.2.2 / 8.2", "All",
     "IV&V must not be shown as approver of the applicant's document unless the plans give IV&V that authority.", "signatories"),
    ("History", "A revision history records every issue with date, change description and affected sections.",
     "Revision / amendment history table.", "DO-178C 7.2.3 / 7.2.4", "All", "", "revision_history"),
    ("Contents", "A table of contents is provided and matches the section headings and page numbers.",
     "Table of contents.", "Unical IV&V practice", "All", "", "toc"),
    ("Acronyms", "All acronyms and abbreviations used are defined.",
     "Acronyms / abbreviations list.", "Unical IV&V practice", "All", "", "abbreviations"),
    ("References", "Applicable and reference documents are listed with document number, title and issue.",
     "Reference documents table including plans, standards and system data.", "DO-178C 11 (life cycle data relationships)", "All",
     "Every document cited in the text should appear in the list and vice-versa.", "references"),
    ("Pages", "Every page carries page numbering in the form 'Page x of y' (or equivalent) and the document identification.",
     "Consistent header / footer with page numbering.", "Unical IV&V practice / CEMILAC template", "All", "", "page_numbering"),
    ("Placeholders", "No unresolved placeholders remain (TBD, TBC, 'XX', 'Error! Reference source not found', empty fields).",
     "Document free of placeholders, or each TBD tracked with an owner and closure date.", "DO-178C 6.3 (accuracy and consistency)", "All",
     "Open TBDs are acceptable only where the plans allow them and they are tracked.", "no_placeholders"),
]

GENERIC_E = [
    ("General", "The document uses committal language ('shall', 'will') for required activities rather than 'may' or 'should'.",
     "Committal statements for every required activity.", "IV&V good practice", "All",
     "Non-committal wording in plans and standards cannot be audited.", "committal_language"),
    ("General", "Every activity identifies who performs it, what record is produced and when it is performed.",
     "Role, record and timing stated for each activity.", "DO-178C 11.19 / 8.2", "All", "", None),
    ("General", "The text describes the project's own practice and is not copied verbatim from DO-178C.",
     "Project-specific description of methods.", "IV&V good practice", "All",
     "Verbatim copying of DO-178C text is a common reason for authority findings.", None),
    ("General", "Terminology is consistent throughout and with the companion documents.",
     "Same names for items, roles and processes throughout.", "DO-178C 6.3 (consistency)", "All", "", "acronyms_defined"),
    ("General", "Figures and tables are numbered, titled and referenced in the text.",
     "Numbered and captioned figures and tables.", "IV&V good practice", "All", "", "figures_tables"),
]

# ---------------------------------------------------------------- per data item
CONTENT = {
# ------------------------------------------------------------------ SOI-1 standards
"SRS": {
 "B": [
  ("11.6.a", "The methods to be used for developing software requirements are defined (e.g. structured methods).", "Description of the requirements development method.", "DO-178C 11.6.a", "A, B, C", ""),
  ("11.6.b", "The notations to be used to express requirements are defined (e.g. text templates, data flow diagrams, formal notation).", "Requirement syntax / notation rules.", "DO-178C 11.6.b", "A, B, C", ""),
  ("11.6.c", "Constraints on the use of the requirements development tools are defined.", "Tool usage constraints (e.g. DOORS attributes, templates).", "DO-178C 11.6.c", "A, B, C", ""),
  ("11.6.d", "The method used to provide derived requirements to the system processes, including the system safety assessment, is defined.", "Derived-requirement identification and feedback process.", "DO-178C 11.6.d / 5.1.1.b", "A, B, C", ""),
 ],
 "F": [
  ("Quality", "Rules ensure each requirement is atomic, unambiguous, verifiable and uniquely identified.", "Requirement quality attributes and ID scheme.", "DO-178C 6.3.1.b, 6.3.1.d", "A, B, C", ""),
  ("Attributes", "Mandatory requirement attributes are defined (ID, text, rationale, derived flag, verification method, trace links, safety flag).", "Attribute list.", "DO-178C 5.1.2 / 11.21", "A, B, C", ""),
  ("Interfaces", "Rules for specifying hardware/software interfaces (protocols, formats, rates, ranges, units) are defined.", "Interface requirement rules.", "DO-178C 11.9.f", "A, B, C", ""),
  ("Robustness", "Rules require abnormal-range, failure-detection and safety-monitoring behaviour to be specified.", "Robustness requirement rules.", "DO-178C 11.9.g / 6.4.2.2", "A, B, C", ""),
  ("Timing", "Rules require timing, performance and memory constraints to be expressed with values and tolerances.", "Rules for quantitative requirements.", "DO-178C 11.9.c-e", "A, B, C", ""),
  ("Partitioning", "Rules for specifying partitioning requirements and the software level of each partition are given.", "Partitioning requirement rules.", "DO-178C 11.9.h", "If partitioning used", ""),
  ("PDI", "Rules for describing how parameter data items are used and their structure / attributes are given.", "PDI requirement rules.", "DO-178C 5.1.2.j", "If PDI used", ""),
  ("Review", "Criteria are defined against which requirements are reviewed for conformance to this standard.", "Review criteria or checklist reference.", "DO-178C 6.3.1.e", "A, B, C", ""),
 ]},
"SDS": {
 "B": [
  ("11.7.a", "Design description method(s) to be used are defined.", "Design method (e.g. structured, object-oriented, model-based).", "DO-178C 11.7.a", "A, B, C", ""),
  ("11.7.b", "Naming conventions to be used are defined.", "Naming rules for components, data and interfaces.", "DO-178C 11.7.b", "A, B, C", ""),
  ("11.7.c", "Conditions imposed on permitted design methods are defined (scheduling, interrupts, event-driven architecture, dynamic tasking, re-entry, global data, exception handling) with rationale.", "Permitted design constructs with rationale.", "DO-178C 11.7.c", "A, B, C", ""),
  ("11.7.d", "Constraints on the use of the design tools are defined.", "Design tool constraints.", "DO-178C 11.7.d", "A, B, C", ""),
  ("11.7.e", "Constraints on design are defined (e.g. exclusion of recursion, dynamic objects, data aliases, compacted expressions).", "Design constraints list.", "DO-178C 11.7.e", "A, B, C", ""),
  ("11.7.f", "Complexity restrictions are defined (nesting depth, unconditional branches, entry/exit points).", "Quantified complexity limits.", "DO-178C 11.7.f", "A, B, C", ""),
 ],
 "F": [
  ("LLR", "Rules define how low-level requirements are written so that source code can be produced directly from them without further information.", "LLR writing rules.", "DO-178C 5.2 / Glossary (low-level requirements)", "A, B, C", ""),
  ("Derived", "Rules define how derived low-level requirements are identified and justified.", "Derived LLR identification rule.", "DO-178C 5.2.1.b", "A, B, C", ""),
  ("Resources", "Rules require resource budgets and margins (timing, memory, stack) to be stated in the design.", "Resource budget rules.", "DO-178C 11.10.e", "A, B, C", ""),
  ("Deactivated", "Rules require deactivated code and its means of deactivation to be described.", "Deactivated code design rule.", "DO-178C 11.10.k / 5.2.4", "If deactivated code", ""),
  ("Partitioning", "Rules for partitioning methods and protection against partition breaches are defined.", "Partitioning design rules.", "DO-178C 11.10.h", "If partitioning used", ""),
  ("Review", "Criteria are defined against which the design is reviewed for conformance to this standard.", "Review criteria.", "DO-178C 6.3.2.e, 6.3.3.e", "A, B, C", ""),
 ]},
"SCS": {
 "B": [
  ("11.8.a", "The programming language(s) and any subset are defined, with reference to data that unambiguously defines syntax, control behaviour, data behaviour and side effects.", "Language standard (e.g. ISO C99) and subset (e.g. MISRA C:2012) reference.", "DO-178C 11.8.a", "A, B, C", ""),
  ("11.8.b", "Source code presentation and documentation standards are defined (line length, indentation, header content, revision history, inputs/outputs, global data).", "Presentation and header rules.", "DO-178C 11.8.b", "A, B, C", ""),
  ("11.8.c", "Naming conventions for components, subprograms, variables and constants are defined.", "Naming rules.", "DO-178C 11.8.c", "A, B, C", ""),
  ("11.8.d", "Conditions and constraints on permitted coding conventions are defined (coupling, complexity of logical/numerical expressions) with rationale.", "Coding constraints with rationale.", "DO-178C 11.8.d", "A, B, C", ""),
  ("11.8.e", "Constraints on the use of the coding tools (compiler options, code generators) are defined.", "Compiler / tool constraints.", "DO-178C 11.8.e", "A, B, C", ""),
 ],
 "F": [
  ("Deviation", "A deviation process for coding-rule violations (record, justification, approval) is defined.", "Deviation procedure.", "DO-178C 6.3.4.d", "A, B, C", ""),
  ("Static", "The static-analysis tool and the rule set used to check conformance are identified, with version.", "Static analysis tool and configuration.", "DO-178C 6.3.4.d / 12.2", "A, B, C", ""),
  ("Verifiability", "Rules support verifiability and structural coverage (e.g. no unreachable code, single exit, limited conditions per decision for MC/DC).", "Coverage-friendly coding rules.", "DO-178C 6.3.4.c / 6.4.4.2", "A, B", ""),
  ("Numerics", "Rules address numerical accuracy (floating-point use, overflow, division by zero, type conversion).", "Numeric safety rules.", "DO-178C 6.3.4.f", "A, B, C", ""),
  ("Compiler", "Rules address compiler-specific behaviour and optimisation constraints affecting object-code traceability.", "Compiler behaviour rules.", "DO-178C 6.4.4.2.b", "A", ""),
 ]},
"IVVP": {
 "B": [
  ("Scope", "The IVVP identifies the software items, software level, certification basis and the life cycle data subject to IV&V.", "Scope statement with item, DAL and data list.", "DO-178C 6.2 / PSAC", "All", ""),
  ("Org", "The IV&V organisation is described and its technical, managerial and financial independence from the development team is demonstrated.", "Organisation chart and independence statement.", "DO-178C 6.2.e / Glossary (independence)", "A, B", ""),
  ("Objectives", "The Annex A objectives allocated to IV&V are listed, including all objectives that require independence at the declared level.", "Objective allocation table.", "DO-178C Annex A", "All", ""),
  ("Activities", "IV&V activities are defined for each SOI stage (reviews, analyses, independent tests, coverage assessment, audits).", "Activity description per SOI.", "DO-178C 6.3-6.4", "All", ""),
  ("Methods", "Review checklists, verdict codes, finding categories and closure rules are defined.", "Method and checklist description.", "Unical IV&V practice", "All", ""),
  ("Entry/Exit", "Entry and exit criteria for each IV&V activity are defined.", "Transition criteria.", "DO-178C 6.2 / 4.3.b", "All", ""),
  ("Deliverables", "IV&V deliverables (review reports, checklists, finding registers, closure report) are listed with schedule.", "Deliverables list.", "Unical IV&V practice", "All", ""),
  ("Reporting", "Reporting lines to the applicant and to the certification authority are defined.", "Reporting and escalation paths.", "DO-178C 9", "All", ""),
  ("Tools", "Tools used by IV&V are listed with version and qualification status where credit is taken.", "IV&V tool list.", "DO-178C 12.2 / DO-330", "All", ""),
 ],
 "F": [
  ("Plans", "The IVVP is consistent with the PSAC and SVP allocation of verification activities and independence.", "Consistency statement / cross-reference.", "DO-178C 4.1.g", "All", ""),
  ("CM", "IV&V records are placed under configuration management (control category stated).", "CM of IV&V records.", "DO-178C 7.3", "All", ""),
  ("PR", "The way IV&V raises and tracks problem reports through the applicant's PR process is defined.", "PR interface.", "DO-178C 7.2.3", "All", ""),
  ("Competence", "Competence and training requirements for IV&V personnel are defined.", "Competence criteria.", "IV&V good practice", "All", ""),
  ("Schedule", "The IV&V schedule is aligned with the SOI dates in the PSAC.", "Schedule with SOI milestones.", "DO-178C 9.2", "All", ""),
 ]},
# ------------------------------------------------------------------ SOI-2
"SRD": {
 "B": [
  ("11.9.a", "The allocation of system requirements to software is described, with attention to safety-related requirements and potential failure conditions.", "Allocation description and safety-related requirement identification.", "DO-178C 11.9.a", "All", ""),
  ("11.9.b", "Functional and operational requirements are specified under each mode of operation.", "Requirements per operating mode.", "DO-178C 11.9.b", "All", ""),
  ("11.9.c", "Performance criteria (e.g. precision and accuracy) are specified.", "Quantified performance requirements.", "DO-178C 11.9.c", "All", ""),
  ("11.9.d", "Timing requirements and constraints are specified.", "Timing requirements with values.", "DO-178C 11.9.d", "All", ""),
  ("11.9.e", "Memory size constraints are specified.", "Memory constraints.", "DO-178C 11.9.e", "All", ""),
  ("11.9.f", "Hardware and software interfaces are specified (protocols, formats, frequency of inputs and outputs).", "Interface requirements.", "DO-178C 11.9.f", "All", ""),
  ("11.9.g", "Failure detection and safety monitoring requirements are specified.", "Failure detection / monitoring requirements.", "DO-178C 11.9.g", "All", ""),
  ("11.9.h", "Partitioning requirements allocated to software, interactions between partitions and the software level of each partition are specified.", "Partitioning requirements.", "DO-178C 11.9.h", "If partitioning used", ""),
  ("Derived", "Derived high-level requirements are identified, justified and provided to the system safety assessment process.", "Derived flag, rationale and evidence of feedback to safety.", "DO-178C 5.1.1.b / Table A-2 obj 2", "All", ""),
 ],
 "F": [
  ("Quality", "Each requirement is uniquely identified, atomic, unambiguous and verifiable.", "Unique IDs; one 'shall' per requirement; measurable criteria.", "DO-178C 6.3.1.b, 6.3.1.d", "A, B, C", ""),
  ("Target", "Requirements are compatible with the target computer (resources, timing, numeric precision).", "Target constraints considered.", "DO-178C 6.3.1.c", "A, B", ""),
  ("Algorithms", "Algorithms are specified with sufficient precision to verify accuracy (equations, ranges, units, tolerances).", "Algorithm definitions.", "DO-178C 6.3.1.g", "A, B, C", ""),
  ("Robustness", "Abnormal inputs, out-of-range values, invalid states and failure modes have defined behaviour.", "Robustness requirements.", "DO-178C 6.4.2.2", "All", ""),
  ("Modes", "All operating modes and transitions (power-up, initialisation, normal, degraded, maintenance/factory, fault) are covered.", "Mode/state requirements.", "DO-178C 11.9.b", "All", ""),
  ("PDI", "If parameter data items are used, the requirements describe how they are used and their structure and attributes.", "PDI usage requirements.", "DO-178C 5.1.2.j", "If PDI used", ""),
  ("Deactivated", "Requirements for functions intended to be deactivated in a configuration are identified.", "Deactivation requirements.", "DO-178C 5.2.4", "If deactivated code", ""),
  ("Standards", "Requirements conform to the Software Requirements Standards.", "Evidence of conformance review.", "DO-178C 6.3.1.e", "A, B, C", ""),
 ]},
"SDD": {
 "B": [
  ("11.10.a", "The design describes how the software satisfies the high-level requirements, including algorithms, data structures and allocation of requirements to processors and tasks.", "Requirement-to-design allocation.", "DO-178C 11.10.a", "All", ""),
  ("11.10.b", "The software architecture defining the software structure is described.", "Architecture description.", "DO-178C 11.10.b", "All", ""),
  ("11.10.c", "The input/output description (e.g. data dictionary) is provided internally and externally throughout the architecture.", "Data dictionary / I/O description.", "DO-178C 11.10.c", "A, B, C", ""),
  ("11.10.d", "The data flow and control flow of the design are described.", "Data-flow and control-flow description.", "DO-178C 11.10.d", "A, B, C", ""),
  ("11.10.e", "Resource limitations, the strategy for managing each resource, margins and the method of measuring margins (timing, memory) are described.", "Resource budgets and margins.", "DO-178C 11.10.e", "A, B, C", ""),
  ("11.10.f", "Scheduling procedures and inter-processor / inter-task communication mechanisms, including interrupts, are described.", "Scheduling and communication design.", "DO-178C 11.10.f", "A, B, C", ""),
  ("11.10.g", "Design methods and implementation details are described (e.g. software loading, user-modifiable software, multiple-version dissimilar software).", "Design methods.", "DO-178C 11.10.g", "A, B, C", ""),
  ("11.10.h", "Partitioning methods and means of preventing partition breaches are described.", "Partitioning design.", "DO-178C 11.10.h", "If partitioning used", ""),
  ("11.10.i", "Software components are described, stating whether new or previously developed, with reference to the baseline of previously developed components.", "Component list with origin.", "DO-178C 11.10.i", "All", ""),
  ("11.10.j", "Derived requirements resulting from the design process are identified.", "Derived LLR identification.", "DO-178C 11.10.j / 5.2.1.b", "A, B, C", ""),
  ("11.10.k", "If deactivated code exists, the means to ensure it cannot be enabled in the target computer are described.", "Deactivation mechanism.", "DO-178C 11.10.k", "If deactivated code", ""),
  ("11.10.l", "Rationale is given for design decisions traceable to safety-related system requirements.", "Safety-related design rationale.", "DO-178C 11.10.l", "All", ""),
 ],
 "F": [
  ("LLR", "Low-level requirements are detailed enough that source code can be implemented directly without further information.", "LLR granularity.", "DO-178C Glossary / 5.2", "A, B, C", ""),
  ("Consistency", "The architecture is consistent (no conflicting data/control flow, correct relationships between components).", "Architecture consistency evidence.", "DO-178C 6.3.3.b", "A, B, C", ""),
  ("Target", "The design is compatible with the target computer (initialisation, interrupts, timing, memory map).", "Target compatibility.", "DO-178C 6.3.2.c / 6.3.3.c", "A, B", ""),
  ("Verifiable", "The architecture and LLRs are verifiable (no unbounded recursion, testable interfaces).", "Verifiability considerations.", "DO-178C 6.3.2.d / 6.3.3.d", "A, B", ""),
  ("Standards", "The design conforms to the Software Design Standards.", "Conformance evidence.", "DO-178C 6.3.2.e / 6.3.3.e", "A, B, C", ""),
  ("Coupling", "Data coupling and control coupling between components are identified so that they can later be verified.", "Coupling identification.", "DO-178C 6.4.4.d", "A, B, C", ""),
  ("Startup", "Power-up, initialisation, built-in test and failure handling design is described.", "Start-up and BIT design.", "DO-178C 11.10.a / 11.9.g", "All", ""),
 ]},
"CODE": {
 "B": [
  ("11.11", "Each source code component carries software identification including name and date of revision and/or version.", "Component headers with ID and version.", "DO-178C 11.11", "A, B, C", ""),
  ("6.3.4.a", "Source code complies with the low-level requirements (review records show this for each component).", "Code review records against LLR.", "DO-178C 6.3.4.a / Table A-5 obj 1", "A, B, C", ""),
  ("6.3.4.b", "Source code complies with the software architecture (data and control flow match the design).", "Review records against architecture.", "DO-178C 6.3.4.b / Table A-5 obj 2", "A, B, C", ""),
  ("6.3.4.c", "Source code is verifiable (no statements that cannot be verified, e.g. unreachable code).", "Verifiability review.", "DO-178C 6.3.4.c / Table A-5 obj 3", "A, B", ""),
  ("6.3.4.d", "Source code conforms to the Software Code Standards; deviations are recorded and justified.", "Coding-standard / static analysis results and deviations.", "DO-178C 6.3.4.d / Table A-5 obj 4", "A, B, C", ""),
  ("6.3.4.e", "Source code is traceable to the low-level requirements; no undocumented functionality.", "Code-to-LLR trace.", "DO-178C 6.3.4.e / Table A-5 obj 5", "A, B, C", ""),
  ("6.3.4.f", "Source code is accurate and consistent (stack usage, memory, fixed-point arithmetic overflow, floating-point, resource contention, worst-case execution timing, exception handling, use of uninitialised variables, data corruption due to task or interrupt conflicts).", "Analysis results for each accuracy/consistency topic.", "DO-178C 6.3.4.f / Table A-5 obj 6", "A, B, C", ""),
 ],
 "F": [
  ("Build", "The compiler, linker and options used are identified and match the SECI / build instructions.", "Build configuration.", "DO-178C 11.16.g / 11.15.b", "A, B, C", ""),
  ("Integration", "Output of the integration process (link maps, memory map, load data) has been reviewed for completeness and correctness.", "Integration review records.", "DO-178C 6.3.5 / Table A-5 obj 7", "A, B, C", ""),
  ("Dead code", "Dead code is removed and deactivated code is identified with its deactivation means.", "Dead/deactivated code analysis.", "DO-178C 6.4.4.3", "A, B, C", ""),
  ("Independence", "Reviews for objectives requiring independence at the declared level were performed by a person other than the author.", "Reviewer identity versus author.", "DO-178C Annex A (independence)", "A, B", ""),
  ("PR", "Code review findings are raised as problem reports or tracked to closure.", "Finding tracking.", "DO-178C 7.2.3", "All", ""),
 ]},
"TRACE": {
 "B": [
  ("11.21.a", "Bi-directional trace exists between system requirements allocated to software and high-level requirements.", "System-HLR trace matrix.", "DO-178C 11.21.a", "All", ""),
  ("11.21.b", "Bi-directional trace exists between high-level requirements and low-level requirements.", "HLR-LLR trace matrix.", "DO-178C 11.21.b", "A, B, C", ""),
  ("11.21.c", "Bi-directional trace exists between low-level requirements and source code.", "LLR-code trace.", "DO-178C 11.21.c", "A, B, C", ""),
  ("11.21.d", "Bi-directional trace exists between software requirements and test cases.", "Requirement-test case trace.", "DO-178C 11.21.d", "All", ""),
  ("11.21.e", "Bi-directional trace exists between test cases and test procedures.", "Test case-procedure trace.", "DO-178C 11.21.e", "All", ""),
  ("11.21.f", "Bi-directional trace exists between test procedures and test results.", "Procedure-result trace.", "DO-178C 11.21.f", "All", ""),
 ],
 "F": [
  ("Orphans", "No orphan requirements, code or tests exist; every untraced item is justified (derived requirement or deactivated code).", "Orphan analysis.", "DO-178C 6.3.1.f, 6.3.2.f, 6.3.4.e", "All", ""),
  ("Derived", "Derived requirements are flagged in the trace and linked to their safety assessment feedback.", "Derived flags in trace.", "DO-178C 5.1.1.b, 5.2.1.b", "All", ""),
  ("Baseline", "Trace data identifies the baseline / version of each traced data item.", "Versioned trace.", "DO-178C 7.2.2", "All", ""),
  ("Coverage", "Requirements-based test coverage of HLR and LLR can be demonstrated from the trace.", "Coverage summary from trace.", "DO-178C 6.4.4.1", "All", ""),
 ]},
# ------------------------------------------------------------------ SOI-3
"SVCP": {
 "B": [
  ("11.13.a", "Review and analysis procedures describe scope and depth and the methods to be used, in addition to the SVP.", "Review/analysis procedures.", "DO-178C 11.13.a", "All", ""),
  ("11.13.b", "Each test case states its purpose, set of inputs, conditions, expected results to achieve the required coverage criteria, and pass/fail criteria.", "Test case definitions.", "DO-178C 11.13.b", "All", ""),
  ("11.13.c", "Test procedures give step-by-step set-up and execution instructions, how results are evaluated, and the test environment to be used.", "Test procedures.", "DO-178C 11.13.c", "All", ""),
 ],
 "F": [
  ("Normal", "Normal-range test cases exercise each requirement with valid equivalence classes, boundary values, time-related functions and state transitions.", "Normal range test design.", "DO-178C 6.4.2.1", "All", ""),
  ("Robust", "Robustness test cases exercise abnormal inputs, invalid transitions, out-of-range loop counts, arithmetic overflow and failure modes.", "Robustness test design.", "DO-178C 6.4.2.2", "All", ""),
  ("HW/SW", "Hardware/software integration tests run on the target computer and cover interfaces, timing, interrupts and resource usage.", "HSIT cases on target.", "DO-178C 6.4.3.a / Table A-6 obj 5", "All", ""),
  ("SW int", "Software integration tests verify interrelationships between requirements and components.", "Software integration test cases.", "DO-178C 6.4.3.b", "A, B, C", ""),
  ("LLR", "Low-level testing covers every low-level requirement.", "LLR test cases.", "DO-178C 6.4.3.c / Table A-6 obj 3", "A, B, C", ""),
  ("Env", "The test environment (target, emulator, simulator, test tools) is identified and any differences from the target are analysed.", "Test environment description and differences analysis.", "DO-178C 6.4.1", "All", ""),
  ("PDI", "Test cases verify the parameter data item file content and its interaction with the executable code.", "PDI test cases.", "DO-178C 6.6 / Table A-5 obj 8-9", "If PDI used", ""),
  ("Review", "The test procedures have been reviewed for correctness against the test cases.", "Review records.", "DO-178C 6.4.5.b / Table A-7 obj 1", "A, B, C", ""),
 ]},
"SVR": {
 "B": [
  ("11.14.a", "For each review, analysis and test, each procedure that passed or failed and the final pass/fail result are indicated.", "Pass/fail result per procedure.", "DO-178C 11.14.a", "All", ""),
  ("11.14.b", "The configuration item or software version reviewed, analysed or tested is identified.", "Version identification of the item verified.", "DO-178C 11.14.b", "All", ""),
  ("11.14.c", "Results of tests, reviews and analyses, including coverage analyses and traceability analyses, are included.", "Results of every verification activity.", "DO-178C 11.14.c", "All", ""),
  ("11.14", "Discrepancies found are recorded and tracked through problem reporting.", "PR references for each discrepancy.", "DO-178C 11.14 / 7.2.3", "All", ""),
 ],
 "F": [
  ("Results", "Test results are correct and discrepancies between actual and expected results are explained.", "Results review records.", "DO-178C 6.4.5.c / Table A-7 obj 2", "A, B, C", ""),
  ("HLR cov", "Requirements-based test coverage of high-level requirements is achieved (every HLR has normal and robustness tests).", "HLR coverage analysis.", "DO-178C 6.4.4.1 / Table A-7 obj 3", "All", ""),
  ("LLR cov", "Requirements-based test coverage of low-level requirements is achieved.", "LLR coverage analysis.", "DO-178C 6.4.4.1 / Table A-7 obj 4", "A, B, C", ""),
  ("MC/DC", "Structural coverage analysis shows modified condition/decision coverage is achieved; gaps are resolved.", "MC/DC coverage report and gap resolution.", "DO-178C 6.4.4.2 / Table A-7 obj 5", "A", ""),
  ("Decision", "Structural coverage analysis shows decision coverage is achieved.", "Decision coverage report.", "DO-178C 6.4.4.2 / Table A-7 obj 6", "A, B", ""),
  ("Statement", "Structural coverage analysis shows statement coverage is achieved.", "Statement coverage report.", "DO-178C 6.4.4.2 / Table A-7 obj 7", "A, B, C", ""),
  ("DC/CC", "Data coupling and control coupling coverage is confirmed by requirements-based tests.", "DC/CC analysis.", "DO-178C 6.4.4.2.c / Table A-7 obj 8", "A, B, C", ""),
  ("Object", "Additional code generated by the compiler that cannot be traced to source code is verified.", "Source-to-object analysis.", "DO-178C 6.4.4.2.b / Table A-7 obj 9", "A", ""),
  ("Gaps", "Structural coverage gaps are resolved and classified (missing tests, requirement deficiency, dead code, deactivated code).", "Gap resolution records.", "DO-178C 6.4.4.3", "A, B, C", ""),
  ("Reviews", "Review and analysis results for HLR, LLR, architecture, source code and integration outputs are included with independence evidence.", "Review records with reviewer identities.", "DO-178C 6.3 / Tables A-3 to A-5", "All", ""),
  ("Tools", "Where verification tool output is used for credit without further review, tool qualification data is referenced.", "Tool qualification references.", "DO-178C 12.2 / DO-330", "If qualified tools", ""),
 ]},
"PR": {
 "B": [
  ("11.17.a", "Each problem report identifies the configuration item and/or life cycle process activity in which the problem was observed.", "Item / activity identification.", "DO-178C 11.17.a", "All", ""),
  ("11.17.b", "Each problem report identifies the configuration item(s) to be modified or the process to be changed.", "Affected items.", "DO-178C 11.17.b", "All", ""),
  ("11.17.c", "The problem description enables understanding and resolution and allows assessment of potential safety or functional effects.", "Problem description with safety assessment.", "DO-178C 11.17.c", "All", ""),
  ("11.17.d", "The corrective action taken to resolve the problem is described.", "Corrective action.", "DO-178C 11.17.d", "All", ""),
 ],
 "F": [
  ("Status", "Each PR has a status, owner and closure evidence; closure is verified (re-review / regression).", "Status and closure verification.", "DO-178C 7.2.3 / 7.2.5", "All", ""),
  ("Classification", "Each PR is classified by safety / functional effect according to the SCMP scheme.", "Classification.", "DO-178C 7.2.3", "All", ""),
  ("Open", "Open PRs at the time of review are listed with justification and mitigation for any planned to remain open at certification.", "Open PR list with justification.", "DO-178C 11.20.k", "All", ""),
  ("CCB", "Change review / CCB decisions are recorded against each PR.", "CCB records.", "DO-178C 7.2.5", "All", ""),
 ]},
# ------------------------------------------------------------------ SOI-4
"SCI": {
 "B": [
  ("11.16.a", "The software product is identified.", "Product identification.", "DO-178C 11.16.a", "All", ""),
  ("11.16.b", "The Executable Object Code and Parameter Data Item Files, if any, are identified.", "EOC / PDI identification with part numbers and checksums.", "DO-178C 11.16.b", "All", ""),
  ("11.16.c", "Each source code component is identified with its version.", "Source component list.", "DO-178C 11.16.c", "All", ""),
  ("11.16.d", "Previously developed software in the product is identified, if used.", "PDS identification.", "DO-178C 11.16.d", "If PDS used", ""),
  ("11.16.e", "Software life cycle data is identified with versions.", "Life cycle data list.", "DO-178C 11.16.e", "All", ""),
  ("11.16.f", "Archive and release media are identified.", "Media identification.", "DO-178C 11.16.f", "All", ""),
  ("11.16.g", "Instructions for building the EOC and PDI files, including compile/link instructions and recovery procedures, are given.", "Build instructions.", "DO-178C 11.16.g", "All", ""),
  ("11.16.h", "Reference to the SECI is given, if packaged separately.", "SECI reference.", "DO-178C 11.16.h", "All", ""),
  ("11.16.i", "Data integrity checks for the EOC are identified, if used.", "Checksums / CRCs.", "DO-178C 11.16.i", "If used", ""),
  ("11.16.j", "Procedures, methods and tools for modifying user-modifiable software are identified, if any.", "UMS procedures.", "DO-178C 11.16.j", "If UMS used", ""),
  ("11.16.k", "Procedures and methods for loading the software into the target hardware are identified.", "Loading procedures.", "DO-178C 11.16.k", "All", ""),
 ],
 "F": [
  ("Consistency", "Versions in the SCI agree with those in the SAS, SVR and the released media.", "Cross-check results.", "DO-178C 7.2.2 / 11.20.e", "All", ""),
  ("Rebuild", "The build has been reproduced from the SCI instructions and gives an identical executable (checksum match).", "Rebuild record.", "DO-178C 7.2.7", "A, B, C", ""),
 ]},
"SECI": {
 "B": [
  ("11.15.a", "The life cycle environment hardware and its operating system software are identified.", "Host hardware / OS identification.", "DO-178C 11.15.a", "All", ""),
  ("11.15.b", "Tools used during development are identified (compilers, linkers, loaders, data-integrity tools, autocode generators with options).", "Development tools with versions and options.", "DO-178C 11.15.b", "All", ""),
  ("11.15.c", "The test environment used to verify the software is identified (test and analysis tools).", "Verification tools with versions.", "DO-178C 11.15.c", "All", ""),
  ("11.15.d", "Qualified tools and their tool qualification data are identified.", "Qualified tools and TQL data.", "DO-178C 11.15.d / 12.2", "If qualified tools", ""),
 ],
 "F": [
  ("Control", "The environment items are under configuration control and their versions match those declared in the plans.", "CM of environment.", "DO-178C 7.5 / Table A-8 obj 6", "All", ""),
 ]},
"SAS": {
 "B": [
  ("11.20.a", "System overview: functions, allocation to hardware and software, architecture, processor(s), hardware/software interfaces, safety features, and differences from the PSAC.", "System overview section.", "DO-178C 11.20.a", "All", ""),
  ("11.20.b", "Software overview with emphasis on safety and partitioning concepts and differences from the PSAC.", "Software overview section.", "DO-178C 11.20.b", "All", ""),
  ("11.20.c", "Certification considerations restated from the PSAC with any differences.", "Certification considerations.", "DO-178C 11.20.c", "All", ""),
  ("11.20.d", "Summary of the actual software life cycle and differences from the PSAC.", "Life cycle summary.", "DO-178C 11.20.d", "All", ""),
  ("11.20.e", "Life cycle data differences, relationships, and explicit reference to the SCI and SECI by identifier and version.", "Life cycle data section with SCI/SECI references.", "DO-178C 11.20.e", "All", ""),
  ("11.20.f", "Additional considerations (issue papers, special conditions) summarised with differences from the PSAC.", "Additional considerations.", "DO-178C 11.20.f", "All", ""),
  ("11.20.g", "Supplier oversight: how supplier processes and outputs comply with plans and standards.", "Supplier oversight section.", "DO-178C 11.20.g", "If suppliers", ""),
  ("11.20.h", "Software identification by part number and version.", "Part number and version.", "DO-178C 11.20.h", "All", ""),
  ("11.20.i", "Software characteristics: EOC size, timing margins including WCET, memory margins, resource limitations and the means of measuring each.", "Characteristics with measured margins.", "DO-178C 11.20.i", "All", ""),
  ("11.20.j", "Change history with attention to safety-related changes and process changes since previous certification.", "Change history.", "DO-178C 11.20.j", "If applicable", ""),
  ("11.20.k", "Software status: unresolved problem reports with description, effects, restrictions, safety effect, justification and mitigation.", "Open PR summary.", "DO-178C 11.20.k", "All", ""),
  ("11.20.l", "Compliance statement with summary of methods used, authority rulings and any deviations.", "Compliance statement.", "DO-178C 11.20.l", "All", ""),
 ],
 "F": [
  ("Objectives", "The SAS demonstrates that all Annex A objectives applicable to the declared level are satisfied, with independence where required.", "Objective compliance matrix.", "DO-178C Annex A / 9.c", "All", ""),
  ("Consistency", "Statements in the SAS agree with the SCI, SVR, SQA records and PR status.", "Cross-check with records.", "DO-178C 9.2", "All", ""),
 ]},
"SCMR": {
 "B": [
  ("11.18", "SCM records cover configuration identification lists, baseline / library records, change history, archive records and release records.", "SCM record set.", "DO-178C 11.18", "All", ""),
 ],
 "F": [
  ("Baselines", "Baselines are established and traceable for each SOI.", "Baseline records.", "DO-178C 7.2.2 / Table A-8 obj 2", "All", ""),
  ("Status", "Configuration status accounting shows the status of every configuration item and PR.", "Status accounting report.", "DO-178C 7.2.6", "All", ""),
  ("Archive", "Archive, retrieval and release records show integrity protection and retention.", "Archive records.", "DO-178C 7.2.7 / Table A-8 obj 4", "All", ""),
  ("Load", "Software load control records are maintained.", "Load control records.", "DO-178C 7.4 / Table A-8 obj 5", "All", ""),
 ]},
"SQAR": {
 "B": [
  ("11.19", "SQA records include review and audit reports, meeting minutes, authorised process deviations and conformity review records.", "SQA record set.", "DO-178C 11.19", "All", ""),
 ],
 "F": [
  ("Plans", "Records show assurance that plans and standards were developed and reviewed for compliance and consistency.", "Plan/standard review records.", "DO-178C 8.1.a / Table A-9 obj 1", "A, B, C", ""),
  ("Process", "Records show assurance that life cycle processes complied with approved plans and standards.", "Process audit records.", "DO-178C 8.1.b / Table A-9 obj 2-3", "All", ""),
  ("Transition", "Records show transition criteria were satisfied.", "Transition audit records.", "DO-178C 8.1.c / Table A-9 obj 4", "A, B, C", ""),
  ("Conformity", "The software conformity review was conducted and its record is complete.", "Conformity review record.", "DO-178C 8.1.d / 8.3 / Table A-9 obj 5", "All", ""),
  ("Independence", "SQA records show SQA independence from development.", "Independence evidence.", "DO-178C 8.1 / Annex A", "All", ""),
 ]},
}

# Consistency checks (sheet D) common per document family
D_COMMON = {
    "plans": [
        ("PSAC", "The document is consistent with the PSAC (software level, software items, life cycle, data items, tools).", "Matching identifiers and statements.", "DO-178C 4.1.g", "All", ""),
        ("Plans", "Document numbers and issues of companion plans and standards quoted in this document match the documents actually issued.", "Correct references.", "DO-178C 4.1.g / 7.2.1", "All", ""),
        ("Roles", "Roles, responsibilities and independence stated match the other plans.", "Consistent roles.", "DO-178C 4.1.g", "All", ""),
        ("Tools", "Tools and versions match those declared in the PSAC/SDP/SECI.", "Consistent tool list.", "DO-178C 4.4.1", "All", ""),
    ],
    "dev": [
        ("Plans", "The data item was produced as defined in the SDP and conforms to the referenced standards.", "Reference to SDP and standards.", "DO-178C 5 / Table A-9 obj 2-3", "All", ""),
        ("Upstream", "Every item traces to the upstream data (system requirements -> HLR -> LLR -> code).", "Trace references.", "DO-178C 11.21", "All", ""),
        ("Baseline", "The upstream documents referenced are the baselined versions.", "Versioned references.", "DO-178C 7.2.2", "All", ""),
        ("Safety", "Derived requirements are provided to the system safety assessment process.", "Safety feedback evidence.", "DO-178C 5.1.1.b / 5.2.1.b", "All", ""),
    ],
    "ver": [
        ("SVP", "Verification was performed as defined in the SVP (methods, environment, independence, transition criteria).", "Reference to SVP.", "DO-178C 6.2 / Table A-9 obj 2", "All", ""),
        ("Versions", "Versions of the items verified match the SCI baseline.", "Version cross-check.", "DO-178C 11.14.b", "All", ""),
        ("Trace", "Test cases, procedures and results trace to requirements and to each other.", "Trace data.", "DO-178C 11.21.d-f", "All", ""),
        ("PR", "Discrepancies are linked to problem reports.", "PR references.", "DO-178C 7.2.3", "All", ""),
    ],
    "final": [
        ("PSAC", "Differences from the PSAC are identified and justified.", "Difference statements.", "DO-178C 11.20", "All", ""),
        ("SCI", "Identifiers and versions match the SCI.", "Matching versions.", "DO-178C 11.16", "All", ""),
        ("Records", "Statements are supported by SCM and SQA records.", "Record references.", "DO-178C 11.18-11.19", "All", ""),
    ],
}
FAMILY = {"SRS": "plans", "SDS": "plans", "SCS": "plans", "IVVP": "plans", "SRD": "dev", "SDD": "dev", "CODE": "dev",
          "TRACE": "dev", "SVCP": "ver", "SVR": "ver", "PR": "ver", "SCI": "final", "SECI": "final", "SAS": "final",
          "SCMR": "final", "SQAR": "final"}
