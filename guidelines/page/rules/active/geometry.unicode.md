---
qa: off
---

# Unicode

A figure may use any non-emoji character and contains at least one box-drawing/block, arrow or geometric-shape drawing character. Default to Unicode box drawing. Use double borders for emphasis or a different kind of construct, dashed lines for guides/barriers/another path class, block glyphs for fills, triangles for arrowheads and a middle dot for a placeholder cell.

Give each glyph one meaning and draw one kind of line with one glyph set. Function-site marks use ①–⑩, ➊–➓, «1» onward, «A»–«Z», @1 onward or @A–@Z; their marks alone do not classify a fence as a figure. Emoji and pictographs do not appear in figures.

Reference palette, with optional examples of uses:

| kind | glyphs | possible uses |
|---|---|---|
| lines | `─ │` | borders, trunks, axes |
| corners | `┌ ┐ └ ┘` | box corners and turns |
| joins | `├ ┤ ┬ ┴ ┼` | attachments and branches |
| arrows | `▶ ◀ ▲ ▼ → ← ↑ ↓ ⇄ ↔` | direction, paired flows, bidirectional relationships |
| double borders | `═ ║ ╔ ╗ ╚ ╝` | emphasis or another kind of construct |
| markers | `● ○ ◆ ▪ ✓ ✗` | points, categories, status |
| numbered sites | `① ➊ «1» «A» @1 @A` | marks resolved by the figure's legend, one family per figure, differing between figures that follow each other and within one subsection |
| diagonals | `╱ ╲` | sloping edges or segments |
| blocks | `█ ▓ ▒ ░ ▏ ▎ ▍ ▌ ▋ ▊ ▉` | fills, density, partial-cell extents |

Numbered function-site marks use the families listed here; other markers can indicate points, categories or status. Give each glyph a consistent meaning. Size a marker column for its longest token, such as «16» or @16, and pad outside shorter tokens so following labels and walls keep their columns. Check the chosen glyphs in the intended monospace rendering.

For prohibited emoji, inspect U+1F000–U+1FAFF, U+FE0F, and these default-emoji characters: `⌚ ⌛ ⏩–⏬ ⏰ ⏳ ◽ ◾ ☔ ☕ ♈–♓ ♿ ⚓ ⚡ ⚪ ⚫ ⚽ ⚾ ⛄ ⛅ ⛎ ⛔ ⛪ ⛲ ⛳ ⛵ ⛺ ⛽ ✅ ✊ ✋ ✨ ❌ ❎ ❓–❕ ❗ ➕–➗ ➰ ➿ ⬛ ⬜ ⭐ ⭕`. Prose numbering is outside this restriction. A figure needs a drawing character in U+2500–U+259F, U+2190–U+21FF or U+25A0–U+25FF; the marks alone do not make a fence a figure.
