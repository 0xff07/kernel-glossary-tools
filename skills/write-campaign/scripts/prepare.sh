#!/bin/bash
# usage: skills/write-campaign/scripts/prepare.sh <campaign> <B-id | page-id | all>...   (all = every catalog page not yet on disk)
# For any campaign spec campaigns/<campaign>.md: resolves batch ids (the spec's `- B<n>: a, b` lines) or page ids,
# writes each page's content brief (the spec's content for the page plus the research pack and a page note, no
# process directives) under progress/<campaign>/pages/briefs/, regenerates the rules appendix there, and prints
# the args object for the Workflow run: {campaign, dir, version, commit, section6, tree, glossary_checkout, pages}.
# A page named more than once is listed once: two writers on one page would write the same file.
set -e
SKILL=$(cd "$(dirname "$0")/../../.." && pwd); cd "$SKILL"
. "$SKILL/skills/write-campaign/scripts/lib.sh"; TREE=$(kg_tree "$SKILL") || exit 1
CAMPAIGN=$1; shift; SPEC=campaigns/$CAMPAIGN.md; [ -f "$SPEC" ] || { echo "no spec $SPEC" >&2; exit 1; }
PY=${KG_PYTHON:-$SKILL/.venv/bin/python}
DIR=$(kg_campaign_field "$SPEC" dir); [ -n "$DIR" ] || DIR=$(kg_campaign_field "$SPEC" campaign)
VERSION=$(kg_campaign_field "$SPEC" version)
COMMIT=$(kg_campaign_field "$SPEC" commit)
SECTION6=$(kg_campaign_field "$SPEC" section6); [ -n "$SECTION6" ] || SECTION6=none
# the tree must sit at the spec's pin: KG_TREE names it when it is not the checkout holding this repository
head=$(git -C "$TREE" rev-parse HEAD 2>/dev/null || true)
[ "$head" = "$COMMIT" ] || { echo "the tree $TREE is at ${head:0:12}, not the spec's pin ${COMMIT:0:12} ($VERSION); set KG_TREE to a checkout at that commit" >&2; exit 1; }
W=progress/$CAMPAIGN/pages; mkdir -p $W/briefs $W/raw
$PY tools/rules.py prompt > $W/rules-appendix.md
pages=()
for a in "$@"; do
  if [ "$a" = "all" ]; then
    while IFS= read -r p; do [ -f "docs/$DIR/$p.md" ] || pages+=("$p"); done < <(grep -E '^page: ' $SPEC | awk '{print $2}')
  elif [[ "$a" =~ ^B[0-9]+$ ]]; then
    line=$(grep -E "^- $a: " $SPEC | head -1); [ -n "$line" ] || { echo "no batch $a in $SPEC" >&2; exit 1; }
    while IFS= read -r p; do if [ -f "docs/$DIR/$p.md" ]; then echo "skip $p: already on disk (name it explicitly to rewrite it)" >&2; else pages+=("$p"); fi; done < <(echo "$line" | sed -E 's/^- B[0-9]+: //' | tr ',' '\n' | sed 's/^ *//')
  else pages+=("$a"); fi
done
# a page named more than once (by its id and by its batch, or beside `all`) is prepared and written once
once=()
for p in "${pages[@]}"; do
  dup=0; for q in "${once[@]}"; do if [ "$q" = "$p" ]; then dup=1; break; fi; done
  if [ $dup -eq 1 ]; then echo "skip $p: named more than once, written once" >&2; else once+=("$p"); fi
done
pages=("${once[@]}")
batch=$(IFS=,; echo "${pages[*]}")
for p in "${pages[@]}"; do
  g=$(echo "$p" | tr '/' '_')
  prior=""
  del=$(git log --diff-filter=D -1 --format=%H -- "docs/$DIR/$p.md" 2>/dev/null || true)
  if [ -n "$del" ] && git cat-file -e "$del^:docs/$DIR/$p.md" 2>/dev/null; then prior="$(git rev-parse "$del^")"; fi
  $PY tools/campaign/run.py --tree "$TREE" content $SPEC "$p" --hints --out $W/raw/$g.md 2>$W/raw/$g.err || { echo "content failed for $p" >&2; cat $W/raw/$g.err >&2; exit 1; }
  { echo "CAMPAIGN CONTENT for the page $p (docs/$DIR/$p.md), extracted from $SPEC and the pinned tree on $(date +%F); every line number below is a hint to re-read on disk, never a citation."; echo
    grep -v '^SOURCES\. ' $W/raw/$g.md; echo
    echo "PAGE NOTE for $p."
    if [ -n "$prior" ]; then echo "- Prior material: a removed revision of this page, \`git show $prior:docs/$DIR/$p.md\` inside the glossary checkout (removed by commit ${del:0:12}); reuse its research (units, callers, commits, figures) re-read on disk, and not its prose where the rules it was written under were weaker than today's."
    else echo "- Prior material: none in this repository's history; the scope fence and the cluster boundary are the floor."; fi; } > $W/briefs/$g.md
  echo "brief: $W/briefs/$g.md ($(wc -c < $W/briefs/$g.md) bytes)" >&2
done
$PY - "$CAMPAIGN" "$DIR" "$VERSION" "$COMMIT" "$SECTION6" "$batch" "$TREE" "$SKILL" <<'PYEOF'
import json, sys
c, d, v, co, s6, pages, tree, skill = sys.argv[1:9]
print(json.dumps({"campaign": c, "dir": d, "version": v, "commit": co, "section6": s6, "tree": tree, "glossary_checkout": skill, "pages": [x for x in pages.split(',') if x]}))
PYEOF
