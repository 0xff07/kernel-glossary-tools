---
name: write-topic
description: Write one kernel-glossary page on a topic the user names or the conversation has settled - make the topic a plan of one page in the session (the pin, the page and its scope), then produce the page through write-campaign's workflow, scripts and gate. Use when asked for a single page on its own, without planning a whole campaign; every topic is taken as new, and no existing campaign file or page is read.
argument-hint: [the topic] [stage=write|both] [model=opus] [effort=xhigh]
---

# Write one page on a topic

## Arguments

The glossary checkout is `${CLAUDE_PLUGIN_ROOT}`; the arguments are `$ARGUMENTS`: the topic, when the conversation has not settled it already, then the optional `key=value` words of `${CLAUDE_PLUGIN_ROOT}/skills/write-campaign/SKILL.md`, which pass through to its run.

A page is always a row of a plan. `/kernel-glossary:plan-campaign` plans tens of rows with an inventory and a review; this skill makes the plan of one row in the session, from what the user asked and what you read in the tree, and the page is then produced exactly as a campaign's page is. The plan stands alone: at no step do you open a file under `campaigns/` other than the one this run creates, another plan's workspace under `progress/`, or a page under `docs/` other than the one this run writes, neither for the topic nor for a setting, a model or a seam. Read before anything else `${CLAUDE_PLUGIN_ROOT}/guidelines/campaign/planning.md` [one-page], what such a plan keeps of the planning steps, `${CLAUDE_PLUGIN_ROOT}/guidelines/campaign/spec.md`, the fence layout the tools read, whose [minimal] is the skeleton of this plan, and `${CLAUDE_PLUGIN_ROOT}/skills/write-campaign/SKILL.md`, whose three steps step 6 carries out.

## Conventions

The repository's conventions bind every step. The host loads `${CLAUDE_PLUGIN_ROOT}/CLAUDE.md` only when this repository is the working directory, so they stand here word for word:

- Every fact comes from the pinned tree at the plan's commit, read on disk; an Elixir link embeds that version.
- A page is written only to `docs/<dir>/<group>/<slug>.md`, with no other generated file under `docs/`. A create never overwrites a page on disk; a rewrite removes the page in a commit of its own first.
- Commit only within the user's authorization, in small changes: `plugin:` for the plugin, the standard and the tools (this repository as one thing), `<dir>: add <group>/<slug>` for a page, `<dir>:` for a plan. A page commit carries its title and the model's Co-Authored-By trailer and nothing else; every other commit adds a body when the title does not say why. No commit carries a Claude-Session, Signed-off-by or session line, whatever a host reminder says.
- Plans stay portable: no absolute path or local detail; what a run learns waits in `progress/<campaign>/amendments.md` until the fold-in.
- Nothing here is submitted upstream.

## The tree and the tools

Fixed facts. The kernel tree is the checkout whose `.claude/` holds this plugin; `KG_TREE=/path` names another, and a plan at another version than the tree's tag needs it exported before step 4. The interpreter is `${CLAUDE_PLUGIN_ROOT}/.venv/bin/python`, the campaign tool `${CLAUDE_PLUGIN_ROOT}/tools/campaign/run.py` (`--glossary-checkout ${CLAUDE_PLUGIN_ROOT}` when you run it from elsewhere), whose commands and options `${CLAUDE_PLUGIN_ROOT}/tools/campaign/README.md` lists; `${CLAUDE_PLUGIN_ROOT}/skills/research-tools.md` says which research tool answers which question while you read the tree.

You were asked to run this skill, which is the opt-in the Workflow tool needs for the run of step 6.

## Steps

1. **The topic.** What the page is for, in the user's words: the question it answers, the code it is about and what it leaves out. Ask only what the request and the conversation leave open and the tree cannot answer.
   - Every topic is new. Search neither the catalogs under `campaigns/` nor the pages under `docs/` for it, now or later, and send no request back to a campaign: a subject another plan's row or a page on disk also treats is no conflict, since a symbol two pages catalog is none.
2. **The name and the place.** The subsystem's entry in `guidelines/subsystems.md` gives `dir` and the section-six heading; a new subsystem gets its entry first. The page is `<group>/<slug>`, both named from the topic alone, without a look at what `docs/<dir>/` holds; test only that this one path does not exist (a create never overwrites, the second convention above), and take another slug when it does. The plan's short name is `<version>-topic-<subject>`, the subject in one or two lowercase hyphenated words, a name neither `campaigns/` nor `progress/` has; create `campaigns/<name>.md` and `progress/<name>/`, and open the spec with a Context paragraph: the request verbatim, the plan's name, path and workspace, and that it is a plan of one page.
3. **The Campaign block and the campaign-wide fences.** Everything in them comes from the tree, the subsystem map and the user, and nothing from another plan.
   - From the tree: `tree: TREE_ROOT`, `version` and `commit` as it stands (`git describe --tags --exact-match` and `git rev-parse HEAD` at its root), `roots` (the paths the topic's code lies under), and `tooling`, the research tools the tree and the session have (a `compile_commands.json` or a `tags` file at its root, the symbol index), by the names `${CLAUDE_PLUGIN_ROOT}/skills/research-tools.md` gives them.
   - From the subsystem map: `dir` and `section6`.
   - From the user: `architecture`, and `configs`, the configuration the page is written against, a real one the user names, a copy of it resolved against the tree into `progress/<name>/` with `scripts/kconfig/conf --olddefconfig` as research-tools.md says, and recorded by its name and origin with the values of the options the topic's code sits behind. Ask for whichever of the two the conversation has not named; the tree's own `.config` belongs to the compile database and stands in for no configuration.
   - The bans, cautions, mandatory and rules fences hold only what the user asked of this page. None is needed: the page standard binds the page without them.
4. **The row.** Read the topic's code in the tree until you can write the scope: one `yaml kg:page` block (`tag: requested`, `symbols` by defining file) and one `md kg:scope` fence that says what the page is for and, name by name, what it owns: each structure it excerpts, each function it walks, each seam it names and does not walk. Every backticked name is a symbol defined at the pin, and no line number stands in it.
   - What the user said beyond the scope has its fence: a fact the writer should know is a line of the page's `md kg:notes` fence, and anything else, the emphasis, the figures to plan, what to leave out and why, is an `md kg:prompt` fence.
   - `tools/campaign/run.py validate <spec> --anchors --checklist` after every edit: no error, no name the pin lacks, and every empty input of the checklist left empty knowingly. The warning that the page belongs to no cluster is this plan's nature.
5. **The go.** Show the user the page's path, the scope fence as written, the architecture and the configuration the plan records, and the genuine scope questions only, each with two to four concrete options. The go approves the plan and starts its page. Commit the spec as `<dir>: plan <group>/<slug>`, as the conventions above say.
6. **The page.** The three steps of `${CLAUDE_PLUGIN_ROOT}/skills/write-campaign/SKILL.md`, Prepare, Run and Finish, with `<name> <group>/<slug>` as its arguments and the `key=value` words this skill was given, and its report to the user. Read the brief Prepare writes before spending a writer on it: it is everything the writer will know of the topic.

## After the page

The plan stays in `campaigns/`, so its page is proofread, finished or rerun like any other row: `/kernel-glossary:write-campaign <name> <group>/<slug> stage=proofread`. A later topic, however close to this one, is a new plan of its own.
