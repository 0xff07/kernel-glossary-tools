#!/bin/bash
# usage: skills/write-campaign/scripts/finish.sh <campaign> [--journal <run>/journal.jsonl] [--co-author "Model <email>"] [--accept <page-id>]... [--dry-run] <page-id>...
#   : the gate over each page of a run, one commit per new page that passed and is not held, the fold of the writers' hints;
#     with --dry-run, the gate alone, one summary line per page
# With --journal (the journal.jsonl of the Workflow run, in the transcript directory the tool result named), each page's
# writer-report.json is first written from the writer's structured output, the last thing the writer returned; the file the
# writer saved itself is kept beside it as writer-report.saved.json when it differs (writers save it before the report is
# complete, so it is often shorter). A page whose writer returned nothing keeps the file the writer saved.
# For each page, in the plan's catalog order: the automatic checker (tools/qa/run.py --spec). A page that passed and
# is new on disk is committed on its own, subject `<dir>: add <group>/<slug>` and the Co-Authored-By trailer,
# nothing else (CLAUDE.md). The trailer names the model that wrote the page: the model of the writer's own turns in its
# transcript beside the journal (agent-<id>.jsonl), which is the workflow's `model` argument and not the model that
# runs this script. --co-author, or KG_CO_AUTHOR in the environment, stands in only for a page whose writer the
# journal's transcripts do not name.
# A page that passed is held, uncommitted, when nobody has answered for what the checker still prints: a scope name
# the page names nowhere (a coverage.scope-closure candidate), or more candidates than the writer's report keeps
# (qa.candidates_kept, with what a proofreader of the same journal left on those rules). A held page is rerun with
# the page named explicitly, or its scope fence is corrected, or --accept <page-id> commits it as it stands on the
# user's word. A page that failed, is held or is missing is reported and counted in the exit status; a committed
# page modified on disk is left as it is (a rewrite starts with a removal, CLAUDE.md). Then skills/write-campaign/scripts/fold.sh appends
# the writers' unreproduced hints to progress/<campaign>/amendments.md. One line per page, then a summary line;
# exit 1 when a page failed the gate, is held or is missing, 2 on a usage error. --dry-run runs the gate and says what
# would be committed, writing nothing.
set -u
SKILL=$(cd "$(dirname "$0")/../../.." && pwd); cd "$SKILL"; . "$SKILL/skills/write-campaign/scripts/lib.sh"; TREE=$(kg_tree "$SKILL") || exit 1; PY=${KG_PYTHON:-.venv/bin/python}
usage() { echo 'usage: skills/write-campaign/scripts/finish.sh <campaign> [--journal <run>/journal.jsonl] [--co-author "Model <email>"] [--accept <page-id>]... [--dry-run] <page-id>...' >&2; exit 2; }
CAMPAIGN=${1:-}; [ -n "$CAMPAIGN" ] || usage; shift
SPEC=campaigns/$CAMPAIGN.md; [ -f "$SPEC" ] || { echo "no spec $SPEC" >&2; exit 2; }
CO=${KG_CO_AUTHOR:-}; DRY=0; JOURNAL=""; ids=(); accept=()
while [ $# -gt 0 ]; do case "$1" in
  --co-author) [ $# -ge 2 ] || usage; CO=$2; shift 2;;
  --co-author=*) CO=${1#--co-author=}; shift;;
  --journal) [ $# -ge 2 ] || usage; JOURNAL=$2; shift 2;;
  --journal=*) JOURNAL=${1#--journal=}; shift;;
  --accept) [ $# -ge 2 ] || usage; accept+=("$2"); shift 2;;
  --accept=*) accept+=("${1#--accept=}"); shift;;
  --dry-run) DRY=1; shift;;
  --*) echo "unknown option $1" >&2; usage;;
  *) ids+=("$1"); shift;;
esac; done
[ ${#ids[@]} -gt 0 ] || usage
[ -z "$JOURNAL" ] || [ -f "$JOURNAL" ] || { echo "no journal $JOURNAL" >&2; exit 2; }
[ $DRY -eq 1 ] || [ -n "$CO" ] || [ -n "$JOURNAL" ] || { echo 'no Co-Authored-By trailer: pass --journal, whose transcripts name the model that wrote each page, or --co-author "Model <email>"' >&2; exit 2; }
accepted() { local a; for a in ${accept[@]+"${accept[@]}"}; do [ "$a" = "$1" ] && return 0; done; return 1; }
for a in ${accept[@]+"${accept[@]}"}; do
  known=0; for i in "${ids[@]}"; do [ "$i" = "$a" ] && known=1; done
  [ $known -eq 1 ] || { echo "--accept $a names no page of this run" >&2; exit 2; }
done
VERSION=$(kg_campaign_field "$SPEC" version); COMMIT=$(kg_campaign_field "$SPEC" commit); DIR=$(kg_campaign_field "$SPEC" dir); [ -n "$DIR" ] || DIR=$CAMPAIGN
head=$(git -C "$TREE" rev-parse HEAD 2>/dev/null || true); [ "$head" = "$COMMIT" ] || { echo "the tree $TREE is at ${head:0:12}, not the spec's pin ${COMMIT:0:12} ($VERSION); set KG_TREE to a checkout at that commit" >&2; exit 1; }

# the plan's catalog order is the order of the kg:page blocks; a page the spec does not list comes last, as given
ordered=$($PY - "$SPEC" "${ids[@]}" <<'PYEOF'
import re, sys
spec, ids = sys.argv[1], sys.argv[2:]
# every `page:` line of the spec, group 1 the page id, in the order the catalog lists them; e.g. `page: rc/portdrv/dpc` gives rc/portdrv/dpc
order = re.findall(r'^page:[ \t]*(\S+)[ \t]*$', open(spec, encoding='utf-8').read(), re.M)
rank = {p: i for i, p in enumerate(order)}
seen = list(dict.fromkeys(ids))
for p in sorted(seen, key=lambda p: (rank.get(p, len(order)), seen.index(p))):
    print(p)
PYEOF
)

# the writer's structured output, recorded in the run's journal, is the report of record; it replaces the file the writer saved
if [ -n "$JOURNAL" ]; then $PY - "$JOURNAL" "progress/$CAMPAIGN/pages/$DIR" "$DRY" "${ids[@]}" <<'PYEOF' || exit 2
import json, os, sys
journal, root, dry, ids = sys.argv[1], sys.argv[2], sys.argv[3] == '1', sys.argv[4:]
label, result = {}, {}
for line in open(journal, encoding='utf-8'):
    try: r = json.loads(line)
    except ValueError: continue
    if r.get('type') == 'started': label[r.get('agentId')] = r.get('label')
    elif r.get('type') == 'result': result[label.get(r.get('agentId'))] = r.get('result', r.get('value'))
n = lambda d, k: len(d.get(k) or []) if isinstance(d, dict) else 0
counts = lambda a, b: f"open issues {n(a,'open_issues')} -> {n(b,'open_issues')}, scope left out {n(a,'scope_left_out')} -> {n(b,'scope_left_out')}, hints {n(a,'unreproduced_hints')} -> {n(b,'unreproduced_hints')}"
for p in ids:
    w = result.get('write:' + p)
    if isinstance(w, str):
        try: w = json.loads(w)
        except ValueError: pass
    h = os.path.join(root, p, 'writer-report.json')
    if not isinstance(w, dict):
        print(f"{p}: no writer result in the journal; the report the writer saved stands{'' if os.path.exists(h) else ' (none on disk)'}"); continue
    old = None
    if os.path.exists(h):
        try: old = json.load(open(h, encoding='utf-8'))
        except ValueError: old = {}
    if old == w: continue
    if dry:
        print(f"{p}: writer-report.json {'differs from' if old is not None else 'missing;'} the writer's structured output ({counts(old, w)}); would be written from it (dry run)"); continue
    os.makedirs(os.path.dirname(h), exist_ok=True)
    if old is not None: os.replace(h, os.path.join(root, p, 'writer-report.saved.json'))
    with open(h, 'w', encoding='utf-8') as f: json.dump(w, f, indent=1, ensure_ascii=False); f.write('\n')
    print(f"{p}: writer-report.json written from the writer's structured output" + (f" ({counts(old, w)}); the writer's own file kept as writer-report.saved.json" if old is not None else " (the writer saved none)"))
PYEOF
fi

# the trailer of a page names the model that wrote it: one line `<page>\t<Model <email>>...` per page whose writer's
# transcript, beside the journal, names the model of its turns (claude-opus-5-5 reads Claude Opus 5.5)
IFS= read -r -d '' TRAILERS_PY <<'PYEOF'
import json, os, re, sys
journal, ids = sys.argv[1], sys.argv[2:]
run = os.path.dirname(os.path.abspath(journal))
agents = {}
for line in open(journal, encoding='utf-8'):
    try: r = json.loads(line)
    except ValueError: continue
    if r.get('type') == 'started' and r.get('label') and r.get('agentId'): agents.setdefault(r['label'], []).append(r['agentId'])
def models(agent):
    seen = []
    try:
        with open(os.path.join(run, f'agent-{agent}.jsonl'), encoding='utf-8') as f:
            for line in f:
                if '"assistant"' not in line: continue
                try: r = json.loads(line)
                except ValueError: continue
                m = r.get('message') if isinstance(r, dict) and r.get('type') == 'assistant' else None
                m = m.get('model') if isinstance(m, dict) else None
                if isinstance(m, str) and m and not m.startswith('<') and m not in seen: seen.append(m)
    except OSError: pass
    return seen
def name(model):
    # a model id: family, major version, an optional minor one and an optional date; e.g. `claude-opus-5-5` gives opus, 5 and 5,
    # and `claude-opus-5-20261101` gives opus and 5
    m = re.fullmatch(r'claude-([a-z]+)-(\d+)(?:-(\d{1,2}))?(?:-\d{8})?', model)
    return f"Claude {m.group(1).capitalize()} {m.group(2)}{'.' + m.group(3) if m.group(3) else ''}" if m else None
for p in dict.fromkeys(ids):
    names = []
    for a in agents.get('write:' + p, []):
        for m in models(a):
            n = name(m)
            if n is None: print(f"{p}: the writer's transcript names the model {m}, which gives no trailer name; --co-author stands in for it", file=sys.stderr)
            elif n not in names: names.append(n)
    if names: print(p + '\t' + '\t'.join(n + ' <noreply@anthropic.com>' for n in names))
PYEOF
MODELS=""; if [ -n "$JOURNAL" ]; then MODELS=$($PY -c "$TRAILERS_PY" "$JOURNAL" "${ids[@]}") || exit 2; fi

# one checker run per page, read as JSON on stdin; five lines out: the summary line, the violations, what holds a
# page that passed (empty when nothing does), the tally of the writer's report, and `ok` when the checker's report was read
IFS= read -r -d '' GATE_PY <<'PYEOF'
import collections, json, sys
sys.path.insert(0, '.')
writer_report, journal, pid = sys.argv[1], sys.argv[2], sys.argv[3]
raw = sys.stdin.read()
one = lambda s: ' '.join(str(s).split())
several = lambda n, word: f"{n} {word}" + ('' if n == 1 else 's')
report = None
for line in raw.splitlines():
    if line.startswith('{'):
        try: report = json.loads(line)
        except ValueError: pass
# the writer's report of record is the writer's structured output in the journal, else the file on disk; a proofreader of
# the same journal answers, in `left`, for what it read and did not repair
writer, left = None, collections.Counter()
if journal:
    label = {}
    for line in open(journal, encoding='utf-8'):
        try: r = json.loads(line)
        except ValueError: continue
        if r.get('type') == 'started': label[r.get('agentId')] = r.get('label'); continue
        if r.get('type') != 'result' or label.get(r.get('agentId')) not in ('write:' + pid, 'proofread:' + pid): continue
        v = r.get('result', r.get('value'))
        if isinstance(v, str):
            try: v = json.loads(v)
            except ValueError: v = None
        if not isinstance(v, dict): continue
        if label[r.get('agentId')] == 'write:' + pid: writer = v
        else: left = collections.Counter(str(e.get('rule')) for e in v.get('left') or [] if isinstance(e, dict))
kept, tally = 0, 'no writer report'
try:
    d = writer if writer is not None else json.load(open(writer_report, encoding='utf-8'))
    kept = len((d.get('qa') or {}).get('candidates_kept') or [])
    tally = f"candidates kept {kept}, open issues {len(d.get('open_issues') or [])}, scope left out {len(d.get('scope_left_out') or [])}, hints {len(d.get('unreproduced_hints') or [])}"
except FileNotFoundError: pass
except (OSError, ValueError, AttributeError, TypeError): kept, tally = 0, 'writer report unreadable'
if not isinstance(report, dict) or not isinstance(report.get('automatic'), list):
    print(''); print(one(raw)[:400]); print(''); print(tally); print('ok'); sys.exit(0)
from tools.qa.run import render
summary = [l for l in render(report).splitlines() if l.startswith('automatic:')][-1]
found = [(item['rule'], f) for item in report['automatic'] for f in item['findings']]
viol = [f"{rule}:{f['line']}: {f['message']}" if f['line'] else f"{rule}: {f['message']}" for rule, f in found if f['kind'] == 'violation']
viol += [f"{e['rule']}: execution error: {e['message']}" for e in report['errors']]
cands = collections.Counter(rule for rule, f in found if f['kind'] == 'candidate')
scope = [f.get('quote') or '?' for rule, f in found if f['kind'] == 'candidate' and rule == 'coverage.scope-closure']
hold = []
if scope:
    hold.append(f"{several(len(scope), 'scope name')} the page names nowhere ({', '.join(scope[:8])}{f' and {len(scope) - 8} more' if len(scope) > 8 else ''})")
total, answered = sum(cands.values()), kept + sum(min(n, left[rule]) for rule, n in cands.items())
if total > answered:
    by = ', '.join(f"{rule} {n}" for rule, n in sorted(cands.items()))
    hold.append(f"the checker prints {several(total, 'candidate')} ({by}) and the writer's report answers for {answered}")
print(summary); print('; '.join(one(v) for v in viol[:3]) + (f"; and {len(viol) - 3} more" if len(viol) > 3 else '')); print('; '.join(hold)); print(tally); print('ok')
PYEOF

committed=0; already=0; failed=0; held=0; left=0; folds=()
for id in $ordered; do page=docs/$DIR/$id.md; h=progress/$CAMPAIGN/pages/$DIR/$id/writer-report.json
  if [ ! -f "$page" ]; then echo "$id: MISSING, no page on disk"; failed=$((failed+1)); continue; fi
  out=$($PY tools/qa/run.py --tree "$TREE" --spec "$SPEC" --json "$page" 2>&1); rc=$?
  { IFS= read -r summary; IFS= read -r viol; IFS= read -r hold; IFS= read -r tally; IFS= read -r read_ok; } < <(printf '%s\n' "$out" | $PY -c "$GATE_PY" "$h" "$JOURNAL" "$id")
  gate="${summary:-no summary} | lines=$(wc -l < "$page") c-fences=$(grep -c '^```c$' "$page") figures=$($PY tools/qa/views.py "$page" figures 2>/dev/null | grep -c ' marks')"
  [ -f "$h" ] && folds+=("$id")
  if [ "$read_ok" != ok ]; then echo "$id: FAILED, the checker's report could not be read (rc=$rc); $(printf '%s' "$out" | head -c 300 | tr '\n' ' ')"; failed=$((failed+1)); continue; fi
  if [ $rc -ne 0 ] && [ $rc -ne 3 ]; then
    echo "$id: FAILED the gate (rc=$rc); $gate; $viol"; failed=$((failed+1)); continue
  fi
  if git ls-files --error-unmatch -- "$page" >/dev/null 2>&1; then
    if git diff --quiet -- "$page" && git diff --cached --quiet -- "$page"; then
      echo "$id: passed, already committed in $(git log -1 --format=%h -- "$page"); $gate; $tally"; already=$((already+1))
    else
      echo "$id: passed, but a committed page modified on disk, left uncommitted (a rewrite starts with a removal, CLAUDE.md); $gate; $tally"; left=$((left+1))
    fi
    continue
  fi
  note=""
  if [ -n "$hold" ]; then
    if accepted "$id"; then note=" (accepted with: $hold)"
    else echo "$id: HELD, passed the gate but left uncommitted: $hold; $gate; $tally"; held=$((held+1)); continue; fi
  fi
  trailers=$(printf '%s\n' "$MODELS" | awk -F'\t' -v id="$id" '$1 == id { for (i = 2; i <= NF; i++) print $i; exit }')
  [ -n "$trailers" ] || trailers=$CO
  by=$(printf '%s\n' "$trailers" | sed 's/ *<.*//' | paste -sd, - | sed 's/,/, /g')
  if [ -z "$trailers" ] && [ -n "$JOURNAL" ]; then echo "$id: passed, but no transcript beside the journal names its writer's model and no --co-author stands in, left uncommitted$note; $gate; $tally"; left=$((left+1)); continue; fi
  if [ $DRY -eq 1 ]; then echo "$id: passed, would commit \"$DIR: add $id\" (${by:-trailer not given})$note; $gate; $tally"; committed=$((committed+1)); continue; fi
  if git add -- "$page" && git commit -q --only -m "$DIR: add $id" -m "$(printf '%s\n' "$trailers" | sed 's/^/Co-Authored-By: /')" -- "$page"; then
    echo "$id: committed $(git log -1 --format=%h) \"$DIR: add $id\" ($by)$note; $gate; $tally"; committed=$((committed+1))
  else
    echo "$id: passed, but the commit failed; $gate; $tally"; left=$((left+1))
  fi
done
if [ $DRY -eq 0 ] && [ ${#folds[@]} -gt 0 ]; then skills/write-campaign/scripts/fold.sh "$CAMPAIGN" "${folds[@]}"; fi
tail=""; [ $DRY -eq 1 ] && tail=" (dry run: nothing written)"
echo "finished: $committed committed, $already already committed, $failed failed or missing, $held held, $left left uncommitted$tail"
[ $failed -eq 0 ] && [ $held -eq 0 ]
