// SPDX-License-Identifier: GPL-2.0
/*
 * A slot map: an array member written by an indexed store.
 */

#include "tb.h"

struct tb_slot_map {
	struct tb_port *map[4];
	unsigned int count;
};

static void tb_slot_map_fill(struct tb_slot_map *m, unsigned int i, struct tb_port *port)
{
	m->map[i] = port;
	m->count++;
}
