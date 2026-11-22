#!/bin/bash
# usage: skills/write-campaign/scripts/fold.sh <campaign> <page-id>...  : append the writers' unreproduced hints to the campaign's amendments file
# Each hint becomes one dated line, `- <date> (<page>): <hint>`, in progress/<campaign>/amendments.md, the fold-in's input
# (guidelines/campaign/spec.md [protocol]). A hint the file already carries for the page, whatever its date, is not
# appended again: finish.sh runs more than once over a page that was held or rerun.
# The fold-in itself is the human's: a scope sentence, a note or an assign row per hint.
SKILL=$(cd "$(dirname "$0")/../../.." && pwd); cd "$SKILL"; . "$SKILL/skills/write-campaign/scripts/lib.sh"; PY=${KG_PYTHON:-.venv/bin/python}
CAMPAIGN=$1; shift; SPEC=campaigns/$CAMPAIGN.md; [ -f "$SPEC" ] || { echo "no spec $SPEC" >&2; exit 1; }
DIR=$(kg_campaign_field "$SPEC" dir); [ -n "$DIR" ] || DIR=$(kg_campaign_field "$SPEC" campaign)
A=progress/$CAMPAIGN/amendments.md
[ -f "$A" ] || printf '# %s amendments (dated lines, one per fence they concern; folded into the spec at the fold-in and then emptied)\n' "$CAMPAIGN" > "$A"
# carried <page> <hint>: a line of the file ends with this page and this hint
carried() { S=" ($1): $2" awk 'BEGIN { s = ENVIRON["S"] } length($0) >= length(s) && substr($0, length($0) - length(s) + 1) == s { f = 1 } END { exit !f }' "$A"; }
n=0; there=0
for id in "$@"; do h=progress/$CAMPAIGN/pages/$DIR/$id/writer-report.json; [ -f "$h" ] || { echo "$id: no writer report at $h" >&2; continue; }
  while IFS= read -r line; do
    if carried "$id" "$line"; then there=$((there+1)); else printf -- '- %s (%s): %s\n' "$(date +%F)" "$id" "$line" >> "$A"; n=$((n+1)); fi
  done < <($PY -c "import json,sys; [print(h) for h in json.load(open(sys.argv[1])).get('unreproduced_hints') or [] if not str(h).lower().startswith('none')]" "$h")
done
tail=""; [ $there -gt 0 ] && tail=", $there already there"
echo "$n hint(s) appended to $A$tail"
