# Fixture port

> CAUTION: AI-GENERATED CONTENT
>
> STRICTLY DO NOT SUBMIT THIS UPSTREAM UNLESS YOU ARE AN EXPERT INTIMATELY FAMILIAR WITH THIS SUBSYSTEM.

A port is one end of a link, and the kernel keeps one record per port so that the low-power states a link runs in are known at both ends. The record decides whether a link may drop into a CL state and which end programs the adapter. A state is enabled for the whole link, so the two records are written together under one lock. This page traces how a mask of states is validated, written to both adapters, recorded and cleared again.

```
    ┌──────────┐      link      ┌──────────┐
    │ port     │◀──────────────▶│ remote   │
    │ clx      │                │ clx      │
    │ bonded   │                │ bonded   │
    └──────────┘                └──────────┘
          ▲                            ▲
          │ tb_port_clx_enable writes  │
          └────────────────────────────┘
```

## SUMMARY

The model is one record per port, written at both ends of a link when a mask of states is enabled, and cleared at one end when the link is disabled. The record is the `clx` member of the port, and the peer pointer names the other end that receives the same mask.

The journey runs from the module parameter that allows CL states at all, through the validation of the mask, to the two adapter writes and their undo when the second write fails. The invariant is that both records hold the same mask or neither does, which the undo restores. A disable clears one record and re-enables the port.

## SPECIFICATIONS

No specification applies to the fixture router; the model is a synthesis over the sources below.

## COVERAGE

### The port record
- [`'\<struct tb_port\>':'drivers/thunderbolt/tb.h'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.h#L36): the record of a port
- [`'\<tb_port_enable\>':'drivers/thunderbolt/tb.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L30): marks a port bonded
- [`'\<tb_port_clx_enable\>':'drivers/thunderbolt/tb.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51): enables a mask on both ends

## DOCUMENTATION

- [`Documentation/driver-api/thunderbolt.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/driver-api/thunderbolt.rst): the fixture's documentation

## OTHER SOURCES

### Added by kg

- [thunderbolt: add the fixture router (commit 5e8f80d3de8d)](https://lore.kernel.org/r/fixture-router@example.invalid)

## DETAILS

The first subsection shows the record a port keeps and the peer pointer beside it. The second follows the enable through its validation and its two writes under the lock. The third shows the enable of a port, which marks it bonded once a peer answers.

### A port keeps the states of its link

[`struct tb_port`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.h#L36) holds the peer pointer and the mask of enabled states, and every other member describes the port itself. The definition follows, with the mask as its third member.

```c
/* drivers/thunderbolt/tb.h:36 */
struct tb_port {
	struct tb_port *remote;
	struct tb_regs_port_header config;
	unsigned int clx;
	bool bonded;
	enum tb_tmu_mode tmu_mode;
};
```

[`struct tb_port`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.h#L36) carries [`port->clx`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.h#L39) as the mask of the states the link runs in, and [`port->remote`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.h#L37) names the other end. The record is therefore one word per port, and the peer pointer is how the second write finds its target.

### The enable validates the mask and writes both ends

[`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) refuses a mask before it touches an adapter, and it writes the two adapters of a link under [`tb_lock`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L10) so that no other enable interleaves. The function is shown in two pieces, outlined below.

| piece | lines | stage |
|---|---|---|
| ❶ | [`tb.c:51-61`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) | checks the parameter, the mask and the peer |
| ❷ | [`tb.c:62-79`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L62) | writes both adapters under the lock and records the mask |

Piece ❶ of [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) is the validation stage, which refuses a disabled parameter, a bit outside the three states and a port with no peer. Each refusal returns its own error, and none of them changes the record.

```c
/* drivers/thunderbolt/tb.c:51 */
int tb_port_clx_enable(struct tb_port *port, unsigned int clx)
{
	int ret;

	if (!clx_enabled)
		return -EOPNOTSUPP;
	if (clx & ~(TB_CL0S | TB_CL1 | TB_CL2))
		return -EINVAL;
	if (!port->remote)
		return -ENODEV;

```

The three tests return `-EOPNOTSUPP`, `-EINVAL` and `-ENODEV` in that order, so a caller can tell a policy refusal from a bad mask. The record is untouched on every refusal, which the next piece relies on.

Piece ❷ of [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) is the write stage, which takes the lock, writes the near adapter, writes the far one and records the mask at both ends. A failed second write undoes the first write before the error returns.

```c
/* drivers/thunderbolt/tb.c:62 */
	mutex_lock(&tb_lock);
	ret = tb_port_clx_write(port, clx);
	if (ret) {
		mutex_unlock(&tb_lock);
		return ret;
	}
	ret = tb_port_clx_write(port->remote, clx);
	if (ret) {
		tb_port_clx_write(port, 0);
		mutex_unlock(&tb_lock);
		return ret;
	}
	port->clx = clx;
	port->remote->clx = clx;
	mutex_unlock(&tb_lock);

	return 0;
}
```

[`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) records the mask in both [`port->clx`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.h#L39) fields after the second write succeeds, and the undo at [tb.c:70](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L70) writes zero to the near adapter when the far write fails. Both records therefore agree whenever the function returns.

```
    ┌──────────┐  ①   ┌──────────┐
    │ port ✅  │─────▶│ remote   │
    │ clx      │  ②   │ clx      │
    └──────────┘      └──────────┘

    ① tb_port_clx_enable  tb.c:74  records the mask near
    ② tb_port_clx_enable  tb.c:75  records the mask far
```

Mark ① is where [`tb_port_clx_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L51) records the mask on the near port, and mark ② is where it records the mask on the far port. The two writes stand two lines apart.

### The enable of a port marks it bonded

[`tb_port_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L30) is the plain enable, which refuses a port with no peer and otherwise marks the port bonded. It is the function the disable path ends with.

```c
/* drivers/thunderbolt/tb.c:30 */
int tb_port_enable(struct tb_port *port)
{
	if (!tb_port_has_remote(port))
		return -ENODEV;
	port->bonded = true;
	return 0;
}
```

[`tb_port_enable()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L30) tests the peer through [`tb_port_has_remote()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.h#L50) and sets [`port->bonded`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.h#L40) when the peer answers. A port with no peer is left as it was, and the error names the missing device.

<!-- kg:expect
only:
- geometry.unicode
findings:
- - geometry.unicode
  - FAIL
  - 124
  - ✅
incomplete: []
-->
