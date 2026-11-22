# Kconfig overview

DETAILS opens, after its route paragraph, with the subsection `### Kconfig assumptions`, the one DETAILS heading that is fixed text and no clause: an index of the configuration the page documents, so that a reader can see the assumptions in one place, and no more than an index, since each assumption is stated where it bites and the subsection is not required reading.

It holds, in this order, a paragraph naming the configuration and its origin (the Ubuntu generic amd64 configuration for 7.3, the x86_64 defconfig resolved at the pinned commit) and the architecture; a table with one row per option the prose names, the option linked to its `config` line, the value the page assumes and a phrase for what it decides on the page's paths; and a closing paragraph saying that the table indexes the prose, where the effect of an option is stated at the point it applies.

An option the named configuration leaves unset and one part of the page assumes set, as the option that builds a test the page covers, takes a row that gives both values, the configuration's and the one that part assumes, and the paragraph names that part.

The table lists the options the prose names and no other, so it is derived from the prose and never a source of facts; the subsection carries no excerpt, no figure, no list and no option the page never uses.

The subsection is the one place a page states its configuration as a whole. The DETAILS preamble holds the route paragraph alone, with no paragraph on the configuration; the route paragraph names the subsections that follow the overview and leaves the overview out; the lead, SUMMARY and the catalog sections name no configuration beyond the architecture.
