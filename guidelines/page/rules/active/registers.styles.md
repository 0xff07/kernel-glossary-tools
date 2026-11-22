---
qa: manual
---

# Styles

Two styles, chosen by one test: is the thing one value, or several separate words? A register is one value at one address, however wide, and all its bits sit on one ruler; a structure is several words at successive DWORD offsets, each its own row. The DWORD-grid style writes field names inside cells and stacks `DW0`, `DW1`,... rows, for a structure or a register whose names fit.

The L-connector style, for registers only, draws one row of one-character cells and calls each named bit out below on an L-shaped leader when the register is mostly single-bit fields; a wide register whose upper bits are one uniform field may show only the interesting DWORD with a note.

The DWORD-grid style, a structure drawn as stacked DWORDs:

```
    bit    3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
           1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0 9 8 7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
    DW0   │       device_id (31:16)       │       vendor_id (15:0)        │
          ├───────────────┬─┬─────┬───────┴───┬───────────┬───────────────┤
    DW1   │   revision    │R│depth│ max_port  │ upstream  │  cap_offset   │
          │    (31:24)    │ │22:20│  (19:14)  │  (13:8)   │     (7:0)     │
          ├───────────────┴─┴─────┴───────────┴───────────┴───────────────┤
    DW2   │                       route_lo (31:0)                         │
          ├─┬─────────────────────────────────────────────────────────────┤
    DW3   │E│                      route_hi (30:0)                        │
          ├─┴─────────────┬───────────────┬───────────────┬───────────────┤
    DW4   │  tb_version   │   __unknown4  │     cmuv      │ plug_ev_delay │
          │    (31:24)    │    (23:16)    │    (15:8)     │     (7:0)     │
          └───────────────┴───────────────┴───────────────┴───────────────┘
```

The L-connector style, a register of single-bit fields:

```
    bit    7 6 5 4 3 2 1 0
          ┌─┬─┬─┬─┬─┬─┬─┬─┐
    DW0   │·│M│S│B│C│·│I│O│
          └─┴┬┴┬┴┬┴┬┴─┴┬┴┬┘
             │ │ │ │   │ │
    SMI_EVT ─┘ │ │ │   │ │
    SCI_EVT ───┘ │ │   │ │
      BURST ─────┘ │   │ │
        CMD ───────┘   │ │
        IBF ───────────┘ │
        OBF ─────────────┘

    OBF = ACPI_EC_FLAG_OBF (0x01)      IBF = ACPI_EC_FLAG_IBF (0x02)
    CMD = ACPI_EC_FLAG_CMD (0x08)      BURST = ACPI_EC_FLAG_BURST (0x10)
    SCI_EVT = ACPI_EC_FLAG_SCI (0x20)  SMI_EVT = 0x40 (firmware, no macro)
    bits 2 and 7 reserved (read 0)
```

This rule applies to a figure whose primary subject is a register, TRB, context, descriptor or packet-header bit layout, a flag word of several bit fields or flag bits, or a pointer or word whose low or high bits carry a tag. A bit strip inside a larger structural figure follows the host figure's style.

Choose DWORD-grid with names inside cells for a multiword structure or a register whose labels fit; choose one row with L-shaped callouts for a register made mostly of single-bit fields. A register is one value at one address, however wide; a structure has successive DWORD rows.
