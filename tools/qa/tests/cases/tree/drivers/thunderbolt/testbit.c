// SPDX-License-Identifier: GPL-2.0
/*
 * A bit operation outside the listed write forms.
 */

#include <linux/bitops.h>
#include "tb.h"

struct tb_test_slot {
	unsigned long flags;
};

#define TB_TEST_LIVE 0

static void tb_slot_test_live(struct tb_test_slot *slot)
{
	__test_and_set_bit(TB_TEST_LIVE, &slot->flags);
}
