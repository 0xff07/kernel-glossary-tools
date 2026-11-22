---
qa: manual
---

# Whole definitions

Reproduce a definition whole, including comments and conditional compilation, never thinned to the members the prose explains. A definition within the excerpt target is one excerpt.

A definition past the target that the page is about, whose members it explains by group, a struct, union or enum or a file-scope array or table whose entries are the members, is read in consecutive pieces like a long function:

- an outline table before the first piece names each piece's mark, lines and member group;
- each piece stands between a paragraph that says what its run of members is for, carrying the piece's mark and naming the definition as a link, and a paragraph that explains the members shown;
- the pieces follow declaration order, each beginning at the line after the previous one ended, and together reproduce the definition from its opening line to its closing line, every line once and nothing folded;
- a cut falls only between members, never inside a preprocessor block or a comment;
- and every piece stands in the subsection that reads the definition, a later subsection linking the members it reasons about rather than showing them again.

A definition past the target that the page shows for one run of members, whose other members it never mentions, may instead stay one excerpt that drops that one unmentioned run with a counted elision named in prose. Explain every member shown, individually or as a justified group; a member table beside a single excerpt can carry the detail.

The source-excerpt target is 6–40 reproduced lines. Past it, choose the pieces when the page explains the definition's members by group, and the one counted elision only for a run the page never mentions; in both forms the definition stands in one place of the page, with its comments and conditional compilation.
