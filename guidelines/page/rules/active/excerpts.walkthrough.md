---
qa: auto
---

# Walkthrough

The reader of a page has read its code.

Every function in this page's catalog is read whole, including one assigned to another page: within the local walkthrough target as one excerpt, a longer one in consecutive pieces cut at its stage boundaries, each piece beginning at the line after the previous one ended and introduced by a sentence naming the function, the stage and the piece's number from its outline, so that the pieces in page order are the function from its signature to its closing brace.

An excerpt is what a reader sees who opens the file at that place and reads down:

- it begins where the thing begins, at a function's signature or a definition's opening line;
- a cataloged function ends where it ends, at the closing brace, while a stage excerpt of any other function may stop after the last line of the stage it shows, with no elision line after it;
- a stretch the page is not about between the lines shown is folded with an elision line, never silently skipped, and
- an elision begun inside a function resumes inside it.

A fence that shows more than one function shows each of them that way. A cataloged function is read whole, in consecutive pieces that continue one another.

A struct, union, enum or file-scope variable definition (a table or an array initializer) the page reads in pieces is held to the same contract: its pieces in page order reproduce the definition from its opening line to its closing line, each line once, with no elision inside a piece and every piece in the subsection that reads the definition, and no unit shows lines of that definition again, since a later paragraph links the members it reasons about.

Use one excerpt for a cataloged function of about 40 lines or fewer, and consecutive stage-boundary pieces for longer functions, without elision. Other functions and re-shown code start at the signature, fold irrelevant stretches with counted elisions, and end at the closing brace or after the last line of their stage. Do not silently skip source lines between the lines an excerpt shows.

The pieces of a cataloged function are read from the page's units of the function's file in page order: a unit is a piece when it reproduces at least one function line that no earlier unit showed and none of its counted elisions begins inside the function, so a unit that folds part of the function is a stage excerpt or a re-show and no piece, and a unit all of whose function lines earlier units showed is a re-show.

The pieces must together reproduce every line from the signature to the closing brace, the first missing line being named; a piece that shows lines before the previous piece's is a candidate, and lines reproduced more than once are measured.

A definition is read in pieces when a unit shows lines of it without its opening line, an unnamed union or struct counting as part of the definition around it; its pieces are read like a function's, the first missing line named, a unit of the definition that is no piece (a re-show or a folded copy) a violation, and a piece in another subsection than the first a violation.
