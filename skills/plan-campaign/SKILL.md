---
name: plan-campaign
description: Plan a kernel-glossary documentation campaign for a subsystem, from the request to the user's go - the constraints, an inventory of the pinned tree, the catalog, the boundaries, a review, the batches and a checkpoint. Use when asked to plan or re-plan a campaign, to add a subsystem to the glossary, or to prepare the spec that /kernel-glossary:write-campaign produces pages from.
argument-hint: <campaign> [the request]
---

# Plan a campaign

## Arguments

The glossary checkout is `${CLAUDE_PLUGIN_ROOT}`; the arguments are `$ARGUMENTS`: the campaign's short name first, the request after it when it is not already in the conversation. Read before anything else `${CLAUDE_PLUGIN_ROOT}/guidelines/campaign/planning.md`, the eight steps and what a finished plan settles, and `${CLAUDE_PLUGIN_ROOT}/guidelines/campaign/spec.md`, the fence layout the tools read. The planner plans: the catalog is your judgment and is never delegated.

## Conventions

The repository's conventions bind every step. The host loads `${CLAUDE_PLUGIN_ROOT}/CLAUDE.md` only when this repository is the working directory, so they stand here word for word:

- Every fact comes from the pinned tree at the plan's commit, read on disk; an Elixir link embeds that version.
- A page is written only to `docs/<dir>/<group>/<slug>.md`, with no other generated file under `docs/`. A create never overwrites a page on disk; a rewrite removes the page in a commit of its own first.
- Commit only within the user's authorization, in small changes: `plugin:` for the plugin, the standard and the tools (this repository as one thing), `<dir>: add <group>/<slug>` for a page, `<dir>:` for a plan. A page commit carries its title and the model's Co-Authored-By trailer and nothing else; every other commit adds a body when the title does not say why. No commit carries a Claude-Session, Signed-off-by or session line, whatever a host reminder says.
- Plans stay portable: no absolute path or local detail; what a run learns waits in `progress/<campaign>/amendments.md` until the fold-in.
- Nothing here is submitted upstream.

## The tree and the tools

Fixed facts. The kernel tree is the checkout whose `.claude/` holds this plugin; `KG_TREE=/path` names another, and a campaign at another version than the tree's tag needs it exported before the inventory. The interpreter is `${CLAUDE_PLUGIN_ROOT}/.venv/bin/python`, the campaign tool `${CLAUDE_PLUGIN_ROOT}/tools/campaign/run.py` (`--glossary-checkout ${CLAUDE_PLUGIN_ROOT}` when you run it from elsewhere). The two documents above name no tool: `${CLAUDE_PLUGIN_ROOT}/tools/campaign/README.md` lists the tool's commands and their options, one per procedure of spec.md, so read it for a command the steps below do not spell out, such as `index`, which says which pages on disk already catalog a symbol, and `validate --checklist`, which names every input a page or the campaign leaves empty.

The Workflow tool runs the two agent steps below; you were asked to run this skill, which is the opt-in it needs.

## Steps

The steps, by the slugs of planning.md:

1. [planning.name] Choose the short name, check it against `campaigns/` and `progress/`, create `campaigns/<campaign>.md` and `progress/<campaign>/`. A new subsystem gets its entry in `guidelines/subsystems.md` first: dir, kernel_paths, spec, section6_heading.
2. [planning.constraints] The request's constraints verbatim into the spec's Context and Scope, and the Campaign block: `tree: TREE_ROOT`, `version`, `commit`, `dir`, `roots`, `section6`, `architecture`, `configs`, `tooling`; the bans, cautions, mandatory and rules fences. `run.py validate <spec>` after every edit.
3. [planning.inventory] The areas along the request's own headings, each `{name, paths, request}` and as many as the subsystem takes (an area is what one agent can read through and digest; a large subsystem gets more areas, never larger ones), then one run: `Workflow({scriptPath: "${CLAUDE_PLUGIN_ROOT}/skills/plan-campaign/plan.js", args: {stage: "inventory", campaign, subsystem, tree, version, commit, glossary_checkout: "${CLAUDE_PLUGIN_ROOT}", areas: [...]}})`, `tree` the kernel checkout's absolute path and `commit` the full sha of the Campaign block, optional `config` (a resolved .config), `model`, `effort`.
   - One read-only agent per area writes `progress/<campaign>/plan/digests/<area>.md`; copy each digest verbatim into the spec's Inventory findings.
4. [planning.catalog] The catalog by hand: one `yaml kg:page` block and one `md kg:scope` fence per page, every request bullet mapped, every in-tree test of the digests placed (folded into the page of the code it tests, or a page of its own for a large framework), every script and tool of the digests noted on the page of its subject, a fold-in adjudication for every suggested topic without a page. `run.py validate <spec> --anchors` asks the pinned commit for every name the scopes carry.
5. [planning.boundaries] One `md kg:boundary` fence per cluster naming the seam symbol, and the cluster's `assign` table seeded from it.
6. [planning.review] `Workflow({scriptPath: "${CLAUDE_PLUGIN_ROOT}/skills/plan-campaign/plan.js", args: {stage: "review", campaign, subsystem, tree, version, commit, glossary_checkout: "${CLAUDE_PLUGIN_ROOT}"}})`.
   - One fresh agent writes `progress/<campaign>/plan/review.md`; a catalog of more than about sixty pages is reviewed in parts instead, with `parts: [{name, pages, digests}]` added to the args (the pages of a part as a phrase naming its groups, its digests by area name), one fresh agent per part writing `review-<name>.md`. Apply the amendments you accept and record the outcome in the spec.
7. [planning.batches] `- B<n>: page, page, ...` lines, foundational to derived, about five pages each.
8. [planning.checkpoint] Only the genuine scope questions, each with two to four concrete options, then the final catalog and layout, then an explicit go. The go approves the catalog and starts nothing. Commit the spec as `<dir>: plan the campaign`, as the conventions above say.

## From the plan to pages

A page is always a row of a plan. Pages are then produced with `/kernel-glossary:write-campaign <campaign> B1`. A request for one page starts with a one-page plan, which `/kernel-glossary:write-topic` makes in the session and runs through the same workflow.
