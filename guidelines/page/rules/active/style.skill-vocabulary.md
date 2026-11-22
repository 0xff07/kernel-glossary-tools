---
qa: off
---

# Skill vocabulary

The page is written in the kernel's words and the reader's. The vocabulary used to talk about a page, how it was researched and how it is checked (a re-show, a stage excerpt, a walkthrough, the catalog, a census, a bare span, the trigger table, a figure family, the worksheet, the evidence sheet, section six, the skim) names nothing a kernel reader knows and never stands in the writer's words.

Say what the thing is instead: the lines shown again, the code below, the functions the page covers, the callers of the helper, the option the page assumes.

| Pattern | Kind | Scope | Unless | Exception |
|---|---|---|---|---|
| `\bre-?show(n\|s\|ing\|ed)?\b\|\bstage excerpts?\b\|\btrigger table\b\|\bfigure famil(y\|ies)\b\|\bbare spans?\b\|\bworksheets?\b\|\bevidence sheets?\b\|\bsection six\b\|\bthe skim\b` | violation | | | a verbatim quote |
| `\bcatalog(ue)?(s\|ed\|ing)?\b\|\bcensus(es)?\b\|\bwalk-?throughs?\b` | candidate | | | a verbatim quote; a catalog the kernel or a specification names in its own words (a firmware method catalog, a vendor's part catalog) |
| `\bbas(is\|es)\b\|\bwitness(es\|ed)?\b\|\bre-?deriv(e\|ed\|es\|ation)\b\|\bexcerpts?\b\|\bcampaigns?\b\|\bcompile database\b\|\bsymbol index\b\|\btags file\b\|\bresearch pack\b` | candidate | | | a verbatim quote; a basis the kernel names in its own words (a per-CPU basis) |
