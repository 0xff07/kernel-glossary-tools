# Lifecycle marker conformance

## DETAILS

### Writes retain their figure order

The write is at [tb.c:34](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L34).

```c
/* drivers/thunderbolt/tb.c:34 */
	port->bonded = true;
```

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

The write is at [tb.c:88](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L88).

```c
/* drivers/thunderbolt/tb.c:88 */
	port->clx = 0;
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

The figure pairs each write with its record.

```
    ┌──────────────┐
    │ ➊ state      │
    │ ➋ state      │
    └──────────────┘

    ➊ tb_port_clx_enable tb.c:75 records the current state
    ➋ tb_port_clx_disable tb.c:88 records the current state
```

<!-- kg:expect
only:
- lifecycle.order
findings: []
incomplete: []
-->
