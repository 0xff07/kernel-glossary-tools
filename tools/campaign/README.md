# Campaign tool

One implementation of the procedures of `guidelines/campaign/spec.md`: validation, the index, a page's content, the notes and the assignments. That document says what each procedure does and how it is done by hand, and names no tool; this file says how this tool is run. Where the two differ, the tool is wrong. The planning procedure lives in `guidelines/campaign/planning.md`; page production is a process built on this tool, outside it.

## Setup

Install this tool's dependency separately from QA:

```sh
python3 -m pip install -r tools/campaign/requirements.txt
python3 tools/campaign/run.py --help
python3 tools/campaign/run.py validate campaigns/v7.2-pci.md --checklist
python3 tools/campaign/run.py --tree /path/to/linux content campaigns/v7.2-pci.md rc/portdrv/error-recovery --hints --out /tmp/content.md
python3 tools/campaign/run.py selftest
```

Neither the tool nor its tests require QA dependencies.

## Commands

`python3 tools/campaign/run.py [--glossary-checkout DIR] [--tree DIR] <command> ...` runs one command, each the procedure of a section of spec.md:

| command | section of spec.md | what it does |
|---|---|---|
| `validate <spec>` | [validate] | reports the errors and the warnings of a spec |
| `show <spec> <page>` | [kinds] | prints every fence that concerns one page |
| `index <spec>` | [index] | says which pages on disk catalog which symbols |
| `content <spec> <page>` | [prompt] | prints a page's content, from which a process assembles a writer prompt |
| `note <spec> <page> "<text>"` | [protocol] | appends a line to a notes fence |
| `assign <spec> <symbol> <page>` | [protocol] | adds or moves a row of an `assign` table |
| `selftest` | none | runs the tool's tests and checks the documents against the tool |

The two options before the command:

- `--glossary-checkout DIR` selects the checkout of this repository the tool works in; it defaults to the one holding the script.
- `--tree DIR` selects the kernel checkout; its default remains `TREE_ROOT`, the kernel checkout whose `.claude/` directory holds this repository.

`python3 tools/campaign/run.py <command> --help` prints a command's options. Every command but `validate` refuses a spec that does not validate: it prints the errors on standard error and exits 1. Exit statuses:

| status | meaning |
|---|---|
| 0 | done |
| 1 | an error of the tool's own, a spec that does not validate, content with gaps and no `--allow-gaps`, or an edit after which the spec does not validate |

### validate

`validate <spec> [--checklist] [--anchors] [--regions]` prints the warnings and then the errors on standard output, one line each, then a summary line that counts the fences, the pages, the clusters, the assignments, the errors and the warnings, and exits 1 when there is an error.

- `--checklist` adds the checklist: one row per page naming each empty input and, for a page in several clusters, its first cluster only, and one row per campaign-wide fence.
- `--anchors` adds the anchor check: one line per name found only outside the roots, a warning per name found nowhere, and a line that counts both. It needs the kernel tree, and a missing anchor changes no exit status. When the tree's `HEAD` is the pin and the names are many, the tool reads the tracked files under the roots once and answers every plain identifier as `git grep` would for it alone, so a catalog of thousands of names is checked in seconds; in a tree at another commit it asks the pinned commit's blobs name by name, which takes minutes.
- `--regions` prints the map of what was read, each fence's line range, kind and identity, to run after editing a fence.

### show

`show <spec> <page>` prints, each under a line naming the fence, the page's block, scope, notes and prompt fences, then for each of its clusters the block, the boundary and the cluster notes, then the Campaign block, the `bans`, `cautions`, `mandatory` and `rules` fences and the campaign-wide notes.

### index

`index <spec> [--page <page>] [--symbol <name>] [--conflicts] [--json] [--dir <dir>]` prints one listing on standard output and a summary of pages, entries and symbols on standard error. What it lists is context for the planner and reaches no prompt.

| option | what it lists |
|---|---|
| nothing | every symbol with its catalogers |
| `--page` | a page on disk's entries each with its other catalogers, or a page not on disk with its scope's catalogers |
| `--symbol` | one symbol's catalogers |
| `--conflicts` | the symbols two pages catalog from one file, and the `assign` rows whose catalogers on disk differ from the intended primary page alone |
| `--json` | the two indexes, by symbol and by page |
| `--dir` | another docs directory than the Campaign block's |

### content

`content <spec> <page> [--hints] [--out <file>] [--allow-gaps]` prints the page's content; the two sections below say what it holds.

- `--hints` adds the research pack.
- `--out <file>` writes the content to the file and reports its size on standard error; without it the content goes to standard output.
- With a gap, a missing scope fence or an unreadable reuse source, the command lists the gaps on standard error, writes nothing and exits 1; `--allow-gaps` carries them in the content as named gaps.
- After the content, the validation warnings that name the page go to standard error and the others are counted.

### note and assign

The two edits of the fold-in:

- `note <spec> <page> "<text>"` appends the line `- <text>` to the page's first notes fence and creates the fence when the page has none; with `--cluster <name>` or `--campaign`, the page then written `-`, the line goes to the notes of a cluster or of the campaign.
- `assign <spec> <symbol> <page>` adds the row to the `assign` table of the page's first cluster, or of the cluster `--cluster <name>` names, and creates the table when the cluster has none; it refuses a symbol another page owns unless `--force` moves it, and then prints the owner it replaced. A table written inline as `{...}` is not edited.

Each rewrites the file, keeping its final newline as it was, re-validates the spec and exits 1 on an error without undoing the edit. `validate` after the last edit shows the whole result.

### selftest

`selftest` runs the tests under `tools/campaign/tests/`. They run on a campaign this repository ships and invent nothing: each test works in a shared clone of this repository at HEAD, on `campaigns/v7.2-pci.md` and its pages under `docs/pci/rc/`, takes a removed revision or a reuse source from a commit of that clone, and reads the pinned kernel tree when `KG_TREE` or the checkout this repository lives in provides it; the tests that read the tree skip otherwise.

It then checks the documents against the tool: every `tools/campaign/run.py <word>` a document of this repository names is a command, and this file names every command and every option the tool takes.

## The page's content alone

`content <spec> <page> [--hints] [--out FILE]` prints what the spec says about one page and nothing about how to write it: MISSION (the scope, the page's notes, the notes and seams of other pages that name it, its cluster with the boundary and the assign rows), CAMPAIGN FACTS (the pin, the architecture, the configuration, the bans, the mandatory features, the cautions, the rules, the campaign-wide notes, the reuse pointers and, under `--hints`, the research pack), the spec's prompt fences and a SOURCES line. No page under `docs/` is read for it: who catalogs what is `index`'s answer, for the planner.

A process that assembles its own writer prompt starts from this text.

## The research pack

`content --hints` adds a RESEARCH PACK to CAMPAIGN FACTS (`guidelines/campaign/spec.md` [prompt]): for every name the scope and the page's `symbols` give, the definition lines, for a name defined more than `PACK_DEFS_CAP` times tree-wide those under the roots and a count of the rest (readtags on `<tree>/tags` when `readtags` and the file exist, each entry's search pattern settled to its line on disk by `tools/tagsfile.py`, a split signature at its first line; for a name the tags file lacks, or without a tags file, the column-0 lines of a `git grep -n -w` on which the name is the defined identifier, in the roots and then in the rest of the tree's code: a function's own line, a `#define`, a `struct`, `union` or `enum` opening line, a typedef or a variable, never a parameter type or an `EXPORT_SYMBOL`), a function's range to the brace that closes its body (a body of one or two lines is marked a stub definition; a `.c` body is listed before a header's), a `git grep -n -w` census counted over the whole tree and printed for the roots and then the rest of the tree's code up to 40 lines per name, the lines under another architecture, `tools/`, `Documentation/`, `samples/` or `scripts/` counted in one summary line and not printed, a name mentioned more than 200 times getting its count only, and, for a function, the callers by function among the printed lines (the first 12), each with its range, so that a stage excerpt is cut without another lookup.

The pack is hints: the writer re-verifies it in one batched command, which replaces the many small lookups a research phase otherwise spends a command each on.

The census is counted tree-wide on purpose, since a caller outside the roots is still a caller; what another architecture, the tools or the documentation say about a name is a count, because the page documents one architecture and cites the tree, not its copies.

A name the column-0 pass misses is looked up a second time: Universal Ctags over the roots (typedefs, members, enumerators, typedef'd structs), the Kconfig files for `config name`, and the definition shapes outside the roots.

