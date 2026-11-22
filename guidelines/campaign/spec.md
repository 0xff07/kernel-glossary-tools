# The campaign spec format

A campaign spec is one Markdown file, `campaigns/<campaign>.md`. People write and read it as prose. Tools read exactly one thing in it: the fenced code blocks whose info string carries the word `kg`. Everything else in the file, the headings, the tables, the paragraphs and any fence without `kg`, is for people and reaches neither a tool nor a prompt. This document defines those fences and the procedures that read and write them, which an orchestrator carries out by hand or with a tool that implements them ([tools]).

`guidelines/campaign/planning.md` describes the planning work.

## The one rule [rule]

A fence is machine-read when its info string is `<language> kg:<kind>` followed by optional `key=value` attributes:

````
```yaml kg:page
page: rc/portdrv/error-recovery
```

```md kg:scope page=rc/portdrv/error-recovery
the recovery state machine: `pcie_do_recovery`, `pci_walk_bridge`, `merge_result` ...
```
````

**Two languages, two contracts.** A `yaml kg:*` fence holds structure: its keys are the schema below, validation ([validate]) checks them, and it is the only place where format needs care. An `md kg:*` fence holds text that a prompt carries verbatim: no format rule applies inside it beyond the fence itself.

A fence with `yaml` or `md` alone is an example or a quotation; validation warns when such a fence looks like a block (a `page:`, `assign:` or `commit:` key at column 0), because a forgotten `kg` is the one silent failure this layout allows.

**Identity lives inside the fences.** A page is the `page:` value of its block, and the `page=` attribute of its scope, notes and prompt fences names the same value. Headings carry no meaning to a tool, so a spec may title, order and group its sections as its readers like.

## The fence grammar [grammar]

**What a tool reads, exactly.** A fence opens on a line that begins with three or more backticks at column 0, indented by nothing and never with tildes; its info string is the rest of that line. It closes on the next line that begins with at least as many backticks and carries nothing else, so a fence quoted inside a longer one is not read; a fence no line closes is an error and is read to the end of the file.

An info string is machine-read when, after optional spaces, it is a language of letters, whitespace, `kg:` and a kind of lowercase letters, then the attributes; `kg:page` with no language before it is a plain fence and is read by nobody.

An attribute is `page=` or `cluster=` and its value, which runs to the next attribute or the end of the line and may hold spaces (`cluster=Port services cluster`); any other text after the kind is an error. The language `yaml` goes with the kinds `campaign`, `cluster` and `page`, `md` with the eight text kinds; any other pairing, `markdown kg:scope` included, is an unknown kind.

A YAML block is loaded as a mapping with a loader that refuses a repeated key at any depth; an empty block is an empty mapping. A page's identity is the string its `page:` value gives, and a cluster's `pages` entries and the `page=` attributes are compared with it as strings.

The backticked texts of a scope fence are read with `` `([^`]+)` `` over its whole body and reduced as `guidelines/page/page-model.md` [scope-names] says, each name once in order; unknown keys of a cluster or page block are ignored.

## The fence kinds [kinds]

| fence | count | holds |
|---|---|---|
| `yaml kg:campaign` | one | the pin and the campaign constants |
| `yaml kg:cluster` | any | a cluster's name, its pages and its `assign` table |
| `yaml kg:page` | one per page | the page's identity, tag and optional known symbols |
| `md kg:scope page=<page>` | one per page | the scope statement, pasted verbatim into the prompt; its backticked names are the page's coverage floor |
| `md kg:notes page=<page>` | any | facts for the next writer of the page, pasted into its prompt |
| `md kg:notes cluster=<name>` | any | facts for every page of the cluster, pasted into their prompts |
| `md kg:notes` | any | facts for every page of the campaign, pasted into every prompt |
| `md kg:prompt page=<page>` | any | free additions to the page's prompt, pasted verbatim: findings on a removed revision, seams the tables do not say, the figures to plan, anything |
| `md kg:boundary cluster=<name>` | one per cluster | the cluster's boundary statement, a floor, pasted into its pages' prompts |
| `md kg:bans`, `md kg:cautions`, `md kg:mandatory`, `md kg:rules` | one each, optional | the project-specific bans, the write-time cautions, the mandatory page features and the rules that bind every page, pasted into every prompt; a ban binds the writer's words as `guidelines/page/page-model.md` defines them, never the bytes a verbatim excerpt reproduces, and no excerpt is cut for a ban or an excluded topic |

An unknown kind or attribute is a validation error. A `page=` or `cluster=` attribute must name a block that exists.

## Every key [schema]

What each fence may hold, who reads it and what validation says when it is wrong. A tool may read every fence; the acceptance criteria read one, the page's `md kg:scope` fence (`guidelines/page/page-model.md` [scope-names]), and nothing else of the spec.

**`yaml kg:campaign`, exactly one:**

| key | value | required | meaning |
|---|---|---|---|
| `campaign` | short name | no, defaults to the file's base name | names the workspace `progress/<campaign>/` and the commit titles |
| `dir` | directory name | no, defaults to `campaign` | the pages live under `docs/<dir>/` |
| `tree` | `TREE_ROOT` or a path | yes | the kernel checkout; `TREE_ROOT` is the kernel checkout whose `.claude` directory holds this repository |
| `version` | release tag | yes | the tag every permalink embeds |
| `commit` | full 40-character sha | yes | the pin; stamped on every prompt, asked by the anchor check ([validate]) |
| `roots` | list of tree paths | no | where the research pack's definition search falls back to without a tags file, and where the anchor check searches first |
| `exclude` | list of directory names | no | subdirectories of `docs/<dir>/` that hold pages outside the campaign, an appendix of earlier material kept beside its pages; the index and the state derivation skip them ([index]) |
| `section6` | `REGISTERS`, `METHODS`, `PRIMITIVES`, `INTERFACES` or `none` | no | the reference section of the pages; a page block may override it |
| `architecture`, `configs`, `tooling` | text, list, text or mapping | no | copied into CAMPAIGN FACTS under their fixed labels; a `tooling` mapping is printed key by key, a `path` value inside it and a top-level `tags` value resolved against the tree root when relative, and names the tools of the research tools the workflow documents the campaign has |
| `reuse` | list of `{figure, source, note, pages}` | no | figure pointers; `source` is `<ref>:<path>`, what `git show` reads in this repository, checked with `git cat-file`; `pages` name page blocks |
| any other key | anything | no | copied verbatim under "Additional campaign fields"; the tool gives it no meaning |

**`yaml kg:cluster`, any number:**

| key | value | required | meaning |
|---|---|---|---|
| `name` | text | yes | the identity `boundary` and `notes` fences name with `cluster=` |
| `pages` | list of page identities | no | each names a page block; a page in no cluster is a warning |
| `assign` | mapping of symbol to page identity | no | the seam table; a symbol assigned twice, or to a page without a block, is an error; rows are added after a check pass ([protocol]) |

**`yaml kg:page`, one per page:**

| key | value | required | meaning |
|---|---|---|---|
| `page` | `<group>/<slug>` | yes | the identity; a second block for one page is an error |
| `tag` | `requested`, `curated` or `optional` | no | where the catalog entry came from |
| `section6` | one of the five values above | no | this page's reference section when it differs from the campaign's |
| `symbols` | list of `{file, names}` | no | known anchors by defining file, added to the research pack when one is asked for ([prompt]) and kept for the reader's orientation; not a floor |

**The `md` fences:**

| fence | attribute | count | read by |
|---|---|---|---|
| `md kg:scope` | `page=<identity>` | exactly one per page | the prompt, verbatim; `coverage.scope-closure`, for the backticked names |
| `md kg:notes` | `page=`, `cluster=`, or neither | any | the prompt of the page, of the cluster's pages, or of every page; the fold-in appends lines ([protocol]) |
| `md kg:prompt` | `page=` | any | the prompt, verbatim |
| `md kg:boundary` | `cluster=` | at most one per cluster; none is a warning | the prompts of the cluster's pages |
| `md kg:bans`, `md kg:cautions`, `md kg:mandatory`, `md kg:rules` | none | at most one each | every prompt |

A fence of an unknown kind, an attribute a kind does not take, a `page=` or `cluster=` naming no block, and a fence never closed are errors; a `yaml` or `md` fence without `kg` whose body looks like a block is a warning. The YAML of a block must be a mapping; a flow list `[a, b]` splits on every comma, so a value with a comma is quoted or written as a block sequence.

## The Campaign block [campaign]

```yaml
campaign: pci             # the short name; defaults to the file's base name
dir: pci                  # docs/<dir>/; defaults to the campaign name
tree: TREE_ROOT           # the kernel checkout whose .claude directory holds this repository, or a path
version: v7.2             # the release tag every Elixir URL embeds
commit: 8d3ae59288f1e7d58d76558a6ee96d533bc5019f
roots: [drivers/pci, include/linux/pci.h]   # where the anchor check ([validate]) searches first; optional
exclude: [appendix]      # subdirectories of docs/<dir>/ that hold pages outside the campaign, skipped by the index; optional
section6: REGISTERS       # the section-six heading, or omit; a page block may override it
architecture: x86-64 with ACPI firmware          # optional
configs: [CONFIG_PCIEPORTBUS with CONFIG_PCIEAER and CONFIG_PCIE_DPC as the documented build]   # optional
tooling:                  # optional; the research tools of the documented tree (the research tools the workflow documents), printed into every prompt with the paths resolved against the tree root
  symbol_index: {tool: codebase-memory-mcp, project: the tree root's}   # the index names its project after the tree root
  compile_db: {path: compile_commands.json, config: allmodconfig}        # relative to the tree root; generated by clang (LLVM=1), with the config it was built from
  tags: tags
reuse:                    # optional figure pointers; a source is <ref>:<path>, what git show reads in this repository
  - {figure: "DPC Control register (PCI_EXP_DPC_CTL)", source: "drafts:docs/pci/rc/portdrv/dpc.md", note: "redraw to scale under the register styles", pages: [rc/portdrv/dpc]}
```

`tree`, `version` and `commit` are the pin; validation refuses a block without all three, and every prompt is stamped with the commit. Any other key is carried into every prompt under "Additional campaign fields" with its YAML preserved; it acquires no meaning to the tool.

The block is YAML, so a list item that contains a comma is quoted or the list is written as a block sequence; a flow sequence `[a, b]` splits on every comma. Long prose does not belong in this block: bans, cautions, mandatory features and rules have their own `md` fences, where quoting and indentation are nobody's problem.

A campaign whose pages cover in-tree tests (`coverage.tests`) lists the tests' directories among its `roots`, so that the anchor check looks for a suite's and a case's name there first, and says in `configs` what the campaign's configuration does with the options that build them: their values there and, where it leaves a test unset, the options the pages on that test assume set. Those options are taken from the fragment the tree ships beside the test; the fragment itself is written for a test runner's own small kernel and is never merged whole into the campaign's configuration.

## The cluster block [cluster]

```yaml
name: Port services cluster
pages: [rc/portdrv/portdrv, rc/portdrv/aer, rc/portdrv/dpc, rc/portdrv/error-recovery]
assign:                   # symbol -> intended primary page; the contested and the explicitly assigned only
  aer_probe: rc/portdrv/aer
  pcie_do_recovery: rc/portdrv/error-recovery
```

The boundary statement is the cluster's `md kg:boundary` fence, a floor: it says what a page covers exhaustively, never what a page may not touch (`guidelines/campaign/planning.md` [planning.boundaries]). `assign` is the seam table, seeded from the boundary's seam statements and grown by the check passes ([protocol]).

A symbol may be assigned to a page of another cluster; the table is looked up across clusters, and validation refuses a symbol assigned to two pages or to a page without a block. An assignment identifies the intended primary page and guides default catalog selection. A symbol in no table is unassigned; boundary prose and catalogs on disk guide its placement.

The writer may also catalog a symbol normally left to another page when the local explanation benefits, applying the same catalog and excerpt requirements. Such coverage does not change its assignment.

## The page block and its fences [page]

```yaml
page: rc/portdrv/error-recovery
tag: curated              # requested | curated | optional; optional
section6: INTERFACES      # optional; REGISTERS | METHODS | PRIMITIVES | INTERFACES | none, when this page's family differs from the Campaign block's value (subsystems.md's note line); the prompt carries the page's value and names the campaign's beside it
symbols:                  # optional known anchors by defining file, added to the research pack when one is asked for and kept for the reader's orientation
  - {file: drivers/pci/pcie/err.c, names: [pcie_do_recovery, pci_walk_bridge]}
```

The scope fence is the writer-facing task and the page's coverage floor:

````
```md kg:scope page=rc/portdrv/error-recovery
the recovery state machine: `pcie_do_recovery`, `pci_walk_bridge`, `merge_result`, `report_error_detected` ...
```
````

Line numbers do not belong in a scope: they age with the tree, and the writer re-finds every name on disk.

`coverage.scope-closure` reads the backticked names of this fence as the symbols the page must name or account for (`guidelines/page/page-model.md` [scope-names]): write each as a symbol defined at the pin, never a family, an expression or a suffix shorthand, which name no symbol; `symbols` is not a second floor.

Every backticked name of the fence counts, so a correction to the scope is a line of the notes fence, never a bracket inside the scope. A test folded into a page is named in its scope like any other symbol, by the identifier of its suite and of each case the page is to cover; a test that is a file and no identifier, a shell selftest, is named by its path, which gives no scope name and reaches the writer as text.

A script or a tool the tree carries for the page's subject (`coverage.scripts-and-tools`) is a line of the page's notes fence, by its path.

Notes are lines of one fact each, undated, since the spec records what holds and never when it was learned ([protocol]); a prompt carries them after the scope:

````
```md kg:notes page=rc/portdrv/error-recovery
- `pci_dev_set_io_state` has a fourth caller, `pci_dev_set_disconnected` (drivers/pci/pci.h:759), named as a writer the page leaves out.
```
````

A `prompt` fence is the hand's channel into the generated prompt, free Markdown pasted whole. Anything that used to be a hand slot goes here in ordinary prose.

## What a page's content carries and where it comes from [prompt]

A process that writes a page assembles its own prompt; the spec's part is the page's content, what the plan says about one page and nothing about how to write it. The table says where each part comes from, so a process reads it from the fences and the pinned tree, by hand or through a tool.

| part | source |
|---|---|
| MISSION: the scope, the page's notes, the cluster's boundary and notes, the assign rows naming the page or its symbols and the cross-references below | the page's scope and notes fences, the cluster blocks with their boundary and notes fences and `assign` tables |
| CAMPAIGN FACTS: the pin, architecture, CONFIG assumptions, section six, tooling, bans, mandatory features, cautions, rules, campaign-wide notes, reuse pointers for this page, additional campaign fields | the Campaign block and the campaign-wide `md` fences; a reuse source checked with `git cat-file` |
| optional research pack | when one is asked for, for every name the scope and `symbols` give: the definition lines, for a name defined more than forty times tree-wide those under the roots and a count of the rest (readtags on the tree's tags file when both exist, otherwise the column-0 lines of a `git grep -n -w` in the roots on which the name is the defined identifier: a function's own line, a `#define`, a `struct`, `union` or `enum` opening line, a typedef or a variable, never a line that only mentions it in a parameter list or an `EXPORT_SYMBOL`), a function's range to the brace that closes its body (a body of one or two lines is marked a stub definition; a `.c` body is listed before a header's), a `git grep -n -w` census counted over the whole tree and printed for the roots and then the rest of the tree's code up to 40 lines per name, with the lines under another architecture (the directories the roots lie under and the `architecture` text names are the campaign's), `tools/`, `Documentation/`, `samples/` or `scripts/` counted in one summary line and not printed, a name mentioned more than 200 times getting its count only, and, for a function, the first 12 callers by function among the printed lines, each with its range, so that the writer cuts a stage excerpt without another lookup; every line a hint the writer re-verifies in one batched command; the census is counted tree-wide because a caller outside the roots is still a caller; never on by default; a name the column-0 pass misses is looked up with Universal Ctags over the roots (typedefs, members, enumerators), in the Kconfig files and by its definition shape outside the roots |
| free additions | the page's `prompt` fences, verbatim |
| Sources | the fences by line range the content drew from, the tree and its commit, and the gaps |

**Cross-references.** MISSION also carries every line of another page's notes or another cluster's notes, and every sentence of another cluster's boundary statement, that names this page by its slug (`slug` or `slug.md`, the slug bounded by no word character, slash or hyphen) or names a symbol of its scope four or more characters long in backticks (`` `name` `` or `` `name()` ``), each line once, under the fence it came from: facts settled elsewhere that bind here, each a hint to re-verify.

A boundary statement's sentences are its text split after a period before a capital, a backtick or a bracket; a notes fence none of whose lines match is carried whole when the fence as a whole matches.

**No page is read.** Nothing of `docs/<dir>/` enters the content: it names no cataloger of a scope symbol and no sibling on disk, so the content of a page is the same whatever else has been written. Who catalogs what is the planner's question, answered by the index ([index]).

**Build properties and nested families.** A scope sentence that asserts a build property, compiled, linked or absent from the default build, is carried with the gate it rests on, the `#if` or the Kconfig line, for the writer to state what the documented build compiles. When two scope fences name nested families (`PCI_EXP_*`, `PCI_EXP_SLTCTL_*`), the prompt's additions say which members each page catalogs.

**Gaps.** These are gaps:

- a missing scope fence and
- an unreadable reuse source.

Content with a gap is not handed to a writer until the gap is closed or carried as a named gap.

Assembling copies and reports; it does not research. Callers, in-function anchors and API lists are the writer's to derive with the research tools the campaign block names (the research tools the workflow documents) against the pinned tree, and a count the prompt carried would only be re-derived.

## Who catalogs what [index]

Per docs directory, the index pairs every symbol with the pages that catalog it: the names of each page's catalog entries (`guidelines/page/page-model.md` [catalog]), a **member entry** aside, keyed `A.B` (`guidelines/page/page-model.md` [catalog]): a member entry claims no owner, and one member may be cataloged on many pages; a malformed key, a declaration such as `bool hotplug_active`, claims none either and is skipped.

For a page not yet on disk, it says who catalogs each symbol its scope names. What it reports is context for the planner and never a decision, and it reaches no prompt ([prompt]): a symbol two pages catalog is information and no finding.

The index keys a symbol by its name and its defining file, so two pages cataloging one name in one file are listed together as its catalogers, and the same name defined in two files is two symbols, each shown with its file; the conflicts listing names the symbols two pages catalog from one file, and the `assign` rows whose disk catalogers differ from the intended primary page alone. Both listings provide context; additional catalogers do not invalidate an assignment or fail QA.

By hand: list the catalog entries of the pages under `docs/<dir>/` with a grep for the two entry forms, a bare entry's file being its URL's, and compare their names with the scope's.

- The pages are every `.md` file under `docs/<dir>/`, recursively, `README.md` and the subdirectories the Campaign block's `exclude` names left out (an appendix of pages outside the campaign is on disk and is nobody's cataloger), each identified by its path under the directory without `.md`;
- the COVERAGE section is the H2 whose title begins with `COVERAGE`, up to the next H2;
- its lines beginning `- ` are read, a traced key anywhere on the line and a bare key at the line's start, the bare entry's URL parsed with the profile's `permalink` and an entry whose URL the template does not match dropped;
- a key is reduced to its symbol name (`guidelines/page/page-model.md` [scope-names]).

The listing for a page not on disk marks a scope span that is a suffix shorthand as unresolvable.

## Validation [validate]

Validation reads every `kg` fence and reports:

- **errors:**
  - a YAML parse failure, a repeated key or a block that is no mapping;
  - no Campaign block, or a second one;
  - a Campaign block without its pin, or whose `commit` is not forty lowercase hex digits;
  - a `reuse` that is no list, a reuse row without a `source` holding `:`, or one naming a page without a block;
  - an `exclude` that is no list of relative directory names;
  - a page block without `page:`, or two blocks with one identity;
  - a page without exactly one scope fence;
  - a `tag` other than `requested`, `curated` or `optional`;
  - a page block's `section6` other than the five values (the Campaign block's is not checked against the five, but against the subsystem entry: a Campaign block whose `section6` disagrees with the `section6_heading` of the entry of its `dir` in `guidelines/subsystems.md`);
  - a `symbols` that is no list of mappings with `names`;
  - a `page=` or `cluster=` attribute naming no block;
  - a cluster block without `name`, or two clusters with one name;
  - a cluster `pages` entry naming no block;
  - an `assign` that is no mapping;
  - a symbol assigned to two pages or to a page without a block;
  - a notes fence with both `page=` and `cluster=`, a second boundary for a cluster, a second `bans`, `cautions`, `mandatory` or `rules` fence;
  - an unknown kind or attribute, text after the attributes, or a fence never closed;
- **warnings:**
  - a `yaml`, `md` or `markdown` fence without `kg` whose body carries `page:`, `assign:`, `commit:`, `tree:` or `version:` at column 0;
  - a Campaign block whose `dir` no entry of `guidelines/subsystems.md` carries (a new subsystem gets its entry first);
  - a page in no cluster;
  - a cluster without a boundary fence;
  - a suffix shorthand in a scope fence, a span opening with one underscore and a lowercase letter, optionally followed by `()`, which names no symbol (`guidelines/page/page-model.md` [scope-names]), one warning per fence listing them;
  - an `[errata …]` bracket in a scope fence, whose backticked names count as scope names like any other, the correction belonging in the page's notes fence;
  - and, as a checklist, per page and for the campaign, every prompt input that is empty (symbols, notes, cluster, boundary, prompt additions, reuse pointers; bans, cautions, mandatory, rules, campaign notes), so that a campaign planned thin is planned thin knowingly.

The anchor check asks the pinned commit for every identifier the scope fences carry, suffix shorthands set aside and each name once, `git grep -I -w -F <name>` under the Campaign block's `roots` and then over the whole tree, in the working tree when `HEAD` is the pin and in the commit's blobs otherwise: a name found nowhere is a warning naming its page, a name found only outside the roots is listed with the first file `git grep -l` prints, as the seam it presumably is, and a summary line counts both; a missing anchor changes no exit status.

The check is skipped when the spec has no Campaign block. It is the mechanical half of the plan review's anchor hunt (`guidelines/campaign/planning.md` [planning.review]), run before the review is dispatched; it asks only whether a name exists, never where its definition is or what calls it.

A spec that does not validate is given to no other procedure of this document.

## After a check pass, and the fold-in [protocol]

Between the planning and the fold-in the spec is not edited. Everything durable a run learns goes to `progress/<campaign>/amendments.md`, one dated line each naming the fence it concerns: a claim of the spec the tree refuted, a scope the run amends, a ruling the user made, a boundary the user moved, a page's rewrite.

A seam is no amendment: who catalogs a symbol is read from the disk, and a symbol two pages catalog is no conflict. At the fold-in, which the user calls at a milestone or at the campaign's end, each amendment is written into the fence it concerns as settled text without a date, and no other fence is touched:

- a sentence of the page's scope fence;
- a line `- <text>`, undated, appended as the last line of the page's first notes fence, the fence created after the page's scope fence, or after its page block when it has no scope, when none exists (a cluster's notes, created after the cluster's boundary fence or else its block, for a cluster; the campaign-wide notes, created after the last of the Campaign block and the `bans`, `cautions`, `mandatory` and `rules` fences, for the campaign); or
- a row in the `assign` table of the owner's cluster, the first cluster listing the owner unless one is named, inserted directly under its `assign:` line, the table created at the end of the block when there is none, and refused for a symbol another page already owns unless the user moves it, the row then rewritten in place in the cluster that holds it; a symbol already assigned to the owner changes nothing.

An `assign` table written inline as `{…}` is not edited. Then the spec is validated, the amendments file is emptied, and the fold-in lands as one commit per spec. Run outcomes stay in the run log, never in the spec, and a page's rewrite is a note on the page.

## Design principles [design]

- The minimum interface is small: the pin, a page's identity and its scope are enough to plan a page and assemble its prompt. Add symbols, clusters, assignments, notes and reuse pointers when they help; the examples show capabilities, not a form every campaign must complete.
- Design, tree facts and history age differently. The fences hold design; history waits in the run workspace until the fold-in ([protocol]) and enters a fence as settled text; tree facts are the writer's to derive at write time; the planning record (inventories, reviews, checkpoints) is prose outside the fences, or a companion file, and binds no page. Whatever a prompt must carry lives in a fence, never only in the record; validation's checklist says what is missing.
- A floor, never a fence: a scope and a boundary say what a page covers at least. Observed catalogs and unassigned names are context for planning; neither an absent entry nor an incomplete lookup creates an exclusion. No tool checks that a page catalogs only what it was assigned.
- Extensions are cheap: an unknown Campaign key passes through; a new kind of prose goes in a `prompt` fence; a tool grows only when a repeatable mechanical operation is actually needed.
- Preservation is checked by a list, not a diff: every mechanism a hand-assembled prompt carried has a named source in the table above, validation's checklist reports the empty ones, and the first slice of a new campaign compares one hand-assembled prompt against the generated base before the rest are dispatched.

## Tools [tools]

Every procedure of this document, validation, the index, a page's content, the notes and the assignments, can be carried out by hand from the sections above, and a tool may carry out any of them. A tool implements this document and is never its source:

- a format changes in this document and in `guidelines/page/page-model.md` first, and where a tool and they differ, the tool is wrong;
- a tool that carries out a procedure gives the answer the procedure defines: the errors and warnings of a spec, the catalogers of a symbol, the content of a page;
- what a tool is called, where it lives and how it is run are the tool's own documentation to say, and this document names none.

## A minimal spec [minimal]

````markdown
# Example campaign

```yaml kg:campaign
campaign: example
tree: TREE_ROOT
version: v7.2
commit: 8d3ae59288f1e7d58d76558a6ee96d533bc5019f
```

## Error recovery

```yaml kg:page
page: rc/portdrv/error-recovery
```

```md kg:scope page=rc/portdrv/error-recovery
the recovery state machine: `pcie_do_recovery` (err.c), `pci_walk_bridge` and the callbacks it runs
```
````

It validates, and the prompt of `rc/portdrv/error-recovery` assembled from it is a base with the scope and the fixed parts. A full spec in this layout is `campaigns/v7.2-pci.md`.
