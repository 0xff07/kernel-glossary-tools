# Lifecycle marker conformance

## DETAILS

### Writes retain their figure order

The write is at [tb.c:74](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L74).

```c
/* drivers/thunderbolt/tb.c:74 */
	port->clx = clx;
```

The write is at [tb.c:75](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L75).

```c
/* drivers/thunderbolt/tb.c:75 */
	port->remote->clx = clx;
```

The figure pairs each write with its record.

```
    ┌──────────────┐
    │ @1 state     │
    │ @2 state     │
    │ @3 state     │
    │ @4 state     │
    │ @5 state     │
    │ @6 state     │
    │ @7 state     │
    │ @8 state     │
    │ @9 state     │
    │ @10 state    │
    └──────────────┘

    @1 tb_port_clx_enable tb.c:75 records the current state
    @2 tb_port_clx_enable tb.c:75 records the current state
    @3 tb_port_clx_enable tb.c:75 records the current state
    @4 tb_port_clx_enable tb.c:75 records the current state
    @5 tb_port_clx_enable tb.c:75 records the current state
    @6 tb_port_clx_enable tb.c:75 records the current state
    @7 tb_port_clx_enable tb.c:75 records the current state
    @8 tb_port_clx_enable tb.c:75 records the current state
    @9 tb_port_clx_enable tb.c:75 records the current state
    @10 tb_port_clx_enable tb.c:74 records the current state
```

<!-- kg:expect
only:
- lifecycle.order
findings:
- - lifecycle.order
  - review
  - 10
  - '@10'
incomplete: []
-->
