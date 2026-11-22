---
qa: auto
---

# Enclosing

An excerpt says what it shows lines of. A unit that opens a construct begins at its opening line, the first line of the signature, the `struct foo {` line or the `#define`, or above it, at the kerneldoc, the plain comment or the preprocessor line standing over the construct, as long as the construct's opening line follows in the same unit.

A unit showing lines from inside a function without its signature is a later piece of a walkthrough and nothing else: a re-show and the stage of another page's function begin at the signature, fold what they skip, and end at the closing brace or where the stage ends. Every unit is introduced by the prose above the fence, which names and links its construct, and begins and ends on whole statements.

A member of a struct, union or enum, or an entry of a file-scope array or table, reproduced without the definition's opening line is indistinguishable from a local and fails, unless the unit is a later piece of a definition read in pieces, introduced by prose that names and links the definition; a definition is never thinned that way, and the pieces are held to the whole definition.

The check reads the constructs a unit touches, not where the unit begins: a macro touched without its opening line fails, and so does a struct, union, enum or file-scope variable touched without its opening line unless the prose above the fence links that definition, an unnamed struct or union inside it counting as part of the definition around it, which makes the unit a piece that the walkthrough check holds to the whole definition; a function's lines reproduced without its signature pass when the prose above the fence links the function or a location inside it, as a later piece or a re-show is introduced.

A unit that opens at the comment or the preprocessor line standing above its construct therefore passes as long as the construct's opening line follows in the same unit.
