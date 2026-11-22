# A function a macro invocation with several arguments defines

## DETAILS

### The call

[`fixture_call`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/forms.c#L21) adds one to its option, and the same line defines it as [`DEFINE_FIXTURE_CALL(fixture_call, int, option)`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/forms.c#L21); the macro itself is [`DEFINE_FIXTURE_CALL`](https://elixir.bootlin.com/linux/v7.2/source/drivers/thunderbolt/forms.c#L9).

<!-- kg:expect
only:
- links.definition-line
findings: []
incomplete: []
-->
