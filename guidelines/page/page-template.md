# TOPIC-NAME

(Use this skeleton with the shared page model and active rules supplied in the writer prompt. Remove the parenthesized guidance from the finished page.)

> CAUTION: AI-GENERATED CONTENT
>
> STRICTLY DO NOT SUBMIT THIS UPSTREAM UNLESS YOU ARE AN EXPERT INTIMATELY FAMILIAR WITH THIS SUBSYSTEM.

(The lead: what the mechanism is for, where it sits and what the page traces, in words a reader with no context can follow, symbols and counts only after that; within the lead's length targets and check boundaries, with at most one figure.)

(The model figure, under the lead or in SUMMARY: the objects and relationships the page is about, or the spine of its journey.)
(The figure's fence goes here at column 0, its body indented four spaces.)

## SUMMARY

(A map, not a walkthrough: the model, then the primary journey with its governing invariant or boundary, within SUMMARY's length targets and check boundaries, every sentence serving one of the four roles; at most one table or one figure within that section's limits, never both and never an excerpt, with prose on both sides. A spec-defined model is cited in SPECIFICATIONS; an unspecified model is a disclosed synthesis.)

## SPECIFICATIONS

(For a spec-defined topic, the normative source of the model, one entry per reference. State that none applies when the subsystem has no external spec.)

## COVERAGE

## DOCUMENTATION

## OTHER SOURCES

(Material no model generated, for grounding a model or checking the page by hand: the mechanism's commits with their mailing-list threads, and whatever a reader adds later. The reader writes anywhere in this section, in any form; a model writes only under its own `### Added by <model>` heading, commit entries taken from `Link:` trailers, and changes nothing else here.)

### Added by <model>

## REGISTERS

(The subsystem's section-six heading from subsystems.md: REGISTERS, METHODS, PRIMITIVES or INTERFACES, for the architecture constructs; omit the section when the entry says none.

Under REGISTERS: the registers, bitfields and fields the page touches, drawn, with the prose saying what each field decides on the page's paths, and no table of helpers per register; the helpers belong to COVERAGE and to DETAILS at their stage.

Under INTERFACES: the subject's contract with the code outside it as lists by use, each class under its own label, the entry points with who may call them, their context, locks and return, the inputs read from callers, the user-visible files and parameters, and the observability lists, with the tree's scripts and tools for the subject, where the page keeps them here, each symbol linked, no table and no excerpt; see `sections.interfaces`.)

## DETAILS

(The route: one paragraph within the route's sentence target, naming in order what the subsections after the Kconfig overview establish and the objects they act on.)

### Kconfig assumptions

(The fixed heading.

- A paragraph naming the configuration the page documents, its origin and the architecture;
- a table, one row per option the prose names, `option | assumed value | what it decides here`, the option linked to its `config` line;
- a closing paragraph saying the table indexes the prose.

An option the configuration leaves unset and one part of the page assumes set, a test's option, gives both values in its row.

An index only, and the one place the page states its configuration as a whole: the preamble above holds the route alone, and every effect is stated again, with the option named, where it applies in the subsections below.)

(A journey or a model: subsections that are the phases of a process in order, or the facets of the model, each cataloged symbol shown inside the phase where it acts beside its definition and usage excerpts and the paragraph that explains them, never one section per symbol in catalog order. Every catalog symbol appears here.

- Each subsection opens with why its subject exists and the model of objects and relationships the reader holds;
- the prose above every excerpt says what the construct is and what the excerpt is for before the code;
- one source unit per fence, an elision indented like the line it resumes at, every member span linked to its declaration line, and a definition past the excerpt target read in consecutive pieces by member group, each between its purpose paragraph and its explanation.

A test the tree carries for walked code follows that code's walk: the suite and the case, what the case feeds in and expects, how it reaches the code, the option that builds it and how the tree's files say it is run.

The scripts and tools the tree carries for the subject are listed beside the observability lists, each file linked with what it does with the subject.)

## WEAKLY SUPPORTED CLAIMS

(Only when a claim remains that the page could not strengthen or make exact; omit the section otherwise, and never leave it empty. The fixed paragraph below, then one line per entry, `- <class>, in "<DETAILS H3>": <what the page claims, what it rests on, what was out of reach>`, the class one of Not cross-checked, Code not shown, Simplified, Taken as given, in the kernel's words and the reader's, every span linked.)

The claims below rest on less than the rest of this page does, and this page could not strengthen them. Verify them before relying on them.
