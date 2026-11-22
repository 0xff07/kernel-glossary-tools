---
qa: off
---

# Bare spans

Left bare, in prose and table cells alike:

- a symbol linked earlier in the same paragraph; C keywords and operators; locals, parameters and goto labels quoted from an excerpt, which no cited file declares;
- literal and error values (`true`, `false`, `0`, `-EINVAL`, `NULL` as a value); literal strings a function prints or logs; a value or expression span, which links a constituent symbol where one exists;
- `/proc`, `/sys`, sysctl and other path strings; Kconfig fragments and keywords (`=y`); tracepoint field names; `name(2)` notation when the entry point is linked elsewhere;
- a wildcard family name (`VM_*`) when its members are linked nearby; a designated initializer's member name, whose citation is a location link at the initializer line; a symbol verified absent from the tree, whose absence the prose states;
- a spec-defined or hardware name (`_PS0`, `SLP_EN`), which stays bare with a note saying so;
- a generic kernel primitive or any other symbol that no cited source file defines (`READ_ONCE()`, `memcpy()`, a helper of another subsystem named at a seam), whether or not an excerpt spells it, which the page links or leaves bare.

A struct, union or enum member a cited file declares is never left bare where the sentence means the member: it links to its declaration line in the type that holds it, the link saying which type that is; a span that means a local or a parameter of the shown function, though a cited type declares a member of that name, stays bare, and the sentence says which function's local it is.

Any other bare span is linked, a span in the descriptive text of a catalog bullet included: only the entry's own linked symbol belongs to the catalog, and the rest of the bullet is closed like prose.

Every bare occurrence of a span, descriptive text in a COVERAGE bullet included, is licensed in one of two ways, and one with none is a violation:

1. a linked occurrence of the same text earlier in the same paragraph;
2. a settled class the checker recognizes:
   - by the text alone, an error value `-E…`, a literal number, `true`, `false` or `NULL`, a commit hash, a C keyword excerpt, a path string, a string or character literal, an expression with an operator, a boot parameter or Kconfig fragment such as `pcie_aspm=` or `=y`, `name(2)` notation, a wildcard family `X_*`, a tracepoint name `subsystem:event`, a designated initializer's member `.name`, a text with spaces that is no tagged type (a printed string or a fragment), or any text holding no identifier with an underscore (a local, a fragment, a mark, a literal); or,
   - with the tree's facts, an identifier that no cited source file declares (a local, parameter or goto label quoted from an excerpt, a generic primitive, a symbol of another subsystem), while an identifier a cited source file defines as a function, struct, union, enum, typedef, variable, macro, prototype or enumerator, or declares as a member of a struct, union or enum, is a symbol and links, a member to its declaration line in the type that holds it, while a member whose name a shown function also uses as a local or a parameter is a candidate, read for which of the two the sentence means.

A bare span is read per occurrence: the same text bare again in a later paragraph needs its own licence, a linked occurrence earlier in that paragraph or a settled class.
