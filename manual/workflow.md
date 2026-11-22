# Workflow notes

These notes describe the plugin's implementation. The [planning skill](../skills/plan-campaign/SKILL.md), [writing skill](../skills/write-campaign/SKILL.md), [topic skill](../skills/write-topic/SKILL.md) and [guidelines](../guidelines/README.md) define the procedures and contracts; this page adds no requirements and is not read by the workflows.

Architecture, configuration, bans, mandatory features, cautions, rules and notes come from the campaign plan. The scripts name no subsystem.

## Planning

```text
/kernel-glossary:plan-campaign <campaign>
```

The [planning procedure](../guidelines/campaign/planning.md) has eight steps: choose a name, record the request's constraints, inventory the pinned tree, build the page catalog, set boundaries, review the catalog, arrange batches, and present the plan for approval. The [plan format](../guidelines/campaign/spec.md) defines the file layout.

The planner builds the catalog itself. Its [workflow script](../skills/plan-campaign/plan.js) runs the `inventory` and `review` stages: one read-only agent per inventory area, then one fresh agent reviewing the catalog. A catalog of more than about sixty pages is reviewed in parts instead: the planner passes `parts`, and one fresh agent per part reviews that part's pages against its digests and writes its own review file.

Every page is a row in a plan. Approving a campaign's plan approves its catalog; it does not start writing. A request for one page starts with a one-page plan, which the topic skill makes; see [One page on a topic](#one-page-on-a-topic).

## Selecting pages and stages

```text
/kernel-glossary:write-campaign <campaign> <B-id|page|all>... [stage=write|proofread|both]
```

The skill accepts batch IDs, explicit page IDs or `all`, mixed as needed. `all` selects catalog pages not yet on disk. Batch selection also skips pages already on disk; naming a page explicitly selects it even when it exists. The repository's rewrite convention still applies to rewriting committed pages.

The default stage is `write`:

- **`write`** runs one writer per page.
- **`proofread`** runs one proofreader per page, using the writer's report as hints and repairing the page as it reads.
- **`both`** runs writing and proofreading in sequence for each page.

For example, a batch can be written with:

```text
/kernel-glossary:write-campaign v7.2-pci B23
```

To proofread an existing page, use its page ID:

```text
/kernel-glossary:write-campaign <campaign> <page-id> stage=proofread
```

Additional `model=`, `effort=` and `proofread=` options are passed to the workflow. The writing skill contains the full argument contract.

## What a batch does

1. **Prepare.** [prepare.sh](../skills/write-campaign/scripts/prepare.sh) reads the plan and pinned tree, writes one brief per page, regenerates the rules appendix and prints the workflow's argument object. A brief is made from the plan and the tree alone: no other page on disk is read for it, so it does not change as pages are written.
2. **Run.** [pages.js](../skills/write-campaign/pages.js) runs the selected writer or proofreader stage for each page.
3. **Finish.** [finish.sh](../skills/write-campaign/scripts/finish.sh) recovers each page's `writer-report.json` from the writer's structured output in the run journal. It checks pages in catalog order, commits each new page that passes, and collects the writers' unreproduced hints. The commit's Co-Authored-By trailer names the model that wrote the page, read from the writer's transcript beside the journal.
   - A page that passes is held back, uncommitted, when the checker still prints a scope name the page names nowhere, or more candidates than the writer's report answers for; `--accept <page>` commits a held page as it stands. Its output has one line per page; `--dry-run` runs the gate alone.

The journal matters: the report file a writer saves can be shorter than the report it returns. The finish step uses the structured output recorded in `journal.jsonl` through `--journal`.

[fold.sh](../skills/write-campaign/scripts/fold.sh) appends unreproduced hints to the campaign's amendments file. Folding them into the plan is the planner's job, following the protocol in the campaign specification.

### Running without the finish step

Run `prepare.sh` yourself and pass the exact object it prints to the Workflow tool. The call has this form, with `preparedArgs` standing for that object:

```js
Workflow({
  scriptPath: "<checkout>/skills/write-campaign/pages.js",
  args: { ...preparedArgs, stage: "write" }
})
```

The workflow has no separate slash command. This route leaves the finish step to you.

## One page on a topic

```text
/kernel-glossary:write-topic [the topic] [stage=write|both]
```

The topic skill serves a request for a single page on its own. It differs from a batch only in where the brief comes from: a batch's briefs are assembled by script from a plan made earlier, while here the plan itself is made in the session, from the topic the user names or the conversation has settled and from what the session reads in the tree.

That plan is a one-page plan in the [plan format](../guidelines/campaign/spec.md): the Campaign block, one page block and its scope fence, under `campaigns/<version>-topic-<subject>.md`. Every topic is taken as new and its plan stands alone: the session opens no other plan and no page on disk, neither to look the topic up nor to borrow a setting, and a subject another plan or page also treats is no conflict. The pin and the research tools come from the tree, the directory and the section-six heading from the subsystem map, the architecture and the configuration from the user, and the campaign-wide fences hold only what the user asked of this page. The session writes the scope from the tree, validates it and shows it to the user. The [planning procedure](../guidelines/campaign/planning.md) says what such a plan keeps of the eight steps.

On the user's go the page is produced by the three steps of a batch, with the plan's name and the page's ID as arguments, so the writer prompt, the checks, the gate and the commit are the same. The plan stays under `campaigns/`, and the page is proofread later with `/kernel-glossary:write-campaign <plan> <page-id> stage=proofread`.

## Writer and proofreader prompts

Each writer receives the checkout, the pinned tree's tag and commit, the interpreter, the page, the brief, its scratch directory, the rules appendix and the spec. Its instruction is to read the [writer prompt](../skills/write-campaign/prompts/writer.md) and follow it.

The prompt defines the standard, the available aids and research tools, and the printing limits. The skeleton and rules define the page's form; another page on disk is not a model to copy.

The writer reads the brief, rules and skeleton, and writes `plan.md` in its scratch directory. That plan sets the central question, chooses a journey or model for DETAILS, inventories the catalog and figures, and identifies claims needing two bases. The writer composes the template, builds it with `expand.py`, and runs the checker at most three times while fixing every violation.

With the first run's fixes it reads the `claims` view once, without searching the tree again: a sentence with a count or a universal word stands as written, is corrected where it stands, or is listed under WEAKLY SUPPORTED CLAIMS as not cross-checked. It then returns its report.

A writer never edits another page, the spec or repository infrastructure, and never runs a git command that changes state. The finish script handles commits.

The proofreader receives the same parameter block, the first section of the writer prompt, and the writer's report as hints. It follows the [common procedure](../skills/write-campaign/proofread/common.md) and the selected [code](../skills/write-campaign/proofread/code.md), [figures](../skills/write-campaign/proofread/figures.md) and [explanation](../skills/write-campaign/proofread/explain.md) procedures in one pass. Those procedures name rules by ID prefix and supply reading steps using the relevant views or tools; they do not restate rules or repeat what the checker decides.

## Repository layout

The [manifest](../.claude-plugin/plugin.json) names the plugin. The planning and writing skill directories contain their workflow scripts, prompts and supporting shell scripts; the [inventory and review prompts](../skills/plan-campaign/prompts/) belong to planning, and the writer and proofreading procedures belong to writing. The topic skill is its procedure alone and runs the writing skill's workflow and scripts. [research-tools.md](../skills/research-tools.md) is shared by the writers, proofreaders and inventory agents.

[docs/](../docs/) contains the subsystem pages, [campaigns/](../campaigns/) the plans, and the git-ignored `progress/` directory the local campaign workspaces. [guidelines/](../guidelines/README.md) defines finished pages, campaign plans and subsystem mappings. [CLAUDE.md](../CLAUDE.md) contains the repository conventions.

The supporting tools are agent-maintained and promise no stable interface ([tools overview](../tools/README.md)); each has its own guide: [QA](../tools/qa/README.md), [writer aids](../tools/writer/README.md) and the [campaign tool](../tools/campaign/README.md). The rules loader and guidelines lint also live under `tools/`.
