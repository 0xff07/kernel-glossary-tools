---
qa: manual
---

# Scope

Determine a figure's primary subject before choosing a bit-layout style.

A register, TRB, context, descriptor or packet-header layout uses the register styles and rulers, and so do a flag word assembled from several bit fields or flag bits (a `vm_fault_t`, a GFP mask) and a pointer or word whose low or high bits carry a tag (`folio->mapping` under its flag mask): each is one value on one ruler, held by a variable or a member instead of an address.

A small bit strip embedded in a larger structural figure follows that host figure's style instead. A register is one value at one address; a multiword structure occupies successive DWORD rows.

A flag word drawn as a register, the L-connector style with the callouts to the right, each `NAME = MACRO (value)`:

```
    vm_fault_t: the flags a fault handler returns, one value on one ruler
    ─────────────────────────────────────────────────────────────────────
    (bits 31:20 are unused; the type is an unsigned int)

    bit    1 1 1 1 1 1 1 1 1 1
           9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
          │ HINDEX│·│C│N│D│F│R│K│P│·│S│G│H│·│M│B│O│
          └───┬───┴─┴┬┴┬┴┬┴┬┴┬┴┬┴┬┴─┴┬┴┬┴┬┴─┴┬┴┬┴┬┘
              │      │ │ │ │ │ │ │   │ │ │   │ │ │
              │      │ │ │ │ │ │ │   │ │ │   │ │ └── O = VM_FAULT_OOM (0x1)
              │      │ │ │ │ │ │ │   │ │ │   │ └──── B = VM_FAULT_SIGBUS (0x2)
              │      │ │ │ │ │ │ │   │ │ │   └────── M = VM_FAULT_MAJOR (0x4)
              │      │ │ │ │ │ │ │   │ │ └────────── H = VM_FAULT_HWPOISON (0x10)
              │      │ │ │ │ │ │ │   │ └──────────── G = VM_FAULT_HWPOISON_LARGE (0x20)
              │      │ │ │ │ │ │ │   └────────────── S = VM_FAULT_SIGSEGV (0x40)
              │      │ │ │ │ │ │ └────────────────── P = VM_FAULT_NOPAGE (0x100)
              │      │ │ │ │ │ └──────────────────── K = VM_FAULT_LOCKED (0x200)
              │      │ │ │ │ └────────────────────── R = VM_FAULT_RETRY (0x400)
              │      │ │ │ └──────────────────────── F = VM_FAULT_FALLBACK (0x800)
              │      │ │ └────────────────────────── D = VM_FAULT_DONE_COW (0x1000)
              │      │ └──────────────────────────── N = VM_FAULT_NEEDDSYNC (0x2000)
              │      └────────────────────────────── C = VM_FAULT_COMPLETED (0x4000)
              └───────────────────────────────────── HINDEX = VM_FAULT_HINDEX_MASK (0x0f0000), bits 19:16

    VM_FAULT_ERROR = OOM | SIGBUS | SIGSEGV | HWPOISON | HWPOISON_LARGE | FALLBACK (the errors a caller tests at once)
    bits 3, 7 and 15 unused (read 0)
```

A pointer whose low bits carry a tag, drawn as a register in the DWORD-grid style, schematic over the address bits:

```
    folio->mapping: an address whose low two bits are flags
    ───────────────────────────────────────────────────────
    (schematic; the pointee is 4-byte aligned, so bits 1:0 carry no address)

     63                                               2       1            0
    ┌──────────────────────────────────────────────────┬────────────┬────────────┐
    │   struct address_space * or struct anon_vma *    │  ANON_KSM  │    ANON    │
    │                      (63:2)                      │    (1)     │    (0)     │
    └──────────────────────────────────────────────────┴────────────┴────────────┘

    ANON = FOLIO_MAPPING_ANON (0x1): set, the address is a struct anon_vma *
    ANON_KSM = FOLIO_MAPPING_ANON_KSM (0x2): with ANON, a KSM stable node
    FOLIO_MAPPING_FLAGS = ANON | ANON_KSM: the mask that separates the tag bits from the address
```
