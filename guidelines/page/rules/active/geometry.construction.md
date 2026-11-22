---
qa: off
---

# Construction

For a dense figure, use a temporary coordinate-based drawing helper in the page's scratch directory when hand placement becomes fragile. Build boxes, horizontal and vertical segments, and labels from shared coordinates. Merge intended line connections into the glyph for their combined directions.

Reject writes outside the canvas and collisions with labels; preserve explicitly planned crossings and never silently clip text or overwrite an occupied cell. Preserve the chosen Unicode style and inspect the final rendered figure.
