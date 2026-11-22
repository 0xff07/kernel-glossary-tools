// SPDX-License-Identifier: GPL-2.0
/*
 * Forms a parse must read: a function a macro invocation with several arguments defines, a member
 * inside an unnamed union, a write inside a macro loop, and a multi-line macro.
 */

#include "tb.h"

#define DEFINE_FIXTURE_CALL(name, type, arg) int name(type arg)
#define for_each_fixture_port(port, ports) \
	for (port = ports; port->remote; port = port->remote)

struct tb_slot_state {
	unsigned int generation;
	union {
		unsigned long bits;
		unsigned int halves[2];
	};
};

DEFINE_FIXTURE_CALL(fixture_call, int, option)
{
	return option + 1;
}

static void tb_slot_state_fill(struct tb_slot_state *state, struct tb_port *ports)
{
	struct tb_port *port;

	for_each_fixture_port(port, ports) {
		state->bits = port->clx;
	}
	state->generation++;
}
