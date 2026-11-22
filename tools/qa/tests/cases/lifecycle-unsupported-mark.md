# Lifecycle marker conformance

## DETAILS

### Writes retain their figure order

The write is at [tb.c:74](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L74).

```c
/* drivers/thunderbolt/tb.c:74 */
	port->clx = clx;
```

The figure pairs each write with its record.

```
    ┌──────────────┐
    │ ❶ state      │
    └──────────────┘

    ❶ tb_port_clx_enable tb.c:74 records the current state
```

<!-- kg:expect
only:
- lifecycle.order
findings:
- - lifecycle.order
  - review
  - null
  - ❶
incomplete: []
-->
