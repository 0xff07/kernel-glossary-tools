---
qa: off
---

# Always linked

Always linked:

- `CONFIG_*` options to the `config X` line of the declaring Kconfig file;
- a field path `a->b` or `foo.bar` to the field's declaration line;
- a struct, union or enum member named by a bare span, `bus_list` or `node`, to its declaration line in the type that holds it, at its first occurrence in each paragraph, table cell or list item, so that the link says which object the member belongs to when several types carry a member of that name;
- an ops-struct member named in prose to its line in the struct.

A local variable, a parameter or a goto label quoted from an excerpt stays bare, and a name that is both a member of a cited type and a local of the shown function is linked as the member where the sentence means the member and left bare where it means the local, the sentence saying so.

A generic kernel primitive (`READ_ONCE()`, `memcpy()`, `rcu_read_lock()`, `atomic_read()`, an errno value) and any other symbol no cited file defines may stay bare, and linking one is the writer's choice. Precedent never excuses a bare span of the linked classes, and pre-existing bare spans of the same family are fixed in the same pass.
