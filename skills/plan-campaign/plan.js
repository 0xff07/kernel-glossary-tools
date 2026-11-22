export const meta = {
  name: 'plan',
  description: 'Kernel-glossary campaign planning: stage inventory (one read-only agent per area writes a digest of the tree under progress/<campaign>/plan/digests/), stage review (one fresh agent attacks the catalog of the spec and writes its amendments under progress/<campaign>/plan/review.md); the catalog itself is the planner\'s own work between the two',
  whenToUse: 'Run by the plan-campaign skill as a tool call, by guidelines/campaign/planning.md. Inventory: args {campaign, subsystem, tree, version, commit, glossary_checkout, areas: [{name, paths, request}], stage: "inventory"}; optional config (a resolved .config path), model, effort. Review, once the spec carries the catalog: the same object with stage "review"; optional parts: [{name, pages, digests}] for a catalog too large for one reviewer, one fresh agent per part.',
  phases: [
    { title: 'Inventory', detail: 'one read-only agent per area: structs, API families, lifecycle and locking, limits, renames, gates, tracing, debug printing, deferred work, debug surfaces, tests, scripts and tools, each anchored at file:line, written as a digest' },
    { title: 'Review', detail: 'one fresh agent reads the spec and the digests and lists the amendments: coverage gaps, duplicated ownership, wrong granularity, ordering defects, anchor errors, unplaced tests and tooling' },
  ],
}

const args_ = args
if (!args_ || typeof args_ !== 'object') throw new Error('the plan workflow takes an object with the campaign, its pin and a stage; run it through /kernel-glossary:plan-campaign')
const GLOSSARY_CHECKOUT = args_.glossary_checkout || args_.skill
if (!GLOSSARY_CHECKOUT) throw new Error('args need glossary_checkout, the absolute path of this repository')
const TREE = args_.tree
const CAMPAIGN = args_.campaign
const SUBSYSTEM = args_.subsystem || CAMPAIGN
const VERSION = args_.version
const COMMIT = args_.commit
if (!CAMPAIGN || !TREE || !VERSION || !COMMIT) throw new Error('args need campaign, tree, version and commit')
const stage = args_.stage || 'inventory'
const MODEL = args_.model || 'opus'
const EFFORT = args_.effort || 'high'
const P = `${GLOSSARY_CHECKOUT}/progress/${CAMPAIGN}/plan`
const PROMPTS = `${GLOSSARY_CHECKOUT}/skills/plan-campaign/prompts`
const CONFIG = args_.config ? `the documented build's resolved config is ${args_.config}` : 'no resolved config is given, so a gate\'s value in the documented build is read from the defconfig and the Kconfig defaults, and said to be'
const g = name => name.replace(/[^A-Za-z0-9_-]+/g, '_')

const DIGEST = {
  type: 'object',
  properties: {
    area: { type: 'string' }, file: { type: 'string' }, lines: { type: 'integer' },
    suggested_topics: { type: 'array', items: { type: 'string' } },
    open_questions: { type: 'array', items: { type: 'string' } },
    tooling: { type: 'array', items: { type: 'string' } },
  },
  required: ['area', 'file', 'lines', 'suggested_topics', 'open_questions', 'tooling'],
}
const REVIEW = {
  type: 'object',
  properties: {
    file: { type: 'string' },
    findings: { type: 'array', items: { type: 'object', properties: { kind: { type: 'string', enum: ['merge', 'split', 'rescope', 'reorder', 'fold-in', 'anchor'] }, pages: { type: 'array', items: { type: 'string' } }, text: { type: 'string' } }, required: ['kind', 'pages', 'text'] } },
  },
  required: ['file', 'findings'],
}

const inventoryPrompt = (a) => `You inventory one area of a kernel subsystem for a documentation campaign; the planner curates the catalog from your digest. Read ${PROMPTS}/inventory.md and carry it out with these parameters. Area: ${a.name}. Subsystem: ${SUBSYSTEM}. The request for this area: ${a.request || 'the area as its paths define it'}. Tree: ${TREE}, version ${VERSION}, commit ${COMMIT}; ${CONFIG}. Kernel paths of the area: ${(a.paths || []).join(', ') || 'the subsystem\'s paths of ' + GLOSSARY_CHECKOUT + '/guidelines/subsystems.md'}. The tools and their measured holes: ${GLOSSARY_CHECKOUT}/skills/research-tools.md. The digest file you write: ${P}/digests/${g(a.name)}.md (create the directory). Read-only on the tree; no other file; no git command that changes state; print at most about 25 KB per command and a function by its range. Return the structured output and nothing else.`

const reviewPrompt = (part) => `You review the catalog of a documentation-campaign plan, adversarially; you never rewrite the plan. Read ${PROMPTS}/plan-review.md and carry it out with these parameters. Subsystem area: ${SUBSYSTEM}. The campaign spec: ${GLOSSARY_CHECKOUT}/campaigns/${CAMPAIGN}.md. The digests: ${P}/digests/. Tree for spot checks: ${TREE}, version ${VERSION}, commit ${COMMIT}. The review file you write: ${part ? `${P}/review-${g(part.name)}.md` : `${P}/review.md`}.${part ? ` The catalog is reviewed in parts, as the prompt file's last section says. Your part: ${part.pages}. Its digests: ${(part.digests || []).map(d => `${P}/digests/${g(d)}.md`).join(', ') || 'the ones of the digests directory its pages come from'}.` : ''} The spec's own validation is ${GLOSSARY_CHECKOUT}/.venv/bin/python ${GLOSSARY_CHECKOUT}/tools/campaign/run.py validate ${GLOSSARY_CHECKOUT}/campaigns/${CAMPAIGN}.md --anchors --checklist, which you may run; its warnings are findings of kind anchor when a scope names a symbol the tree lacks. No other file; no git command that changes state; print at most about 25 KB per command. Return the structured output and nothing else.`

if (stage === 'inventory') {
  const areas = args_.areas || []
  if (!areas.length) throw new Error('args_.areas is empty: one {name, paths, request} per area, the areas along the request\'s headings, as many as the subsystem takes')
  const results = await parallel(areas.map(a => () => agent(inventoryPrompt(a), { label: `inventory:${a.name}`, phase: 'Inventory', schema: DIGEST, model: MODEL, effort: EFFORT })
    .then(d => { log(d ? `${a.name}: digest ${d.file}, ${d.lines} lines, ${d.suggested_topics.length} suggested topics, ${d.open_questions.length} open questions` : `${a.name}: the inventory returned nothing`); return d })))
  return results.filter(Boolean)
}
if (stage === 'review') {
  const parts = args_.parts || []
  const options = (label) => ({ label, phase: 'Review', schema: REVIEW, model: MODEL, effort: args_.effort || 'xhigh' })
  if (!parts.length) {
    const r = await agent(reviewPrompt(), options('review'))
    log(r ? `review: ${r.findings.length} findings in ${r.file}` : 'the review returned nothing')
    return r
  }
  // a catalog too large for one reviewer: one fresh agent per part, each on its own pages and digests
  const results = await parallel(parts.map(p => () => agent(reviewPrompt(p), options(`review:${p.name}`))
    .then(r => { log(r ? `${p.name}: ${r.findings.length} findings in ${r.file}` : `${p.name}: the review returned nothing`); return r })))
  return results.filter(Boolean)
}
throw new Error('args_.stage must be "inventory" or "review"')
