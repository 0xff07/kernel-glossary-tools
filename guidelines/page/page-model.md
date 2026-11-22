# Page model

Read this shared vocabulary once with the active rules. It defines their terms and inspection views; each rule keeps its applicability, numerical limits, patterns and exceptions. The style and claim views have different scopes. This file adds no per-rule QA task or page-completion state.

## Profile [profile]

The constants of a Linux-kernel page, read by the tools as one block; a rule that restates one of them (the caution text, the section order, a URL form) states the same value.

```yaml kg:profile
source_lang: c                        # the info string of a source fence
comment: ["/*", "*/"]                 # the delimiters of provenance and elision lines
source_suffixes: [".c", ".h", ".S"]   # source files, whose constructs the tree facts look up
cited_suffixes: [".rst", ".txt", "Kconfig", "Makefile"]   # other files a page may cite, by suffix or by whole name
permalink: "https://elixir.bootlin.com/linux/{version}/source/{path}#L{line}"
commit_permalink: "https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id={commit}"   # a commit's page, built from its full hash and never fetched
sections: [SUMMARY, SPECIFICATIONS, COVERAGE, DOCUMENTATION, OTHER SOURCES, DETAILS]
catalog_sections: [SPECIFICATIONS, COVERAGE, DOCUMENTATION, OTHER SOURCES]
reference_sections: [REGISTERS, METHODS, PRIMITIVES, INTERFACES]   # section six
claims_sections: [WEAKLY SUPPORTED CLAIMS]   # the last section, present only when the page has an entry for it
register_headers: ["regs.h", "tb_msgs.h"]   # a file whose name ends in one of these holds register definitions
config_option: "CONFIG_(\\w+)"        # a span of this shape names the Kconfig option `config <1>`
upstream_trailer: [Link, Closes]      # the commit trailers that carry a commit's upstream URLs
example_consumer_paths: ["drivers/"]  # where a cited file outside the page's subsystem is an example driver
caution: |
  > CAUTION: AI-GENERATED CONTENT
  >
  > STRICTLY DO NOT SUBMIT THIS UPSTREAM UNLESS YOU ARE AN EXPERT INTIMATELY FAMILIAR WITH THIS SUBSYSTEM.
```

A **cited URL** is a URL the `permalink` template matches, `#L{line}` optional; its path, version and line are the template's parts, and the **documented version** is the version the page's cited URLs carry. A **commit URL** is one the `commit_permalink` template matches. A page's H2 sections are `sections` in that order, with at most one of `reference_sections`, its section six, between OTHER SOURCES and DETAILS.

## Paragraphs, words and sentences

A paragraph is one unwrapped prose line outside fences, headings, blockquotes, table rows, list items and indented material. Blank lines separate paragraphs. For counts, reduce links to their text and code spans to one word. Count whitespace-separated tokens containing a letter or digit, ignoring complete figure/prose numbering marks.

Split sentences at whitespace after `.`, `!`, `?`, or those terminators followed by a closing quotation mark; retain pieces containing a letter, digit or underscore.

## Block maps

For reading the arrangement, P is one prose paragraph, C a source fence, D a figure, T a table and Q a quotation fence. C/D/T/Q are blocks. A list or a fourth-level heading is neither a prose paragraph nor a block. Paragraph runs break at any other item and at a subsection boundary.

## Source units and bytes

A source excerpt is a fence whose info string is exactly `c`. A source unit is the code attributed to one `/* path/from/tree/root:LINE */` provenance comment. Provenance lines and counted elision lines are not reproduced source lines. The source bytes are the tracked, unchanged files at the documented upstream tag and commit, including tabs, trailing spaces and CR characters.

## Length checks

Targets guide writing; a count outside the target does not by itself fail the rule: a review candidate is read for whether the text needs its length. A violation fails. A target lower bound is not a rejection threshold unless the violation cell says so.

## Style matching and scope

Match case-insensitively unless the row explicitly specifies otherwise. A blank Scope cell means prose, reference, catalog and heading rows, excluding H2 headings. Catalog sections are SPECIFICATIONS, COVERAGE, DOCUMENTATION and OTHER SOURCES; reference is section six.

WEAKLY SUPPORTED CLAIMS is the claims region: no style row reads it, since its entries name in the reader's words what the page could not support, and no claim view reads it; its links are checked like any other.

The style rules govern the author's own words and nothing the page carries from elsewhere, in whatever form it stands:

- source fences, quotation fences and blockquotes are excluded;
- every line of OTHER SOURCES, the shelf of cited commits and reader-added material, is excluded;
- a list entry of SPECIFICATIONS, which names a document and its section as the document does, is excluded, while the section's paragraphs are the writer's and read;
- and within a row that is read, links are reduced to their visible text and code spans, double-quoted runs (a quoted comment, message, subject or help text), source locations, double colons and numeric colon pairs are masked.

A match inside material the page quotes is therefore never a finding; a quotation left unmarked is the author's words until it is marked. The spans-visible form keeps code spans visible. A catalog-tagged row means a catalog row, any table row, or a section-six list item. Figure rows are appended raw after this masking; backticks or quotes inside drawings do not hide their text.

## Style inspection view

For this inspection, read the author's words only:

- reduce links to their visible text;
- mask code spans, double-quoted runs, location forms, double colons and numeric colon pairs;
- exclude source excerpts, quotation fences, blockquotes, every line of OTHER SOURCES and the list entries of SPECIFICATIONS.

Keep code spans visible for verification-narration. The + figure scope includes raw figure text. What a campaign bans or excludes binds the author's words in this same sense: a fence reproduces the source whole whatever vendor or topic its lines name, and the author's words about such lines are a phrase or a sentence, omitting what they can.

## Style matching outcomes

Read these matching boundaries with the writing requirement; a candidate requires judgement, not an automatic rejection. The exception column names permitted grounds.

## Claim sentences

A sentence is read as the prose view shows it, so a digit or a word inside a double-quoted run, a location form or a `<N>:<M>` pair counts as nothing. A code span hides nothing from the count: a bare number in backticks (`0`, `4096`) is a count like one in plain text, and a span holding an identifier is a mixed token (`CR3`, `x86_64`, `pci=hpbussize=8`) and no count; the universal words are read outside code spans.

It carries a **count** when it contains a digit run outside a version `v\d…`, an ordinal `\d+(st|nd|rd|th)`, a mark or a mixed token, or a number word (one through twenty, thirty through ninety, hundred, thousand) as a whole word outside a hyphenated compound, where `one` counts only when the next word begins with a letter, or is a masked code span, and is none of of, that, which, who, whose, to, is, was, and, or, in, on, at, for, with, by, as, than, from, into, the.

A **mixed token** is a run of non-space characters holding a letter or `_` and a digit together (`x86-64`, `IPU6`, `e1000e`, `CR3`, `0x8086`, a commit id, `pci=hpbussize=8`), and a **hyphenated compound** two or more words joined by `-` (`read-only`, `power-of-two`, `MSI-only`).

It carries a **universal word** when it contains, as a whole word, in any case and outside a hyphenated compound, one of: only, sole, solely, never, always, all, every, each, none, no other, nothing, anything, everything, whole, exactly, the one, the single; `once` counts only where it means one time, when the next token is a punctuation mark, the end of the sentence, or one of per, more, again, and never after `at`; `each other` and `one another` are fixed phrases and carry no universal word; `whole` carries none when it ends its clause or is followed by below, above, here, again, first or last.

The **claim sentences** of a page are the sentences of its prose lines in the prose and reference regions that carry a count or a universal word.

## Claim prose view

For these claim sentences, read prose lines in the lead, SUMMARY and DETAILS, and in section six (REGISTERS, METHODS, PRIMITIVES or INTERFACES). COVERAGE, SPECIFICATIONS, DOCUMENTATION and OTHER SOURCES are catalog regions and excluded, and so is WEAKLY SUPPORTED CLAIMS, which lists the claims the page could not support and makes none.

Prose lines exclude fences, headings, blockquotes, table rows, list items and material indented four spaces or a tab. Reduce links to their text, then mask code spans, double-quoted runs, location links/forms, `::` and `<N>:<M>` pairs before counting or reading universal words. This is the local prose view; retain original line locations.

## Fences

A line beginning with three backticks at column 0 opens a fence, and the next such line closes it; a well-formed closing line holds nothing but backticks and spaces, since a Markdown renderer keeps the fence open past any other. A fence no later line closes runs to the end of the page. Everything from the opening to the closing marker lies in the fence: no heading, span, link or paragraph is read there. A fence is:

| kind | when |
|---|---|
| a source excerpt | its info string is exactly `c` |
| a figure | any other info string stands on it and a body line carries a drawing character (box drawing and block elements U+2500–U+259F, arrows U+2190–U+21FF, geometric shapes U+25A0–U+25FF) |
| a quotation or listing | otherwise |

A figure whose body carries marks of a figure family, with the legend that names their sites, is a **marked figure**; one that carries none is an **unmarked figure**.

## Spans and links

A span is backticked text outside fences, blockquotes and H2 lines; a span written as a link's text is a linked span, any other a bare span. A link's class follows from its text, backticks and a leading `&` or `*` removed, the first that applies of:

| class | text |
|---|---|
| location | `<file>:<N>` or `<file>:<N>-<M>`, the file a path or a cited name |
| file | |
| config | a text matching the profile's `config_option` |
| field | `a->b`, `a.b`, `->b`, `.b`, chains included |
| commit | 10 to 40 hex digits |
| plain | a link whose text is not backticked |
| symbol | any other backticked text |

The symbol name of a text is the last identifier before its first `(` when it has one, else its last word with `*`, `&` and a trailing bracketed size removed; a text that is exactly `struct X`, `enum X` or `union X` names `X` with that tag, and only a definition of that kind is its definition. The cited files of a page are the paths of its provenance lines and of its cited URLs.

## Constructs

A construct is a definition in a source file, of kind function, struct, union, enum, typedef, variable or macro, with its first and last line; a struct or union member, an enumerator and a prototype are no constructs. The construct holding a line is the innermost whose lines contain it.

The declarations at a line are the constructs, members, enumerators and prototypes whose name that line carries as their defining line. Any method that yields these facts serves, a parse of the file with a C grammar first, a symbol index or a reading of the file where the parse is missing or errs; a parse decides where they disagree.

## Subsystem paths

A page's subsystem entry is the entry of `guidelines/subsystems.md` whose `dir` is the page's top directory under `docs/`; its `kernel_paths` are the subsystem's own source paths, directories ending in `/`, files or globs. A file lies in the subsystem when it is one of them, lies under one of the directories or matches one of the globs; every other file belongs to another subsystem.

An example driver is a cited file under one of the profile's `example_consumer_paths` that lies outside the page's subsystem, `Kconfig` and `Makefile` excepted; on a subsystem whose entry says `consumers: core`, no cited file is an example driver.

## Catalog [catalog]

A page's catalog keys are its COVERAGE keys, reduced to their symbol names; a member key `A.B` names a member and claims no symbol. The complete entry and trace definitions live beside the coverage-form rule.

## Scope names [scope-names]

A scope name is a C identifier, a tagged type (`struct X`, `union X`, `enum X`), a call with one balanced parenthesized argument list, or an array with one bracketed size. It takes the identifier, excluding C keywords. Families, expressions, fields, values and paths give no scope name. The request that dispatches a page gives its scope names; a campaign plan carries them in the page's scope fence.
