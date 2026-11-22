# The writer prompt

One agent per page, dispatched by the pages workflow (stage `write`).

The agent reads this file and carries it out with the parameters its prompt gives, by the names used here: KG_GLOSSARY_CHECKOUT (this checkout), KG_TREE with VERSION and COMMIT (the pinned tree, its tag and its commit), PY (the interpreter), DIR and SECTION6 (the knowledge base under docs/ and its section-six heading, or none), PAGE and PAGE_ID (the page file and its id), BRIEF, SCRATCH (the page's scratch directory), APPENDIX (the rules appendix) and SPEC.

The proofreader of the same page reads the first section only; its own procedure is skills/write-campaign/proofread/common.md.

## The standard, the aids and the limits

### The standard

Every fact comes from KG_TREE read on disk at COMMIT, never from memory, another page or the web; every Elixir link embeds VERSION.

The standard the page is written to is two things and nothing else: the writing rules, the file APPENDIX (the shared page model and every active rule with its QA policy; the rule files themselves are under KG_GLOSSARY_CHECKOUT/guidelines/page/rules/active/, one rule per file, the file name its id, and the skeleton is KG_GLOSSARY_CHECKOUT/guidelines/page/page-template.md); the campaign spec's content for the page, extracted into BRIEF (the scope, which is the coverage floor; the notes; the cluster boundary and the assignments, a floor and never a fence; the campaign facts with the architecture, the configuration, the bans, mandatory features, cautions, rules and campaign-wide notes; a research pack of definition lines, ranges, censuses and callers that are hints to re-read on disk, never citations; and a page note on prior material).

The form is the skeleton and the rules; a page already on disk is neither a fact source nor a model for this one, and how this page meets the rules, its journey or model, its figures and its vocabulary, is designed from the material. A rule whose QA policy is off still binds the page; the policy only says that no check is run for it.

Five things older pages recorded in a side file now stand on the page itself:

- a count or a universal claim carries beside it the scope condition that makes it true;
- a lifecycle figure names, in the paragraph after it, the writers of its drawn fields that the page does not show, with the file and the reason;
- a bare span that means a local or a parameter says so in its sentence;
- a scope name the page leaves out is named as a seam or as left out, with the reason, where it would have appeared;
- and a claim the page could not strengthen stands in its last section, WEAKLY SUPPORTED CLAIMS, with what it rests on.

### The aids

Optional aids, none required and none a fact source:

- `PY KG_GLOSSARY_CHECKOUT/tools/qa/run.py --tree KG_TREE --spec SPEC PAGE` runs the automatic checks of the severity-1 rules (append `--json` to save a report, `--since <report>` for the delta, `--rule <id>` for one rule);
- `PY KG_GLOSSARY_CHECKOUT/tools/qa/views.py PAGE <view>` prints reading aids (regions, blocks, skim, openers, closers, post-fence, members, unreproduced, reshow, enumerations, claims, headings, figures, spine, writes --fields a,b);
- `PY KG_GLOSSARY_CHECKOUT/tools/writer/excerpt.py --tree KG_TREE path:A-B` prints one source unit in the page's fence form, and with `--whole path:A` the construct holding line A;
- anchors.py resolves symbols to definition lines and expand.py builds a page from a template whose @@c directives and [[key]] links it expands (KG_GLOSSARY_CHECKOUT/tools/writer/README.md);
- figures.py insert PAGE FRAGMENT --at LINE splices a figure and renumbers mark families.

### Research tools

Research tools on this machine:

- the tags file KG_TREE/tags with readtags when it exists;
- git grep, log and show in the tree;
- the compile database KG_TREE/compile_commands.json with clang-query when it exists;
- the symbol index, the codebase-memory-mcp MCP tools via ToolSearch (query "codebase-memory"), for where a name is defined, who calls it and what it calls (`list_projects` names the project of KG_TREE, `check_index_coverage` opens a file's questions, then `search_graph`, `trace_path` inbound or outbound, `search_code` and `get_file_outline`), with `git grep -n -p` the floor of every caller list, since the index's in-degrees are no census and a dispatch through a callback table is invisible to it;
- the semcode MCP tools via ToolSearch (query "semcode") for `find_implementors` and `find_registrations` alone, the functions installed in a struct member and the members a function is installed in, and for no other question;
- an OTHER SOURCES URL is the Link: or Closes: trailer of `git log -1 --format=%B <sha>`, taken verbatim, never a hand-built URL;
- what each tool gets wrong, measured, is in KG_GLOSSARY_CHECKOUT/skills/research-tools.md.

### The limits

Print at most about 25 KB per command; print a function by its range, never a whole file; save an output you will return to under SCRATCH and grep it instead of printing it again; every command replays your whole context, so plan the functions you need and print them together, and never print the brief, the rules or the page twice.

## The procedure

### The task and its bounds

You are writing one page of a Linux-kernel knowledge base: PAGE_ID in docs/DIR, documented at VERSION; the brief says what subsystem, architecture and configuration the page documents. You research it on the pinned tree, compose it, check it with the severity-1 checker and hand it over. The only files you write are PAGE and files under SCRATCH (create it).

Never edit another page, the campaign spec or this repository, and never run a git command that changes state. If the page already exists on disk when you start, a previous writer died: read it, keep what you verify on the tree, and finish it.

### Read

Read first, in this order, in slices of at most 25 KB per command, printing nothing twice: the brief; the writing rules, whole; the skeleton, KG_GLOSSARY_CHECKOUT/guidelines/page/page-template.md, for the sections and what each holds.

### What binds the page

The shape is what the rules ask and nothing more (a lead that says purpose, position and promise; the model figure under the lead or in SUMMARY, with the vocabulary settled once near it; the section-six drawings or lists; a DETAILS subsection that opens with why its subject exists and the model the reader holds, introduces every construct above its code with the excerpt's purpose, explains below it what the lines established, and closes on the state reached; a long function or definition read in outlined consecutive pieces; the logs, tracepoints, hand-offs and files that expose the mechanism, listed where the rules place them; the tests the tree carries for the walked code, each after the walk it exercises; the scripts and tools the tree carries for the subject, listed beside the observability lists; the last section, WEAKLY SUPPORTED CLAIMS, only when a claim remains that you could not strengthen); the design that meets it is yours, from the material.

If the page note names a removed revision, use it as research (units, callers, commits, figures) re-read on disk, and not as prose where the rules it was written under were weaker than today's: subsections without purpose or mental model, members and functions listed one after another, constructs introduced below their code, stitched fences, elisions at column 0, bare member spans, function links on signatures while the sentence explains lines deep in the body, vocabulary never settled.

OTHER SOURCES is rebuilt from the tree's trailers; carry over verbatim any reader-added line a removed revision holds outside a model's block.

The campaign facts of the brief bind the page: its bans, mandatory features, cautions, rules and campaign-wide notes, the configuration it documents and the architecture it fixes; name a configuration option where a claim depends on it, since a name of the build names nothing.

### Plan

Plan before composing, briefly, in SCRATCH/plan.md:

- the page's central question and the reader's starting knowledge;
- DETAILS as a journey or a model, one subsection per phase or facet in explanatory order (never one per symbol), each with its purpose and the model the reader holds;
- the vocabulary correspondence settled once near the model figure;
- the catalog (every symbol you excerpt, each with a definition unit and a concrete in-tree usage unit; every helper the prose names in DETAILS gets both);
- the figures (the model figure under the lead or in SUMMARY; at least one figure in every DETAILS subsection after Kconfig assumptions, which carries none, an unmarked one where the subsection has no shape of the trigger table, so that a reader who looks only at the figures follows the page; a figure for every shape of the trigger table a subsection carries; every cataloged function's concept in some figure so that the titles in page order read as the outline; the register drawings in a REGISTERS section with every bit, offset and macro verified against the header that defines them; a lifecycle strip for every cataloged struct whose field two or more shown functions write, with the writers you do not show named after it; unmarked figures where no site needs naming; new figures from the material are encouraged);
- the claims that carry a count or a universal word, each established on two differently shaped bases before it stands on the page with its scope condition;
- the observability lists;
- the tests of the walked code, the suites and cases the scope names and those one batched `git grep -n -w -e <name> -e <name> -- '*test*'` of the walked functions finds in the tree's test files, each with what the case feeds in and expects, how it reaches the code, the option that builds it and the fragment and command the tree gives for running it;
- the tree's scripts and tools for the subject, those the notes name and those one `git grep -l -w` of the subject's struct, file, ioctl and tracepoint names finds under `scripts` and `tools` outside `tools/testing`, each with what it does with the subject;
- the configuration options the paths depend on.

### Compose

Compose through the template tools, which is what makes the verbatim rule hold: SCRATCH/page.tpl with an `@@c path:A-B[,C-D...] [| note]` directive for every excerpt (one source unit per fence; a cataloged function whole from its signature to its closing brace in one unit or in outlined consecutive pieces; a fold only as a counted elision; a definition past 40 lines read in pieces by member group with an outline table before the first piece), `@@fig name` for a figure held in SCRATCH/figs/name.txt, and `[[key]]`, `[[text|key]]` (a member as `[[field|struct.field]]`, a name defined in several files as `[[name|name@path]]`), `[[@path:N-M]]`, `[[commit:sha]]`, `[[file:path]]` for every link; resolve the keys with `PY KG_GLOSSARY_CHECKOUT/tools/writer/anchors.py --tree KG_TREE resolve NAME... > SCRATCH/anchors.tsv`, check with `anchors.py check`, build with `PY KG_GLOSSARY_CHECKOUT/tools/writer/expand.py --tree KG_TREE --version VERSION --anchors SCRATCH/anchors.tsv --figures SCRATCH/figs SCRATCH/page.tpl PAGE` until it reports 0 errors.

Never type a source line into the page by hand. Write the prose in a few heredocs; after the first clean build, fix the template and rebuild or make narrow edits on the page.

### Check

Check with the checker only, as it runs by default:

- never pass `--include-off` and never name a rule whose policy is off with `--rule`, and make no reading pass of your own but the one over the claims, below;
- at most three whole-page runs, the first after the first complete build, each later one after a batch of fixes read through `--since`, with every violation at zero and every candidate read against its rule and fixed or kept with its reason in your report, one entry of qa.candidates_kept for each candidate the last run still prints: the finish step holds a page back from its commit when the checker prints more candidates than that list answers for, or a scope name the page names nowhere, so name every scope name where it would have appeared (explained, as a seam, or as left out with the reason) and report in unreproduced_hints one the pinned tree does not have;
- a changed excerpt comes from excerpt.py or a rebuild, never typed.

The rules whose QA is manual or off bind the page as you write it; a later proofreader reads for them.

### Read the claims

Read the claims once, with the fixes of the first run, so that the next run checks what the reading changed; a first run that asks for no fix is followed by the reading all the same, and by a second run when the reading changed the page.

`PY KG_GLOSSARY_CHECKOUT/tools/qa/views.py PAGE claims > SCRATCH/claims.txt` lists every prose sentence of the page that carries a count or a universal word, each with its line (no figure, table row or list item), and is the one view this procedure asks for.

Read the file in slices, and each sentence against facts.two-bases, facts.universal-claims, facts.guards, facts.config-effects and facts.unwitnessed from what you already hold, the units the page shows and the bases your plan records. The reading searches the tree for nothing: a second basis you do not hold is not fetched now. Each sentence ends in one of three states. It stands as written, because the lines the page shows establish it or your plan records its two bases.

It is corrected where it stands, by an edit of that sentence alone, when the edit makes it true and keeps what the paragraph needs from it:

- the universal word goes, or the set is restricted in the kernel's terms (the function, the file, the directory, the architecture);
- the condition that makes it true is added;
- the option is named where the sentence names a build;
- a restated guard takes the code's operator and constants;
- a motive no comment or commit states is cut or given its source.

It is listed when the count or the universal is the point of the sentence and rests on one check that stops short of the whole tree (the callers one search found, the writers in one directory, no other user of a name): the sentence states the scope that check covered, and the claim takes its entry in WEAKLY SUPPORTED CLAIMS as Not cross-checked.

A claim that rests on no check at all is corrected, never listed, and so is one that would be the section's eleventh entry, since the section fails the page past 10. A sentence a later fix writes is held to the same three states as you write it.

### Claims you cannot support

A claim you cannot support as the rules ask is strengthened before you report it:

- a count or a universal claim gets its second basis, or its sentence states the scope the one check covered (the files one build compiles, one directory, one architecture);
- a claim about code gets the code shown, or is reduced to what the shown lines establish;
- a model figure's simplification gets the exact rule in the prose beside it;
- a number measured on one build names the build;
- a value taken from the documented configuration names the option.

What you still cannot support goes on the page, in the last section WEAKLY SUPPORTED CLAIMS in the form its rule gives (the fixed paragraph, then one entry per claim, `- <class>, in "<DETAILS H3>": <what the page claims, what it rests on, what was out of reach>`, the class one of Not cross-checked, Code not shown, Simplified, Taken as given, in the reader's words, every span linked), and the section stands only when it has an entry.

### Hand over

List in the open_issues of your report, the structured output you return, everything you leave, each with its kind and its place: one of those four classes for an entry of the section, in the same words, or form for a weakness of the page's form (a figure you did not draw, a shape of the trigger table you left out, a length over a target); a proofreader starts from that list.

Before you finish, save the same report as JSON to SCRATCH/writer-report.json (a fallback if you die before returning: the structured output you return is the report of record, skills/write-campaign/scripts/finish.sh writes it over this file, folds its unreproduced hints into the campaign's amendments, and the proofreader reads it when it runs later), then hand over by returning the structured output and nothing else.
