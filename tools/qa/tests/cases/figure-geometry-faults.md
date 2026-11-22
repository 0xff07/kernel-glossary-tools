# Fixture port

> CAUTION: AI-GENERATED CONTENT
>
> STRICTLY DO NOT SUBMIT THIS UPSTREAM UNLESS YOU ARE AN EXPERT INTIMATELY FAMILIAR WITH THIS SUBSYSTEM.

A port is one end of a link, and the kernel keeps one record per port so that the low-power states a link runs in are known at both ends. The record decides whether a link may drop into a CL state and which end programs the adapter. A state is enabled for the whole link, so the two records are written together under one lock. This page traces how a mask of states is validated, written to both adapters, recorded and cleared again.


## DETAILS

These figures exercise display-cell geometry.

### Missing downward join

The bar cannot end a trunk that continues below.

```
    ─┴─
     │
     ▼
```

### Missing side exit

The source wall lacks the right-facing port.

```
    ┌───┐
    │ A │──▶
    └───┘
```

### Dashed connector elbow

A dashed connector still needs reciprocal ports at its turn.

```
    ┆
    ┌──▶
```

### Wrong elbow

The lower corner lacks the upward port from the preceding row.

```
    ──┐
      ┌──▶
```

### One-cell shift

The lower shaft has moved one display cell.

```
    ┬
     │
     ▼
```

### Two-cell heavy shift

The lower heavy shaft has moved two display cells.

```
    ┳
      ┃
      ▼
```

### Double-line missing join

A double-line trunk continues below an up-only junction.

```
    ═╩═
     ║
     ▼
```

### Reversed head

The shaft meets only the tip side of this head.

```
    ▶──
```

### Changed box width

The side and bottom are one cell wider than the top.

```
    ┌───┐
    │x   │
    └────┘
```

### Absent box wall

One interior row has no glyph in its planned right column.

```
    ┌───┐
    │   │
    │ A  
    └───┘
```

### Floating double run

Two unattached glyphs form one vertical run.

```
    ║
    ║
```

### Floating heavy run

One unattached heavy glyph is also a run.

```
    ┃
```

### Framed span is a trunk

The partition tick inside a surrounding frame retains its ports.

```
    ┌──┬──┐
    │  │  │
    │ ─┴─ │
    │  │  │
    └──┴──┘
```

<!-- kg:expect
only:
- geometry.layout
findings:
- - geometry.layout
  - review
  - 19
  - ─┴─
- - geometry.layout
  - review
  - 30
  - │ A │──▶
- - geometry.layout
  - review
  - 40
  - ┌──▶
- - geometry.layout
  - review
  - 49
  - ┌──▶
- - geometry.layout
  - review
  - 58
  - │
- - geometry.layout
  - review
  - 68
  - ┃
- - geometry.layout
  - review
  - 77
  - ═╩═
- - geometry.layout
  - review
  - 87
  - ▶──
- - geometry.layout
  - review
  - 96
  - │x   │
- - geometry.layout
  - review
  - 97
  - └────┘
- - geometry.layout
  - review
  - 107
  - │ A
- - geometry.layout
  - review
  - 116
  - ║
- - geometry.layout
  - review
  - 125
  - ┃
- - geometry.layout
  - review
  - 135
  - │ ─┴─ │
incomplete: []
-->
