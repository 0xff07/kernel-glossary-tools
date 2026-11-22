# Rule maintenance notes

These notes explain how the existing rule files and tools fit together. The [writing standard](../guidelines/README.md), [page model](../guidelines/page/page-model.md), individual rules and [rule loader](../tools/rules.py) are the definitions and implementation. This page adds no requirements and is not supplied to writers or QA.

## Rule files

An active rule is one Markdown file under `guidelines/page/rules/active/`. Its filename is its ID. Its requirement, scope, numerical limits and exceptions stay together in that file. Shared terms and inspection views live in the page model, supplied once with the active rules.

Before changing a rule, look for other rules governing the same object and resolve overlapping obligations in their own files.

Moving a rule to `guidelines/page/rules/inactive/` disables it for writers and QA. Moving it back enables it. IDs remain unique across both directories; an inactive rule's policy and checker can be kept for later reactivation.

## QA policies

The rule loader reads the optional `qa` field from each rule's frontmatter:

- **`qa: off`** — the writer follows the rule; QA does not check it. This is the default when the field is absent.
- **`qa: manual`** — the writer follows the rule; QA checks it manually.
- **`qa: auto`** — the writer follows the rule; QA checks it automatically when a checker is implemented.

Every active rule is supplied to the writer, including rules with QA off. Inactive rules are neither supplied nor checked.

An automatic checker lives under `tools/qa/checks/`, named `<id>.py`. It yields violations, candidates or measurements. A violation prevents a pass; a candidate is read and its disposition recorded in the writer's report.

Each checker reads thresholds and patterns from tables in its own rule file. Without a checker, the same rule is checked manually. An error in an existing checker leaves QA incomplete. Conformance cases under `tools/qa/tests/cases/` exercise checkers against their rules.

## Running checks

From the plugin checkout, using the Python environment created during installation:

```sh
.venv/bin/python tools/rules.py list
.venv/bin/python tools/rules.py prompt
.venv/bin/python tools/rules.py list --qa
.venv/bin/python tools/guidelines_lint.py
.venv/bin/python -m unittest discover -s tools/qa/tests
```

The lint catches invalid metadata, rule dependencies, stale references among the documents, and references from the standard or its tools to the plugin layer. Meaning and contradictions still need review.

Thresholds and exceptions remain local to each rule. The writing principles, including soft length bands, model/journey structure and drawing requirements, remain part of the standard; mechanical checks run as per-rule checkers against the conformance corpus.

The [QA guide](../tools/qa/README.md) documents the checker API, inspection views and tests. The [writer aids](../tools/writer/README.md) and [campaign tool](../tools/campaign/README.md) have their own usage and test instructions.
