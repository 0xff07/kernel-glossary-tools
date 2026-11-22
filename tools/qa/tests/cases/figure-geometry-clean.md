# Fixture port

> CAUTION: AI-GENERATED CONTENT
>
> STRICTLY DO NOT SUBMIT THIS UPSTREAM UNLESS YOU ARE AN EXPERT INTIMATELY FAMILIAR WITH THIS SUBSYSTEM.

A port is one end of a link, and the kernel keeps one record per port so that the low-power states a link runs in are known at both ends. The record decides whether a link may drop into a CL state and which end programs the adapter. A state is enabled for the whole link, so the two records are written together under one lock. This page traces how a mask of states is validated, written to both adapters, recorded and cleared again.


## DETAILS

These figures exercise display-cell geometry.

### Reciprocal branches

Every turn and attachment carries its actual ports.

```
    ┌──┬──┐
    │  │  ├──▶
    └──┼──┘
       │
       ▼
```

### Independent boxes

Separate boxes use different bounds; trailing annotations are outside them.

```
    ┌───┐       ┌──────┐
    │ A │ note  │ B    │
    └───┘       └──────┘
```

### Rounded and mixed borders

Rounded, heavy and mixed single/double glyphs carry the same directions.

```
    ╭───╮   ┏━━━┓   ╔══╤══╗
    │ A │   ┃ B ┃   ║  │  ║
    ╰───╯   ┗━━━┛   ╚══╧══╝
```

### Merged frame bottom

An inner frame ends at junctions on a shared border before the next box.

```
    ┌─────────┐
    │ ┌───┐   │
    │ │ A │   │
    └─┴───┴───┘

      ┌───┐
      │ B │
      └───┘
```

### Arrow reaches a wall

No fixed gap or mandatory arrow label is required.

```
        ┌───┐
    ───▶│ A │
        └───┘

        ┌───┐
    ──▶ │ B │
        └───┘

          ┌───┐
    ──▶   │ C │
          └───┘
```

### Embedded arrowhead

A downward head replaces one glyph of a continuous vertical shaft or top border.

```
      │
    ┌─▼─┐
    │ │ │
    └─┼─┘
      ▼
```

### Bidirectional flow

Both heads accept a shaft between them.

```
    ◀───▶
    ─↔─
    ─⇄─
```

### Dashed guides

Straight dashed guides may cross a transverse border without a join.

```
      ╎
    ─────
      ╎
```

### Measurement partitions

Standalone bars have short endcaps and partition ticks rather than vertical trunks.

```
    budget ├─────────────┤
    fits   ├───┼───┤
    over   ├───────┼─────────┤
```

### Labelled open axis

A labelled axis can remain open; half-line ticks and diagonals are not straight runs.

```
    │ level
    │
    │
    ╵    ╱ ╲ ╳
```

### Display cells

Wide and combining characters still put both sidewalls in columns 5 and 10.

```
    ┌────┐
    │中ab│
    │éabc│
    └────┘
```

### Legend text

Legend entries are text rather than connection rows, even when their phrase uses line glyphs.

```
    ──①──▶

    ① tb_port_clx_enable  tb.c:74  │── marks the recorded field
```

### Graphic endpoints

Markers and blocks can terminate a connector.

```
    ●    ①    ▌
    │    ║    ┃
    │    ║    ┃
    ○    ·    ◆
```

<!-- kg:expect
only:
- geometry.layout
findings: []
incomplete: []
-->
