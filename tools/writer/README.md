# Writer tools

Mechanical aids a page writer may use. None is required: a page written by hand and a page built with them are checked the same way, by `tools/qa/run.py` against the active rules, and the tools decide nothing about a page. They exist because every verbatim excerpt a model types is output it pays for and a byte it can get wrong, and because a page carries hundreds of links whose anchors are looked up one at a time.

Standard library only, with two exceptions: `figures.py` reads the page through the QA engine's page model and needs PyYAML, and `excerpt.py --whole` asks the QA engine for the construct at a line and needs tree-sitter as well. `anchors.py` uses `readtags` when the tree has a `tags` file (through `tools/tagsfile.py`, which settles the file's search patterns to line numbers) and `git grep` otherwise.

```sh
python3 tools/writer/excerpt.py drivers/pci/pcie/err.c:210-218,236-243
python3 tools/writer/anchors.py resolve pcie_do_recovery 'struct pci_error_handlers' pci_error_handlers.error_detected CONFIG_PCIEAER > anchors.tsv
python3 tools/writer/anchors.py check anchors.tsv
python3 tools/writer/expand.py --version v7.2 --anchors anchors.tsv --figures figs page.tpl page.md
python3 tools/writer/figures.py insert page.md fragment.md --at 412
python3 tools/writer/figures.py rotate page.md --check
python3 -m unittest discover -s tools/writer/tests
```

Each tool takes `--tree` (default `$KG_TREE`, else the kernel checkout whose `.claude/` directory holds this repository) and prints its usage with `--help`.

## excerpt.py

Prints one source fence containing exactly one `path:A-B[,C-D...]` unit (with `--whole`, `path:A` names the whole construct holding line A, found with the tree facts of `tools/qa/`), the provenance comment `/* path:A */` with an optional `--note`, the lines verbatim from the working copy (or from `git show` with `--commit`), and a counted elision `... /* N lines, to :C */` between ranges, indented like the line it resumes at.

Multiple units, ranges past the file's end, descending ranges and ranges with no line between them are errors. Whether a unit begins and ends where the excerpt rules say is the checker's question, not the tool's.

## anchors.py

`resolve NAME...` prints `name<TAB>path:line<TAB>kind` for every definition it finds of a C identifier, a tagged type (`struct X`), a member (`A.B`) or a Kconfig option (`CONFIG_X`); `NAME@path` keeps only the definitions under that path. A name defined in several files prints several lines, and the writer keeps the one the page means; a name it cannot find goes to standard error and the exit status is 1.

`check TSV` re-reads a table and reports every line whose file does not spell the name at that line, the test the link checker applies to the finished page. An anchor is a hint to re-read on disk: the definition-line rule decides what a definition line is, and prototypes are left out.

A function whose signature is split (`static int` on the line above `name(...)`) resolves to the signature's first line, the return type's, which that rule names; `check` accepts the name line as well.

## expand.py

Builds the page from a template that is the page with shorthand outside its fences: `@@c UNIT [| note]` on a line of its own becomes the single-unit fence `excerpt.py` would print, `@@fig NAME` inlines `NAME.txt` from `--figures`, and inline `[[key]]`, `[[text|key]]`, `[[@path:N-M]]`, `[[commit:sha]]` and `[[file:path]]` become links at the one documented `--version`: a symbol through the anchors table, a location with the site text the site-text rule prescribes (the base name, or the path when another cited file shares it or the file is a Kconfig or Makefile), a commit through `git rev-parse` into the commit permalink, a file by its base name.

Put separate source directives on either side of the prose that connects and introduces their excerpts; a semicolon-separated list of units is an error. Text inside fences is copied untouched, so a built page can be rebuilt after the template changes. Every unknown key, missing file, line past a file's end and empty elision is printed, the page is written anyway so the places can be fixed, and the exit status is 1.

A writer who keeps the template and rebuilds after each fix emits only the prose and the directives; the excerpts come from the tree every time. Edits made to the built page and not to the template are lost at the next build, so fix the template, or stop building once the page is handed over.

## figures.py

`insert PAGE FRAGMENT --at N` splices a figure into a finished page. The fragment is the paragraph above the figure, the one figure fence and, for a figure with a legend, the paragraph that walks its marks; N is the page line the fragment goes before, the first line of a paragraph, heading, block or list after a blank line (`tools/qa/views.py PAGE regions` prints the numbers).

The drawing is indented four spaces when the fragment leaves it flat.

The tool refuses what the figure rules would refuse before anyone reads the drawing: a tab or a `c` info string in the fence, no drawing character, a line wider than the layout rule allows, no prose above the fence, a position inside a fence, between consecutive pieces of one source construct, between a figure and its walk paragraph, in a catalog section, or in a lead or SUMMARY that already holds its one figure.

The marks may be written in any figure family: after the splice every marked figure whose family the marks rule refuses, one equal to the figure before it or to another figure of its subsection, takes the first family in the order ①, ➊, «1», «A», @1, @A that its marks fit and that its neighbours and its subsection do not use, and the marks are rewritten in that figure's fence and legend, in the prose after it up to the next marked figure or the end of its subsection; a figure the rule accepts keeps its marks, so an inserted figure costs its own lines and nothing else, and an unmarked figure, with no marks and no legend, changes no other figure at all.

`rotate PAGE` does the renumbering alone, after figures were moved or removed by hand; `--check` prints what would change and writes nothing. The tool then names the figure rules to run on their own, a single-rule run that counts as no QA round: whether the figure is right, its legend sites shown and its walk paragraph complete is the checker's question.

A sentence before a figure that names its marks, and a mark two figures of one subsection share, are rewritten by hand; the tool prints every line it touched.
