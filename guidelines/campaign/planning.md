# Planning a campaign

A campaign is a documentation set of tens of pages. It starts with a plan the user approves, kept in a committed, machine-portable spec at `campaigns/<campaign>.md`; its pages are then produced by whatever process this repository provides, in batches whose state is derived from the catalog against `docs/`, and what a run learns returns to the spec at the fold-in (`guidelines/campaign/spec.md` [protocol]). The planner plans; catalog design is the load-bearing judgment and is never delegated.

## Planning [planning]

1. [planning.name] Choose the campaign's short name (one to three lowercase hyphenated words naming the area), check it against `campaigns/` and `progress/`, and create the spec and the workspace `progress/<campaign>/` the moment planning starts.
2. [planning.constraints] Extract the request's constraints before touching the tree, verbatim into the spec's Context and Scope: the tree with its version tag and commit pin, the architecture scope, the granularity preference, the emphasis areas, any wording bans or mandatory tools, and the topic list, with every gap the request admits noted as work.
3. [planning.inventory] Inventory with parallel read-only agents, one per area, the areas cut along the request's own headings and as many as the subsystem takes: an area is what one agent can read through and digest, so a large subsystem gets more areas, never larger ones, and no area is merged with another to keep the count down. Each agent gets the inventory prompt the workflow provides.
   - Record every digest verbatim in the spec, one Inventory findings subsection per area; every line number in a digest is a hint to re-verify at write time.
4. [planning.catalog] Curate the catalog yourself. Map every bullet of the request to one or more pages, curate gap-fill pages for what the digests surfaced, and record a fold-in adjudication for every suggested topic that gets no page.
   - Place every in-tree test the digests list (`coverage.tests`): a suite is folded into the page of the code it tests, its suite and case names written into that page's scope, and a suite that tests the code of several pages is named in each of them; a test may get a page of its own when it is large, a framework whose fixtures, mock devices, helpers or runner the tests of several pages rest on, or a suite with more cases than the pages of the code under test can carry, and that page then owns the machinery while each page of the code under test keeps the cases that pin its own functions.
   - Note every script and tool the digests list (`coverage.scripts-and-tools`) on the page of its subject, one line of that page's notes fence each, by its path, since a path gives no scope name.
   - Each page is a `yaml kg:page` block carrying its identity `<group>/<slug>` (the output path `docs/<dir>/<group>/<slug>.md`) and a tag, requested or curated, with an `md kg:scope` fence carrying the scope statement that names its anchor symbols, without line numbers, since the writer re-finds every one (`guidelines/campaign/spec.md` [page]).
   - Validate every fence and ask the pinned commit whether every name a scope fence carries exists there (`guidelines/campaign/spec.md` [validate]), so a renamed or invented anchor is caught before the review.
5. [planning.boundaries] Write one boundary statement per sibling cluster as its `md kg:boundary` fence, naming the seam symbol, and seed the cluster block's `assign` table from the seams it names; validation refuses a symbol assigned to two pages.
   - A boundary is a floor, never a fence: it says what a page must cover exhaustively (the definition excerpt, the lifecycle, the locking, the enumerated call sites), and any other page reaches the same symbol to whatever depth its own narrative needs and catalogs it too where its narrative owns a use of it; a symbol two pages catalog is no conflict (`sections.coverage-form`).
6. [planning.review] Have the catalog adversarially reviewed by a fresh agent with the review prompt the workflow provides, or in parts by one fresh agent per part when the catalog is too large for one reviewer, apply the amendments you accept, and record the outcome.
7. [planning.batches] Order the batches foundational to derived: encodings and counters before the objects that hold them, objects before the machinery that indexes them, machinery before the syscalls that drive it, core mechanisms before driver instances, in batches of about five pages. A batch is advice to the invoker, never a state machine.
8. [planning.checkpoint] Checkpoint with the user: only the genuine scope questions, each with two to four concrete options, then the final catalog and layout, then an explicit go. The go approves the catalog and starts nothing; execution happens only through invoked batches.

A plan is complete when the spec:

- records its own name, path and workspace;
- carries no absolute path or local detail;
- carries the re-entry contract;
- maps every request bullet to a row or a fold-in;
- gives every row its path, anchor symbols and tag;
- states the projected total and tag census;
- names a seam symbol per cluster;
- records the fold-in list, the digests with their version-specific renames and the four enumerations of `coverage.observability` (tracing integration, debug printing, deferred processing, debugging infrastructure) populated or verified negative per area, the in-tree tests of `coverage.tests` placed or verified absent per area, the scripts and tools of `coverage.scripts-and-tools` noted or verified absent per area, the batch order with the write-time cautions, the review's accepted amendments, the user checkpoint with its decisions, and the save and commit policy.

## A plan of one page [one-page]

A page asked for on its own is still a row of a plan. Its plan is a spec of one row, the layout of `guidelines/campaign/spec.md` [minimal] with the campaign constants the request and the tree give it, and whoever takes the request makes it with the user, in the conversation that asks for the page. Each such plan is new and stands alone: no other plan is read for its topic, its constants or its fences, and a symbol its page shares with another plan's row or with a page on disk is no conflict ([planning.boundaries]).

It keeps [planning.name], [planning.constraints], the one row of [planning.catalog], its scope written from the tree and its anchors asked of the pin, and the go of [planning.checkpoint], which here starts the page as well. It has no area to inventory, no cluster to bound, no catalog to review and no batch to order, and it is complete when it records its name, path and workspace, carries no absolute path or local detail, and gives its row its path, anchor symbols and tag.

## The spec's structure [spec]

A spec is one Markdown file in the fence layout of `guidelines/campaign/spec.md`: tools read only the fenced blocks whose info string carries `kg` (`yaml kg:campaign`, `yaml kg:cluster`, `yaml kg:page` for structure; `md kg:scope`, `md kg:notes`, `md kg:prompt`, `md kg:boundary`, `md kg:bans`, `md kg:cautions`, `md kg:mandatory`, `md kg:rules` for text a prompt carries verbatim), and everything else in the file is prose for people.

The planning record below is that prose, or a companion file; nothing a prompt must carry lives only there, and validation's checklist names the prompt inputs a page or the campaign leaves empty (`guidelines/campaign/spec.md` [validate]).

1. [spec.context] Context: what was asked and where the requirements come from, the short name with the spec's path and the workspace, the tree with tag and commit, what is explicitly not an input, the output root, the portability rule; the pin itself lives in the Campaign block.
2. [spec.re-entry] Re-entry contract:
   - confirm the tree pin and the Elixir tag first;
   - derive state as the catalog-versus-`docs/` diff, the subdirectories the Campaign block's `exclude` names left out (`guidelines/campaign/spec.md` [index]), which says what exists and never what is finished;
   - create or reuse the workspace `progress/<campaign>/`;
   - write only the invoked batch, and a page on disk is never overwritten by a create;
   - record anything durable a run learns in the workspace's amendments file for the fold-in (`guidelines/campaign/spec.md` [protocol]), or surface it to the user for a ruling.
   - The spec names the standard's sections by slug and never a process path that only git history holds, so it stays executable on any machine after the repository changes shape.
3. [spec.scope-decisions] Scope decisions, numbered, as the user confirmed them.
4. [spec.inventory] Inventory findings, one compact digest per area.
5. [spec.directories] Directory organization with its rationale.
6. [spec.catalog] Page catalog: the page blocks with their scope fences, grouped under whatever headings read well, the cluster blocks with their boundary fences and `assign` tables, and, as prose, the fold-in adjudications and the projected total with tag census.
7. [spec.execution] Execution and verification:
   - the campaign's own deltas to the writing standard as prose;
   - the project-specific bans, the mandatory page features, the write-time cautions and the rules that bind every page as their `md kg:*` fences;
   - settled facts as `md kg:notes` fences on the page, the cluster or the campaign they concern, written at planning and at the fold-in (`guidelines/campaign/spec.md` [protocol]);
   - the recommended batch order as `- B<n>: page, page` lines and the save and commit policy as prose.
8. [spec.draft-reuse] Draft reuse map, when prior material exists:
   - per source file a verdict (backbone-reusable, mine-sections-only, ignore), symbol spot checks, defect classes with counts, and section-to-page mining pointers;
   - a superseded corpus is archived under a tag of this repository, `archive/<campaign>-<YYYY-MM>-<version>` on the commit holding it, created at the go and before the first slice, and cited by tag and path, which is what a reuse pointer's `source` names (guidelines/campaign/spec.md [campaign]);
   - a clone that lacks the tag cannot read the pointer, which the prompt then carries as a gap.

Run outcomes are recorded only in run logs, never in the spec, and nothing in the spec says when something was learned. A lesson that settles an adjudication is surfaced to the user, who alone makes it a ruling; the ruling waits in the amendments file and lands in the fence it concerns at the fold-in, a scope sentence, a note or an `assign` row (`guidelines/campaign/spec.md` [protocol]).

## Deriving from drafts and from removed pages [deriving]

1. [deriving.map-first] Map first, read once: research agents read the draft corpus once and record the reuse map; later work consults the map.
2. [deriving.re-verify] Reuse structure, re-verify everything: a draft may contribute skeleton, ordering, tables and figures, and every symbol, line number, excerpt and claim taken from it is re-found on disk, because the renamed symbol is the staleness that survives spot checks.
3. [deriving.extend] Extend to standard: definition plus usage, full enumerations, lifecycle coverage. Scrub with every sweep pattern of the style table, add or correct provenance comments, carry OTHER SOURCES over verbatim and add your own `### Added by <model>` block with the commit entries the tree's trailers give.
4. [deriving.dispositions] Every source entry, section, behavior, enumeration, figure and reference gets a disposition; cuts shrink the derived page's catalog and scope in the same change, are recorded in the spec, and the page passes the completeness audit like a fresh one.
5. [deriving.rewrite] A committed page the user directs to be rewritten is prior material like any draft. It is removed in a commit of its own, `<dir>: remove <group>/<slug> for its rewrite`, made only on the user's commit go; the rewrite is then a create of the same catalog row whose content names the removed revision (`git show <commit>:docs/<dir>/<group>/<slug>.md`) as the derivation source together with the findings that motivated the rewrite.
   - Items 1 to 4 govern what may be reused and what is re-found on disk. There is no repair operation and no repair campaign: a page is created, or finished where a dead writer left it; a create does not overwrite a page on disk.
