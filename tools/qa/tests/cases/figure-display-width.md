# Fixture port

> CAUTION: AI-GENERATED CONTENT
>
> STRICTLY DO NOT SUBMIT THIS UPSTREAM UNLESS YOU ARE AN EXPERT INTIMATELY FAMILIAR WITH THIS SUBSYSTEM.

A port is one end of a link, and the kernel keeps one record per port so that the low-power states a link runs in are known at both ends. The record decides whether a link may drop into a CL state and which end programs the adapter. A state is enabled for the whole link, so the two records are written together under one lock. This page traces how a mask of states is validated, written to both adapters, recorded and cleared again.


## DETAILS

These figures exercise display-cell geometry.

### Display-cell boundaries

The four-space indent is included; combining marks add no cells and wide characters add two.

```
    ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
    ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
    ─中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中
    ─ééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééé
    ─éééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééé
```

### Tabs

A figure tab is a violation even below the width limit.

```
    ─	label
```

### Wide register exception

A single-row register with L-connectors remains a review when it exceeds the limit.

```
    bit 1 0
    ┌─┬─┐
    │A│B│
    └┬┴┬┘
     │ │
    A┘ │
    B──┘
    ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
```

```c
	─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
```

```text
	plain listing
```

<!-- kg:expect
only:
- geometry.layout
- geometry.figure-tabs
findings:
- - geometry.layout
  - FAIL
  - 20
  - ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
- - geometry.layout
  - FAIL
  - 21
  - ─中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中中
- - geometry.layout
  - FAIL
  - 23
  - ─éééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééééé
- - geometry.figure-tabs
  - FAIL
  - 31
  - "─\tlabel"
incomplete: []
-->
