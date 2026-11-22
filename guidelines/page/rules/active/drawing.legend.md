---
qa: auto
---

# Legend

A figure names functions through marks and a legend inside the same fence below the drawing. Use one of ①–⑩, ➊–➓, «1» onward, «A»–«Z», @1 onward or @A–@Z. Each entry names the complete mark, function, source site and a phrase of at least three words explaining what the site does or decides. Draw objects, fields, events and values; a one-word verb may sit beside a mark. Every drawn mark has an entry even if it is the figure's only mark. On a lifecycle figure, name the field set.

Every legend phrase has at least three words. Resolve a basename only when it identifies one cited file; otherwise use the path from the source-tree root. A drawn mark without a legend entry, an undrawn legend entry, an unshown site or a site outside its named writer fails. Keep the legend inside the same fence below the drawing.


Use `① name file:line  phrase`, optionally `name()`. An entry may inherit the previous entry's file as `① name :75  phrase`; require that previous file to exist. Use the root-relative path when two cited files share a basename. A decimal mark has no leading zero, capital families have capacity 26 and circled families capacity ten. Match the whole mark token, so @1 does not match @10 or an email address.

A legend entry is a line of the figure fence of the shape `<mark> <name>[()] [<file>]:<line> <phrase>`:

- the mark is the line's first token and begins with no box-drawing character;
- the name is a C identifier, with or without `()`;
- the file is a path ending in a source suffix of the profile, or is left out to inherit the previous entry's file;
- the line is digits;
- the phrase is the rest of the line.

Any other line of the fence is a drawing line, and every mark-like token on a drawing line is a drawn mark. Marks are read as complete marks, so two written back to back (`«1»«2»`) are neither drawn marks nor entries: separate them with a space.

With the tree, each entry's file is resolved against the files the page cites, by its path or by a base name that one cited file carries, and its line must be reproduced by an excerpt and lie inside the function the entry names; the SUMMARY model figure's legend is read the same way.
