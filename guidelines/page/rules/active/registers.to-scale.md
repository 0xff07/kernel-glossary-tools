---
qa: manual
---

# To scale

Draw to scale by default, with a complete ruler and exact `(hi:lo)` ranges. Draw schematic only where a boundary has no fixed number (a field that ends at MAXPHYADDR, a generic pattern): name the variable boundary `N` or `M`, join the gaps with `...`, and size cells for their labels. Exact positions on a generic pattern are fake precision. Every range, constant and macro in the figure and its legend is a behavioral claim, verified against the reproduced definition.

Schematic where the boundary varies, the x86-64 page-table entry: `M` is named, the cells are sized for their labels, and the legend says what moves with `M`:

```
    x86-64 4-KByte-page table entry (PTE)
    ─────────────────────────────────────────
    (schematic; M = MAXPHYADDR, the boundary varies by CPU)

     63   62           52 51          M M-1              12 11          0
    ┌────┬───────────────┬─────────────┬───────────────────┬─────────────┐
    │ XD │  ignored/MPK  │  reserved   │ physical address  │    flags    │
    │(63)│    (62:52)    │  (51:M, 0)  │     (M-1:12)      │   (11:0)    │
    └────┴───────────────┴─────────────┴───────────────────┴─────────────┘

    M = MAXPHYADDR (physical-address width: 36, 39, 46, or 52)
    flags (8:0): P(0) R/W(1) U/S(2) PWT(3) PCD(4) A(5) D(6) PAT(7) G(8)
    available (11:9): AVL;  reserved bits (51:M) are 0
    the address field high bit moves with M
```

This rule applies to a figure whose primary subject is a register, TRB, context, descriptor or packet-header bit layout, a flag word of several bit fields or flag bits, or a pointer or word whose low or high bits carry a tag. A bit strip inside a larger structural figure follows the host figure's style.

Choose DWORD-grid with names inside cells for a multiword structure or a register whose labels fit; choose one row with L-shaped callouts for a register made mostly of single-bit fields. A register is one value at one address, however wide; a structure has successive DWORD rows.
