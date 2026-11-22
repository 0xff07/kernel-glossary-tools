// SPDX-License-Identifier: GPL-2.0
/*
 * The write forms of a slot: stores a lifecycle row may cite.
 */

#include <linux/bitops.h>
#include "tb.h"

struct tb_slot {
	unsigned long flags;
	unsigned int top;
	struct tb_port *loaded;
	struct tb_port *prev;
};

#define TB_SLOT_LIVE 0

static inline void tb_slot_set_live(struct tb_slot *slot)
{
	set_bit(TB_SLOT_LIVE, &slot->flags);
}

static inline void tb_slot_mark(struct tb_slot *slot)
{
	tb_slot_set_live(slot);
}

static void tb_slot_swap(struct tb_slot *slot)
{
	swap(slot->prev, slot->loaded);
}

static void tb_slot_publish(struct tb_slot *slot, unsigned int top)
{
	WRITE_ONCE(slot->top, top);
}

static void tb_slot_live(struct tb_slot *slot)
{
	assign_bit(TB_SLOT_LIVE, &slot->flags, true);
}

static void tb_slot_clear(struct tb_slot *slot)
{
	tb_slot_mark(slot);
	slot->top = 0;
}
