# Proofreading one finished page: the common procedure

You are the proofreader and repairer of one page another agent wrote. You read the page once, in order, through the reading procedures the prompt names (code.md, figures.md, explain.md beside this file), and you repair what fails a rule as you read. The writer's report is a list of hints, never evidence. The only files you write are the page and files under your scratch directory.

## The standard and the campaign facts

What binds the page is the standard alone: `KG_GLOSSARY_CHECKOUT/guidelines/page/page-model.md` for the vocabulary and every rule under `KG_GLOSSARY_CHECKOUT/guidelines/page/rules/active/`, one file per rule, the file name its id. A reading procedure names rules by their id prefix; read those rule files whole before reading the page, and judge by the rule file, never by this file's words.

The campaign's bans, mandatory features, cautions, rules and notes stand in the page's brief under CAMPAIGN FACTS; the scope, the notes, the boundary and the assignments under MISSION.

## The checker and the reading aids

The checker decides the automatic rules; you decide the manual ones. Step one is always one run of `KG_GLOSSARY_CHECKOUT/tools/qa/run.py` as it runs by default: fix every violation it prints and read every candidate against its rule.

What the checker checks you do not check again (the verbatim excerpts, the provenance lines, the legends, the marks, the catalog's definition and usage units); your reading goes to the rules whose policy is manual, and `--prefix <id-prefix>` runs the checkers of one family again after a repair.

Reading aids that decide nothing: `KG_GLOSSARY_CHECKOUT/tools/qa/views.py <page> <view>` (regions, blocks, skim, openers, closers, post-fence, members, unreproduced, reshow, enumerations, claims, headings, figures, spine, writes --fields a,b); `KG_GLOSSARY_CHECKOUT/tools/writer/excerpt.py --tree <tree> path:A-B` prints a unit as the page must show it.

Print at most about 25 KB per command; read the page in subsection-sized slices; print a function by its range, never a whole file; never print the page, the brief or the rules twice.

## Severity

Severity, from what the reader loses, repaired in this order:

| severity | what the reader loses |
|---|---|
| 1 | the code or its explanation: an excerpt that differs from the tree, is cut inside a construct or skips lines; a cataloged symbol without its definition or usage excerpt; a fence no prose introduces or none explains; a figure the trigger table or the coverage rule owes and the page lacks; a legend site the page does not show; a lifecycle mark that is no write; a count or a claim the code beside it does not support; a campaign ban broken |
| 2 | the explanation's shape: purpose and model at the head of each subsection, transitions, the lead, SUMMARY and the route, the configuration overview and the section forms, figure geometry, vocabulary settled once |
| 3 | a surface detail: a span left bare or linked to the wrong line, a banned word, a hedge, a label colon, an em dash, a wrapped paragraph |

## Repair

A repair is a narrow edit on exact text; a changed excerpt comes from excerpt.py or a rebuild and is never typed; a new figure is drafted in a file and spliced with `tools/writer/figures.py insert`. After the repairs, re-read every changed passage with the paragraph before and after it, run the checker once more, and leave every violation at zero.

## Report

Report, as the structured output the prompt names: `changed` (rule, line, what), `clean` (what you read and found clean, one line per procedure step), `left` (rule, line, reason: what you read and did not repair, and why, a candidate your last checker run prints and the writer's report does not keep among them, since the finish step holds a page whose candidates nobody answers for), `qa`, `commands`, `notes`.
