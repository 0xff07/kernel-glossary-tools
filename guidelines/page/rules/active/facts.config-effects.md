# Config effects

Where a path, a member, a constant or a branch the page explains depends on a Kconfig option, the prose names the option where the dependence bites and says what it does there: which branch is compiled, which value a constant takes, which symbol the option selects, and what the other value of the option does at that point, in the same sentence or the one after it.

"With `CONFIG_X86_5LEVEL` set and five-level paging enabled at boot, `PGDIR_SHIFT` is 48; without it the P4D level folds and the shift is 39." "Assuming `CONFIG_MEMCG` is enabled, `memcg_data` is a member of the folio; a kernel built without it has no such word, and `folio_memcg()` returns NULL."

A name of the build stands in for no option: "the documented build", "the compile database's build", "the default build", "this configuration" and their like name nothing the reader can look up, and send the reader back to the overview to learn what was meant; the sentence names the option and the value it assumes instead.

The assumptions are therefore stated where they matter, and a reader who skips the Kconfig overview still meets every one of them in the prose, since the overview indexes the prose and the prose never defers to it.

An option that changes nothing on the page's paths is not named; a page-wide assumption, the architecture or the memory model, is stated at its first effect and again wherever a later claim rests on it in a way the reader would not expect.
