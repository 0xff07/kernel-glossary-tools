---
qa: manual
---

# Scripts and tools

A page lists the scripts and tools the tree carries for its subject: a file under `scripts/` or `tools/` that reads, decodes, drives, checks or generates something of the mechanism the page walks.

A debugger helper that knows the subject's structs, a decoder of its dumps or traces, a user-space program that drives its ioctls or reads its files, a semantic patch or checker that knows its API, a generator of its code or tables: each is one. A test is none, and follows the walk of the code it exercises; a header copied for user-space builds is none either.

The list stands beside the page's observability lists, one item per script or tool: the file linked, what it does with the subject in one sentence that names the file, the ioctl, the tracepoint, the struct or the symbol of the subject it knows, and how it is invoked where the tree's documentation or the tool's own usage text says so.

A tool whose working explains the mechanism, a decoder that mirrors a struct's layout or a helper that walks the same list, is also named at the walk of what it mirrors.

The page lists the scripts and tools its request names and those it finds naming its subject, and states no absence of them.
