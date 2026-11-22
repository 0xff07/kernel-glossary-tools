---
qa: manual
---

# When

An object is an instance class:

- a struct the page catalogs,
- a field of another page's struct that a function this page catalogs writes, or
- the file-scope variables of one mechanism the page catalogs, taken together.

An object has a lifecycle to draw when two or more functions write a field of it.

A struct the page catalogs is owed its figure; the other objects, a field of another page's struct, a mechanism's file-scope variables, another instance of a cataloged type, are the writer's call, drawn where the drawing teaches and otherwise left out, the paragraph beside the figure giving the reason, and nothing limits what else the writer draws.

The figure draws the writes made by the functions the page shows, the cataloged ones and the stage excerpts; a writer the page shows nowhere is named beside the figure with its reason and never a mark, so that drawing an object never forces an excerpt of another page's function.

The figure is the object lifecycle strip when the order of the events and the intervals in which the object is inconsistent are the point, the two-field state pair when the relation between two fields is the state, one figure per object or one strip with a bar per object for any number of objects whose writes are the same events; the allocation that zeroes an object and the free that ends it are writes through a call.

The writers of a member are every function that assigns it by the write forms described here, found over the whole tree with headers included; a catalog entry for a member (`struct tb_nhi *nhi`) names no object.

Place an object lifecycle strip in the DETAILS subsection that introduces its object, even on an object page. It must not appear under the lead or in SUMMARY, and drawing it does not fulfill the separate requirement for an overview figure there. Use a figure of the objects and their relationships or the primary journey for that overview. The conditions requiring a lifecycle strip still apply.


Find direct assignments, compound assignments and increments/decrements; also find writes through:

- swap,
- WRITE_ONCE,
- smp_store_release,
- exchange/compare-exchange helpers,
- memset/memcpy,
- bit operations,
- accessors and
- container calls.

Include allocation that zeroes the object and free that ends it. For a write through a call, retain the called helper or macro and its site. Check every writer of every drawn field among the functions the page shows, and name the writers it does not show beside the figure; distinguish other instances of the same type with a reason for leaving them out.

Trace through a call when its immediate line does not visibly name the field, one level into the called function and no further; a call's presence alone does not establish a write.
