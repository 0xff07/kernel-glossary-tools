# An unclosed fence

## DETAILS

### The fence never closes

The excerpt below opens a fence that no later line closes.

```c
/* drivers/thunderbolt/tb.c:30 */
int tb_port_enable(struct tb_port *port)
{
	return 0;
}
<!-- kg:expect
only:
- page.fence-close
findings:
- - page.fence-close
  - FAIL
  - 9
  - '```c'
incomplete: []
-->
