---
qa: manual
---

# Introduced

The prose above a fence, back to the previous heading, figure, table, list or excerpt, introduces the excerpt before the reader meets its code. It names the construct the excerpt shows, or the function a body fragment belongs to, as a link to its definition line; says what the construct is and what role it plays in the explanation where the page has not established that yet; and says what the excerpt is for, the question its lines answer or the relationship they establish, so that the reader knows what to look for before reading them.

What a construct is comes before its code, never after it: an excerpt whose construct the page introduces for the first time below the fence, or whose purpose the reader learns only from the prose after it, fails this rule, and the prose after the fence explains what the lines established without introducing them.

A mention in a heading, a table cell, the provenance comment or a location link does not count; a mention above a previous heading, figure, table, list or excerpt does not carry. A unit that is a comment alone, or top-level lines that start no construct, shows no construct; a location link into its lines introduces it.

A registration macro's unit, `DEBUGFS_ATTR_RO(x);` or `rootfs_initcall(x);`, is named by its argument, and a linked symbol built on that stem introduces it. A unit of a file that is not C, a Kconfig or a Makefile, shows no C construct; a link to the file, to the option a `config` line among its lines declares, or to a location in its lines introduces it.

Read the prose above every fence for its three parts, the construct named and linked, its role where new, and the purpose of the excerpt; an introduction that only announces the code ("the definition follows", "the function is shown below") supplies the name and not the purpose.
