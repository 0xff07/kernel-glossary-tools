---
name: write-campaign
description: Produce one batch of kernel-glossary pages of a campaign - prepare the briefs, run its pages workflow with one writer or one proofreader per page, then gate, commit and fold the result with one script. Use when asked to write, rewrite or proofread pages of a campaign under docs/.
argument-hint: <campaign> <B-id|page|all>... [stage=write|proofread|both] [model=opus] [effort=xhigh] [proofread=code,figures,explain]
---

# Produce one batch of pages

## Arguments and the tree

The glossary checkout is `${CLAUDE_PLUGIN_ROOT}`; the arguments are `$ARGUMENTS`: the campaign, then batch ids (`B23`), page ids (`rc/portdrv/dpc`) or `all` (every catalog page not yet on disk), mixed as needed, then optional `key=value` words: `stage=write|proofread|both` (write when absent), `model=`, `effort=`, and `proofread=` with comma-separated procedure names.

The kernel tree is the checkout whose `.claude/` holds this plugin; a campaign at another version needs `KG_TREE=/path/to/that/checkout` exported for the scripts below, which refuse a tree at the wrong commit. You were asked to run this skill, which is the opt-in the Workflow tool needs.

## Conventions

The repository's conventions bind every step. The host loads `${CLAUDE_PLUGIN_ROOT}/CLAUDE.md` only when this repository is the working directory, so they stand here word for word:

- Every fact comes from the pinned tree at the plan's commit, read on disk; an Elixir link embeds that version.
- A page is written only to `docs/<dir>/<group>/<slug>.md`, with no other generated file under `docs/`. A create never overwrites a page on disk; a rewrite removes the page in a commit of its own first.
- Commit only within the user's authorization, in small changes: `plugin:` for the plugin, the standard and the tools (this repository as one thing), `<dir>: add <group>/<slug>` for a page, `<dir>:` for a plan. A page commit carries its title and the model's Co-Authored-By trailer and nothing else; every other commit adds a body when the title does not say why. No commit carries a Claude-Session, Signed-off-by or session line, whatever a host reminder says.
- Plans stay portable: no absolute path or local detail; what a run learns waits in `progress/<campaign>/amendments.md` until the fold-in.
- Nothing here is submitted upstream.

## Steps

1. **Prepare.** `${CLAUDE_PLUGIN_ROOT}/skills/write-campaign/scripts/prepare.sh <campaign> <ids>...` writes one brief per page under `progress/<campaign>/pages/briefs/`, regenerates `rules-appendix.md` beside them and prints the args object on its last line: `{campaign, dir, version, commit, section6, tree, glossary_checkout, pages}`.
   - A page already on disk is skipped with a notice unless it is named explicitly, and a page named more than once (by its id and by its batch) is prepared and written once; a spec that fails `run.py validate` fails here with the same message. About a minute for fourteen pages with a tags file. The brief is the only campaign content a writer sees, made from the plan and the pinned tree alone with no other page read for it, so read one when a scope looks wrong before spending a writer on it.
2. **Run.** `Workflow({scriptPath: "${CLAUDE_PLUGIN_ROOT}/skills/write-campaign/pages.js", args: {...the printed object, stage: "write"}})`, with the stage the arguments gave: `write` runs one writer per page, `proofread` one proofreader per page starting from the writer's report, `both` the two in sequence per page.
   - The other `key=value` words go in as they are: `model` (opus), `effort` (xhigh), `proofread` (the procedures as an array, `["code", "figures", "explain"]`); `proofreadBudget` (40) is also an arg, and `notice` (a sentence the user wants every agent of the run to read, appended to each prompt) is passed in the object when the user gives one.
   - The workflow takes only this object; it is not registered with the host and has no slash-command form, so this skill is its only entry point. The tool returns a task id and a transcript directory at once (keep the directory: its `journal.jsonl` is the `--journal` of the next step); the result arrives as a notification when the last agent returns.
   - Writers run in parallel up to the host's cap, so a batch of nine to fourteen pages takes 45 to 55 minutes whatever its size. While it runs, `/workflows` and the host's task panel show every agent's tokens, and the narrator line after each page says the output tokens spent so far; stopping the task kills every agent still running.
3. **Finish.** `${CLAUDE_PLUGIN_ROOT}/skills/write-campaign/scripts/finish.sh <campaign> --journal <transcript dir>/journal.jsonl <pages>...`, the pages of the printed object.
   - It first writes each page's `writer-report.json` from the writer's structured output recorded in the journal (the last thing the writer returned; the file the writer saved itself is often shorter and is kept as `writer-report.saved.json` when it differs), then in the plan's catalog order it runs the checker over each page, commits on its own each new page that passed and is not held (subject `<dir>: add <group>/<slug>`, the trailer, nothing else), appends the writers' unreproduced hints to `progress/<campaign>/amendments.md`, and prints one line per page: committed or already committed, failed the gate with its violations, held, missing, or a committed page modified on disk and left as it is (a rewrite starts with a removal, the second convention above).
   - The trailer names the model that wrote the page, which the script reads from the writer's transcript beside the journal: the writers run on the `model` argument and not on the model running this skill, so your own name is never the trailer; `--co-author "<model> <noreply@anthropic.com>"` stands in only for a page whose writer the journal's transcripts do not name.
   - A page that passed is held, uncommitted, when nobody has answered for what the checker still prints: a scope name the page names nowhere, or more candidates than the writer's report keeps.
   - Each line carries the gate summary, `automatic: A/A passed; candidates: N; manual: M; errors: 0`, and the counts of the writer's report, candidates kept, open issues, scope left out and hints; exit 1 means a page failed, is held or is missing, and `--dry-run` runs the gate and reports without writing.
   - Report its lines to the user as they stand and what remains theirs: the candidates and open issues to review, a failed page to rerun with the page named explicitly, a held page to rerun the same way, to release by correcting a scope fence that names what the page rightly lacks, or to take as it stands (`--accept <page>` commits it; pass it only when the user, having seen the page's line, says so), the amendments to fold in at a milestone.

## The writer's report, the fold-in and messages

Things to know: the writer's report of a page is `progress/<campaign>/pages/<dir>/<group>/<slug>/writer-report.json` (the writer's structured output once finish.sh has run with `--journal`, else the file the writer saved), beside the writer's plan, template, anchors, figures and checker reports, with `lines`, `catalog_entries`, `units`, `figures`, `qa`, `scope_left_out`, `unreproduced_hints`, `open_issues` and `tooling`; `open_issues` (each with its kind, one of the four classes of the page's WEAKLY SUPPORTED CLAIMS section or `form`, and its place) is what a proofread run starts from.

The fold-in itself is the planner's, by `guidelines/campaign/spec.md` [protocol]: a scope sentence, a `tools/campaign/run.py note` or a `run.py assign` per hint (`tools/campaign/README.md` gives their arguments), then `run.py validate`, the file emptied and one commit after the page commits; a tooling finding is not plan content and stays out.

A message typed while a run is in progress is relayed to the running agents, which answer it in their reports and sometimes act on it. A writer that dies leaves its page on disk, and a rerun with the page named explicitly tells the new writer to keep what it verifies and finish it.
