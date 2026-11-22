---
qa: off
---

# Coverage form

COVERAGE catalogs the symbols selected for this page and excerpted, under third-level labels, one entry per symbol. Symbols outside this catalog are normally left to another article, but may include them when the local explanation benefits, using judgment even when another page is assigned or already catalogs them.

An assignment identifies the intended primary page; cataloging the symbol here adds coverage without transferring that assignment. Duplicate catalog coverage across pages is allowed. Merely mentioning or linking a symbol does not require a catalog entry, and a symbol that will not be excerpted is a linked prose mention. An entry that traces uses the traced form; others use the bare form.

Macros, members, indented enumerators and symbols first named earlier by a forward declaration, prototype or same-named construct take bare entries. Members may be cataloged on multiple pages without designating a primary page.


A **catalog entry** is a COVERAGE line of one of two forms,

```
- [`'\<KEY\>':'PATH'`](URL): role
- [`'KEY'`](URL): role
```

with `KEY` the symbol as prose names it (`struct tb_switch`, `tb_port_enable`, `TB_CFG_PORT`), `PATH` its defining file and `URL` a cited URL with a line `L`. The first is the **traced form**, whose text is the argument of `git log -L:'\<KEY\>':'PATH'`, and the second the **bare form**, whose file is the URL's.

The entry's **name** is the symbol name of `KEY` : `tb_switch` for `struct tb_switch`, `tb_port_enable` for `tb_port_enable()`. A **member entry** is a bare entry whose `KEY` is `A.B`, with `B` a member of the struct or union `A` (`tb_cm.hotplug_active`), a member of an unnamed struct or union counting as a member of the struct or union around it, and its name is the key itself.

A key of two or more words with no `(`, other than `struct X`, `enum X` or `union X`, is a declaration such as `bool hotplug_active` and malformed, and so is a traced key `A.B`. The catalog's **keys** and **names** are its entries', in page order, each once.

An entry's **trace** is the line of its file where `git log -L:'\<T\>':'<file>'` starts, `T` being `KEY` when it is `struct X`, `enum X` or `union X` and the entry's name otherwise: the first line that begins with an ASCII letter or `_` and holds `T` as a whole word, whose number `grep -n '^[A-Za-z_]' <file> | grep -m1 '\<T\>'` prints, which is where git's `-L :<funcname>` search stops under the `cpp` diff driver the kernel sets for `*.[ch]` and under the default one.

An entry **traces** when its trace is `L`, or the line after `L` when `L` is the first line of a function signature whose name stands on the next line, and a member entry never does.

- A macro never traces, its line beginning with `#`,
- nor does an enumerator on an indented line,
- nor a symbol its file names first on another line: a forward declaration, a prototype, a struct of the same name.

A name a header declares by prototype and each implementation defines by a `#define` is anchored at one of those `#define` lines, a bare entry whose file is that implementation's, the prose saying which implementation the page chose.

Use `https://elixir.bootlin.com/linux/{version}/source/{path}#L{line}` at the documented version. Tagged keys retain struct/enum/union. Reject a declaration such as `bool field` or a traced member key. A prototype in a header with architecture implementations supplied by `#define` is linked to the chosen implementation's macro line with a bare key; state the implementation choice in prose.
