# Lifecycle marker conformance

## DETAILS

### Writes retain their figure order

The write is at [tb.c:74](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L74).

```c
/* drivers/thunderbolt/tb.c:74 */
	port->clx = clx;
```

The write is at [tb.c:34](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L34).

```c
/* drivers/thunderbolt/tb.c:34 */
	port->bonded = true;
```

The figure pairs each write with its record.

```
    ┌──────────────┐
    │ ① state      │
    │ ② state      │
    └──────────────┘

    ① tb_port_enable tb.c:34 records the current state
    ② tb_port_clx_enable tb.c:74 records the current state
```

<!-- kg:expect
only:
- lifecycle.order
findings:
- - lifecycle.order
  - review
  - 10
  - ②
incomplete: []
-->
