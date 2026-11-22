# Pattern: radix walk

1. Use when a key, an address, an ID or a handle, is split into index fields that select an entry level by level, each entry holding the next level's table or the leaf: a CPU or IOMMU page table, a device table reached through a requester ID, a PASID directory and table, a radix tree or XArray, an interrupt remapping table indexed in two steps.
   - The point is which bits of the key select which table, how many levels the walk takes and where a leaf or an empty entry ends it, which is why a sentence that names the levels does not replace the drawing.
2. Draw the key at the top as one row of cells, one per field, high bits on the left, each cell naming the bit range and the index it yields for the worked example, the lowest field being the offset inside the leaf.
   - Under each field, through a `┬` tick and a `▼`, draw the table that field indexes as a column of entries, the table's name on its first row and the index of each shown entry at the left of its cell; mark the entry the example selects, and let it exit the right wall through `├─▶` into the next table, the last into the leaf.
   - Show the empty entries and the leaf entries the format allows at each level, with `·` rows standing for the entries left out, and give every table its full index range.
3. The shape asserts the mapping of key bits onto levels by position, the chain of tables by the arrows, and the depth of the walk by the number of columns: a reader counts the levels, reads which bits each consumes and sees where the walk can stop early. Keep the bit ranges, the entry counts and the level names exact; the entry chosen is the example's and is marked, the legend naming the function that reads or writes it and its site.
4. Distinct from the sparse slot map, which is one level of slots with or without backing; from parent and children fan-out, whose children are not indexed by a key; and from linked structs via field-level pointers, where the pointers are fields and not entries a key selects.

```
    One key through a three-level radix table, nine index bits per level
    ─────────────────────────────────────────────────────────────────────

    key    ┌────────────────┬────────────────┬────────────────┬────────────────┐
           │ bits 38:30     │ bits 29:21     │ bits 20:12     │ bits 11:0      │
           │ L2 index = 1   │ L1 index = 7   │ L0 index = 3   │ offset = 2051  │
           └───────┬────────┴───────┬────────┴───────┬────────┴───────┬────────┘
                   │                │                │                │
                   ▼                ▼                ▼                ▼
            ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
            │ L2 (root)   │  │ L1          │  │ L0          │  │ 4 KiB page  │
            ├─────────────┤  ├─────────────┤  ├─────────────┤  ├─────────────┤
            │ 0   empty   │  │ 0   empty   │  │ 0   leaf    │  │ byte 0      │
            ├─────────────┤  ├─────────────┤  ├─────────────┤  │             │
            │ 1  table «1»├─▶│ 1   empty   │  │ 1   empty   │  │             │
            ├─────────────┤  ├─────────────┤  ├─────────────┤  │             │
            │ ·   ·       │  │ ·   ·       │  │ 3  leaf «3» ├─▶│ byte 2051   │
            ├─────────────┤  ├─────────────┤  ├─────────────┤  │             │
            │ 511 empty   │  │ 7  table «2»├─▶│ ·   ·       │  │             │
            └─────────────┘  ├─────────────┤  ├─────────────┤  │             │
                             │ ·   ·       │  │ 511 empty   │  │ byte 4095   │
                             ├─────────────┤  └─────────────┘  └─────────────┘
                             │ 511 empty   │
                             └─────────────┘

    «1» x86_64_pt_load_entry_raw x86_64.h:110  reads the L2 entry the first field selects
    «2» x86_64_pt_table_pa :76  decodes the L1 entry into the L0 table's address
    «3» x86_64_pt_entry_oa :87  decodes the leaf into the page's output address
```
