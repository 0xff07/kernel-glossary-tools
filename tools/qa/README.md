# Optional QA

Install into the repository's virtual environment (`python3 -m venv .venv && .venv/bin/pip install -r tools/qa/requirements.txt`, Python 3.10+): PyYAML for the profile fence of `guidelines/page/page-model.md`, tree-sitter with its C grammar for the source facts the tree rules read. Each rule's optional `qa` frontmatter is read by `tools/rules.py`; the loader accepts `off`, `manual` and `auto`, with `off` as the default. The runner reports and writes nothing: no record, no state, no certificate.

```sh
python3 tools/rules.py list --qa
python3 tools/qa/run.py docs/subsystem/group/page.md
python3 tools/qa/run.py docs/subsystem/group/page.md --rule page.fence-close --rule excerpts.verbatim
python3 tools/qa/run.py docs/subsystem/group/page.md --rule style.hedges --include-off
python3 tools/qa/run.py docs/subsystem/group/page.md --json > /path/to/scratch/qa-1.json
python3 tools/qa/run.py docs/subsystem/group/page.md --since /path/to/scratch/qa-1.json
python3 tools/qa/views.py docs/subsystem/group/page.md skim
python3 tools/writer/excerpt.py --whole drivers/thunderbolt/tb.c:30
```

Inputs:

- the tree is `--tree`, else `$KG_TREE`, else the kernel checkout whose `.claude/` directory holds this repository;
- a page under `docs/<dir>/` takes its subsystem entry from `guidelines/subsystems.md`, its scope fence from `campaigns/<dir>.md`, the campaign being the one `--spec` names, else `--campaign`, else the page's directory (`` (`--spec`, `--scope`, `--subsystem`, `--evidence` and `--campaign` override).

A missing sheet counts as empty and is noted. Before a tree rule runs, the tree is validated:

- the cited URLs carry one version,
- that version is the tag at HEAD, and
- every cited file is tracked and clean;

a problem leaves the tree rules incomplete. `--since` compares with a report saved by `--json` and prints what is new, gone and standing, so a rerun after a batch of fixes costs little to read.

| Code | Result |
|---|---|
| 0 | Every selected automatic check passed; no manual rule and no candidate remains, or no QA was selected |
| 1 | A violation |
| 2 | An execution error, a missing input or an input problem: QA is incomplete |
| 3 | The automatic checks passed; manual rules or candidates remain to be read |

## Findings

A finding has a kind.

| kind | what it means |
|---|---|
| a **violation** | fails the rule |
| a **candidate** | an occurrence the procedure finds and cannot decide, which the writer or the orchestrator reads against the rule and records the disposition of, once, in the research notes |
| a **measurement** | decides nothing and is printed only under `--json` or per rule |

A rule's automatic check passes when it yields no violation. An exception to a violation is a ruling the user gave; it is recorded in the notes with its reason and reported, never silenced in the runner.

## Checker API

For a rule with `qa: auto`, place its complete implementation in `tools/qa/checks/<id>.py`; no registry is needed, and the lint refuses a checker whose name is no rule. Implement the whole rule, including its conditions and exceptions:

```python
from tools.qa.inputs import candidate, limits_of, violation

def check(page, context):
    yield violation(17, "offending text", "Explain the violation.")
    yield candidate(None, "a quote", "Explain what to read.")
```

`check` returns or yields findings:

- `line` is an original 1-based page line or `None` for a page-level finding,
- `quote` the page text the finding is about,
- `message` required.

A checker does its page-only work first, then asks for an input with `context.require("tree" | "facts" | "git" | "scope")`; a missing input raises `Missing`, and the runner keeps the findings yielded before it and reports the rule incomplete. Any other error, a wrong return value or an invalid line is an execution error, never a pass and never a silent switch to manual.

A checker carries no threshold, pattern or word list of its own: `limits_of(context, rule, unit, measure)` reads the rule file's `Unit | Measure | Target | Review candidate | Violation` table, `style_rows` its `Pattern | Kind | Scope | Unless | Exception` table and its `` `<name>`: `` word lists, `scalar` a number the rule states in words. A rule whose table the readers cannot parse fails the lint.

`tools/qa/page.py` implements `guidelines/page/page-model.md`; `tree.py` the tree, its facts and the git questions; `geometry.py` the display-cell inspection of figures; `source.py` the anchors, catalog-form and walkthrough procedures the excerpt and link checkers share; `style.py` the sweep. The campaign tool reads none of these.

## Views

`tools/qa/views.py <page> <what>` prints a reading aid for a manual rule and decides nothing: `prose`, `spans-visible`, `raw`, `regions`, `blocks`, `skim`, `openers`, `closers`, `post-fence`, `members`, `unreproduced`, `reshow`, `enumerations`, `claims`, `headings`, `figures` (each figure with its title, its mark count and family, then the gap since the last figure per subsection), `spine`, `writes` (the lines of the shown units that assign to a field or call a write helper, each with its tree line, `--fields a,b` narrowing them to named fields; the view a check reads against a lifecycle figure's legend and the writers it names as left out).

`tools/writer/excerpt.py --whole path:A` prints the construct holding line A as a unit ready to paste, through the same tree facts.

## Tests

```sh
python3 -m unittest discover -s tools/qa/tests -v
python3 tools/guidelines_lint.py
```

`tests/cases/` is the conformance corpus: each case is a page followed by a `<!-- kg:expect` block that states, as `[rule, FAIL | review, line, quote]`, every violation and candidate the rules derive for it; `tests/cases/tree/` is the small source tree the cases cite, made into a git repository by its `init.sh` at test time.

A case's expectation is derived from the rule file, never captured from a run; a case marked `reference_fails: true` states what the rule says where the checker is known to decide otherwise, and the test fails the day the checker catches up so the marker is dropped.

When a checker is added or changed, add a case that passes and one per failure shape, each a minimal edit of `clean-page.md` citing only the fixture tree. `test_qa.py` covers rule maintenance, policy selection and failure handling; `test_conformance.py` also checks every figure pattern under `guidelines/page/figures/` and every example figure of the `registers.*` rules with the figure rules.
