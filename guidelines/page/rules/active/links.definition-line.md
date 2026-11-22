---
qa: off
---

# Definition line

Link every kernel symbol outside fences at its first occurrence in each paragraph, table cell or list item to its definition line at the documented version. Later occurrences in the same paragraph or cell may remain bare. Retain struct/enum keywords. Use the definition's kind and declaring line, including the first line of a split function signature, a member's declaration and macro-defined declarations/functions.

A call site, branch or assignment is a location link covering the source run it describes, anchored at its first line.

A function span in a sentence that explains particular lines of the function links to the first of those lines rather than to the signature, a line an excerpt beside the sentence reproduces, so that the link lands on the code the sentence is about; the definition line is the link where the sentence introduces the function, names its role or speaks of it as a whole.

A function link never lands on a call or prototype, except a function declared by another subsystem whose tree has no C definition because a macro generates it or it is written in assembly. Use one base throughout: `https://elixir.bootlin.com/linux/{version}/source/{path}#L{line}`. A tagged link `struct X`, `enum X` or `union X` links a definition of that tag, not a same-named object.

Confirm the file exists and every linked line/range is within it.

- A location link's first stated line equals its URL anchor.
- A CONFIG link lands on the option's `config` or `menuconfig` declaration.
- A function link lands on the function's definition line or on a line inside its body; a body line no excerpt on the page reproduces is a candidate, resolved by linking the definition line or showing the lines the sentence explains.
- A split function signature starts on the preceding return-type line only when that line has no semicolon and is outside another construct.
- A macro-declared symbol may land on its file-scope invocation spelling the symbol, never on a call inside a function; a tagged symbol cannot use this fallback.
- For a macro-defined function such as `DEFINE_IDTENTRY_ERRORCODE(exc_general_protection)`, the declaring invocation may be linked by the function name, macro name or whole invocation.
- A member key `A.B` lands on B within A, including a declaration by a macro such as `DECLARE_BITMAP(bits, 64)` inside A.
- A symbol the tree defines only through a macro, so that no definition line carries its name, may link its prototype, and the sentence that first names it says which macro generates it; a link landing on a prototype is a candidate, cleared by that sentence.
- A type the tree declares and never defines, an incomplete type whose pointers the code passes only through helpers (`struct encoded_page;`), links its declaration line, the only line that carries its name, a bare `struct`, `union` or `enum` declaration of that name, and the prose names it as a type the tree declares and never defines.

A C identifier written as plain text in a prose line, outside code spans, links, quoted runs, location forms and a cited commit subject, that holds `_`, ends in `()` or names a CONFIG option, with no linked occurrence of the same name earlier in its paragraph, is a candidate: link it, or write it as a span that a licence for a bare span covers.

A link is read as a CONFIG link only when its text matches the profile's `config_option` (`CONFIG_X`); an option written without the prefix is a symbol link, which must land on a definition line of that name, and the `config X` line of a Kconfig file is none. Write the option as `CONFIG_X` to link the declaration.
