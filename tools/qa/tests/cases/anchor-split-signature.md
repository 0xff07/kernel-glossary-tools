# Fixture lookup

> CAUTION: AI-GENERATED CONTENT
>
> STRICTLY DO NOT SUBMIT THIS UPSTREAM UNLESS YOU ARE AN EXPERT INTIMATELY FAMILIAR WITH THIS SUBSYSTEM.

A port is found by its index in the fixture's table, through a lookup whose signature is split across two lines: the return type on one line, the name and the parameters on the next. This page cites the lookup at the first line of that signature, the definition line the rule names, and shows it whole but for its last two lines, so that the walkthrough must see the function behind the split signature to report the lines it lacks.

```
    ┌──────────┐   index   ┌──────────┐
    │ caller   │──────────▶│ ports[]  │
    └──────────┘           └──────────┘
```

## SUMMARY

The model is one table of ports indexed by a small integer, and one lookup that bounds the index before it returns a pointer into the table.

## SPECIFICATIONS

No specification applies to the fixture router; the model is a synthesis over the sources below.

## COVERAGE

### The lookup
- [`'\<tb_port_lookup\>':'drivers/thunderbolt/tb.c'`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L92): finds a port by index

## DOCUMENTATION

- [`Documentation/driver-api/thunderbolt.rst`](https://elixir.bootlin.com/linux/v7.2/source/Documentation/driver-api/thunderbolt.rst): the fixture's documentation

## OTHER SOURCES

### Added by kg

- [thunderbolt: add the fixture router (commit 5e8f80d3de8d)](https://lore.kernel.org/r/fixture-router@example.invalid)

## DETAILS

The one subsection shows the lookup from its split signature.

### The lookup bounds the index

[`tb_port_lookup()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L92) is linked at the first line of its signature, the return type's line, and [`tb_port_lookup()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L93) at the name line, both definition lines of the same function; the blank line above the signature is no definition line, so [`tb_port_lookup()`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/tb.c#L91) fails.

```c
/* drivers/thunderbolt/tb.c:92 */
static struct tb_port *
tb_port_lookup(unsigned int index)
{
	if (index >= ARRAY_SIZE(ports))
		return NULL;
```

The excerpt stops before the return and the closing brace, which the walkthrough reports as lines no excerpt reproduces.

<!-- kg:expect
only:
- links.definition-line
- excerpts.walkthrough
findings:
- - links.definition-line
  - FAIL
  - 44
  - tb_port_lookup()
- - excerpts.walkthrough
  - FAIL
  - null
  - tb_port_lookup
incomplete: []
-->
