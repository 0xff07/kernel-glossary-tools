# The plan-review prompt

One fresh agent, dispatched by the plan workflow (`plan.js`, stage `review`) after the catalog and the boundaries exist in the spec. It returns amendments and never rewrites the plan.

```
Adversarially review this documentation-campaign plan for <subsystem
area>. You are attacking the catalog, not the prose. Input: the campaign
spec at <path> (context, inventory digests, catalog, boundary rules, batch
order) and the digests under <digests directory>. Tree for spot checks:
<path>, version <tag>, commit <commit>. The only file you write is the
review, <review file>.

Hunt for, and propose concrete fixes with one-line justifications:
1. Coverage gaps: topics in the digests or the request absent from both
   the catalog and the fold-in list.
2. Duplicated ownership: sibling pages whose scope statements would force
   the same walkthrough twice; propose the boundary statement and seam
   symbol, or a merge.
3. Wrong granularity: rows whose scope exceeds one page (propose the split
   line) and rows too thin to stand alone (propose the merge target).
4. Ordering defects: pages batched before the pages that explain their
   prerequisites.
5. Anchor errors: scope-statement symbols that do not exist at the
   documented version. The anchor check of validation has already asked
   the tree whether every name exists; hunt for the right name in the
   wrong page and for the renamed twin a bare existence check passes.
6. Unplaced tests and tooling: a KUnit suite, a kselftest or a test
   framework of the digests that no scope and no fold-in line names; a
   test given a page of its own that the page of the code it tests would
   carry; a framework the tests of several pages rest on that no page
   explains; a script or a tool of the digests that no page's notes name.

Save as you go: create the review file with your first confirmed
amendment and append each further one as you confirm it, so that the
file on disk always holds everything confirmed so far; a reviewer that
is cut off before it writes loses its whole review. Put the list in its
final order with one rewrite at the end if it needs one.

Write a numbered amendment list (merge / split / rescope / reorder /
fold-in), each naming the affected rows, to the review file, and return
the structured output the prompt names: one finding per amendment with
its kind, the pages it names and the text. Do not rewrite the plan.
```

## A catalog reviewed in parts

One reviewer reads the whole spec and every digest. A catalog too large for that (more than about sixty pages, or a spec whose digests alone fill most of a context) is reviewed in parts, `parts` of the workflow's arguments, each `{name, pages, digests}`: one fresh agent per part, at the same time, each writing `review-<name>.md` beside where `review.md` would be. A reviewer of a part carries out the prompt above on its pages and adds these rules:

- Of the spec, read the Context, the Scope decisions, the Campaign block, the Directory organization, the page blocks and scope fences of your part, every cluster block with its boundary fence and seam table, the fold-in adjudications, the batch order and the Checkpoint. Skip the spec's Inventory findings, which repeat the digests, and read your part's digests in the digests directory.
- The hunt is the same six items, on your pages. A finding about a seam with a page of another part names both pages, and a coverage gap is measured against your part's digests.
- Number the amendments from 1 within your file.

