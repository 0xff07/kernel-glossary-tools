# Walk paragraphs

## DETAILS

The route names the two subsections in order. The first carries a figure and its walk, and the second a plain paragraph.

### A figure with six marks takes a six-sentence walk

The slot moves through six writes, and the figure below marks each of them. The walk after it names every mark in order.

```
    ┌─────────────────────────┐
    │ ① ② ③ ④ ⑤ ⑥             │
    └─────────────────────────┘

    ① tb_slot_swap writes.c:30  exchanges prev and loaded
    ② tb_slot_publish writes.c:35  stores the top
    ③ tb_slot_live writes.c:40  assigns the live bit
    ④ tb_slot_set_live writes.c:20  sets the live bit
    ⑤ tb_slot_clear writes.c:45  marks through the accessor
    ⑥ tb_slot_clear writes.c:46  zeroes the top
```

Mark ① is where tb_slot_swap exchanges the magazines. Mark ② is where tb_slot_publish stores the top. Mark ③ is where tb_slot_live assigns the bit. Mark ④ is where tb_slot_set_live sets it. Mark ⑤ is where tb_slot_clear marks through the accessor. Mark ⑥ is where it zeroes the top.

The six writes thus follow the strip. The slot is complete after the last one.

### A plain paragraph also permits six short sentences

The slot has a top. The top is a number. The number is small. The slot has flags. The flags are bits. The bits are few.

The paragraph above has six short sentences, just like the figure walk. Neither needs a sentence-count exception.

<!-- kg:expect
only:
- arrangement.paragraphs
findings: []
incomplete: []
-->
