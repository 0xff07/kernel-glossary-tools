---
qa: off
---

# Superlatives

A ranking or importance word sits in the same clause as the mechanic that makes it true and goes when the mechanic is absent; an "is what" or "matters" frame becomes the plain claim.

| Pattern | Kind | Scope | Unless | Exception |
|---|---|---|---|---|
| `\b(<superlative>)\b` | violation | | | a verbatim quote |
| `\bthe (fast\|slow) path\b\|\b(is\|are) what\b` | candidate | | | "the fast path" and "the slow path" where the kernel names them; a verbatim quote |

`<superlative>`: the most invasive, the most fragmenting, the most aggressive, the most consequential, the most preferred, the least preferred, the most expensive, the cheapest, the cheap path, the strongest guarantee, the weakest guarantee, the worst outcome, the best outcome, the entire performance benefit, the entire correctness benefit, the key invariant, the key difference, the key innovation, the key role, the design assumption, the design intent, matters, is what makes, what makes, the only mode that, elaborate, elegant, fundamental, cornerstone, linchpin, crucial, critical, the reasoning.

`matters` covers "X matters" and "X matters because Y"; `critical` and `matters` take no exemption.
