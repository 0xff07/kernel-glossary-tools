---
qa: manual
---

# Figure

The drawing carries the events as columns or the states as boxes, the fields and the values they take, and a mark at every write, a write through a call included (a `swap`, a store macro, a bit operation, an accessor, a container function), whose legend entry names the call where the line carries no recognized write form; the legend beneath names the writer and its site; every writer of a drawn field among the functions the page shows appears, and the writers the page does not show are named in the paragraph after the figure, each with its file and the reason it is left out, so that a writer left out is an omission the reader can see and not a state the code can reach unnoticed.

Find direct assignments, compound assignments and increments/decrements; also find writes through:

- swap,
- WRITE_ONCE,
- smp_store_release,
- exchange/compare-exchange helpers,
- memset/memcpy,
- bit operations,
- accessors and
- container calls.

Include allocation that zeroes the object and free that ends it. For a write through a call, the legend entry names the called helper or macro beside its site. Check every writer of every drawn field among the functions the page shows, and name beside the figure the writers it does not show; distinguish other instances of the same type with a reason for leaving them out.

Trace through a call when its immediate line does not visibly name the field, one level into the called function and no further; a call's presence alone does not establish a write.

To check, read every mark of the figure against the tree: its site is one line of a cited file, inside the writer the legend names, and that line writes a drawn field by an assignment, a compound assignment, an increment or decrement, or a call on the line of `swap`, `WRITE_ONCE`, `smp_store_release`, `xchg`, `cmpxchg`, `try_cmpxchg` (their `64`, `_relaxed`, `_acquire` and `_release` forms included), `memset`, `memcpy`, `set_bit`, `clear_bit`, `change_bit`, `assign_bit`, the `__` forms of those four and the `test_and_` forms of the first three, with the field among its arguments, or through the call the entry names; an entry whose line writes no drawn field, or lies outside its writer, fails.

A figure with a legend whose marks are no writes is no lifecycle figure and is read under the legend rule alone.
