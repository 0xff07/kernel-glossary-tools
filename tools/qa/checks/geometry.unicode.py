"""geometry.unicode: no emoji or pictograph in a figure, by the rule's list and
the supplementary blocks."""

import re

from tools.qa.inputs import violation

# an emoji or pictograph: a character of U+1F000 to U+1FAFF, one of the rule's
# default-emoji characters, or the variation selector U+FE0F; e.g. U+2705,
# U+2B50 and U+1F642
EMOJI = re.compile(
    "[\U0001f000-\U0001faff]|[⌚⌛⏩-⏬⏰⏳◽◾☔☕♈-♓♿⚓⚡⚪⚫⚽⚾⛄⛅⛎⛔⛪⛲⛳⛵⛺⛽✅✊✋✨❌❎❓-❕❗➕-➗➰➿⬛"
    "⬜⭐⭕]|️"
)


def check(page, context):
    for fence in page.figures:
        for row, line in enumerate(fence.body):
            for match in EMOJI.finditer(line):
                yield violation(
                    fence.start + 1 + row,
                    match.group(0),
                    f"an emoji or pictograph (U+{ord(match.group(0)):04X}) in"
                    " a figure",
                )
