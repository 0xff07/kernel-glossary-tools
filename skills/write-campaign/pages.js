export const meta = {
  name: 'pages',
  description: 'Kernel-glossary page production for any campaign from the standard alone (the writing rules, the spec content for the page): stage write (one writer per page, the automatic checks only), stage proofread (one proofreader per page that repairs as it reads, through the reading procedures under skills/write-campaign/proofread/), or both without the human gate',
  whenToUse: 'Run by the write-campaign skill: skills/write-campaign/scripts/prepare.sh prints the args object and the skill passes it with a stage (write, proofread, both; prepare only echoes the prepared args). Optional args: model (opus), effort (xhigh), proofread (the procedure names), proofreadBudget (40), writerReports ({page: report} for a proofread stage), notice (a sentence from the user relayed to every agent of the run). The writer reads skills/write-campaign/prompts/writer.md; the proofreader reads skills/write-campaign/proofread/common.md.',
  phases: [
    { title: 'Write', detail: 'one writer per page: rules, spec content, the pinned tree; severity-1 checks only; writer report saved beside the page scratch' },
    { title: 'Proofread', detail: 'one proofreader per page reads the page once in order through the chosen procedures and repairs as it reads, within a command budget' },
  ],
}

const args_ = args
if (!args_ || typeof args_ !== 'object') throw new Error('the pages workflow takes the object skills/write-campaign/scripts/prepare.sh prints, with a stage; run it through /kernel-glossary:write-campaign')
const GLOSSARY_CHECKOUT = args_.glossary_checkout || args_.skill
if (!GLOSSARY_CHECKOUT) throw new Error('args need glossary_checkout, the absolute path of this repository: paste the object skills/write-campaign/scripts/prepare.sh prints')
const TREE = args_.tree
if (!TREE) throw new Error('args need tree, the kernel checkout at the pin: paste the object skills/write-campaign/scripts/prepare.sh prints')
const CAMPAIGN = args_.campaign
const DIR = args_.dir
const VERSION = args_.version
const COMMIT = args_.commit
const SECTION6 = args_.section6 || 'none'
if (!CAMPAIGN || !DIR || !VERSION || !COMMIT) throw new Error('args need campaign, dir, version and commit: paste the object skills/write-campaign/scripts/prepare.sh prints')
const SPEC = `${GLOSSARY_CHECKOUT}/campaigns/${CAMPAIGN}.md`
const W = `${GLOSSARY_CHECKOUT}/progress/${CAMPAIGN}/pages`
const PY = `${GLOSSARY_CHECKOUT}/.venv/bin/python`
const APPENDIX = `${W}/rules-appendix.md`
const PROMPTS = `${GLOSSARY_CHECKOUT}/skills/write-campaign/prompts`
const PROOFREAD = `${GLOSSARY_CHECKOUT}/skills/write-campaign/proofread`
const PROCEDURES = args_.proofread || ['code', 'figures', 'explain']
const MODEL = args_.model || 'opus'
const EFFORT = args_.effort || 'xhigh'
const BUDGET = args_.proofreadBudget || 40
const stage = args_.stage || 'write'
const NOTICE = args_.notice ? `\n\nNotice from the user for this run: ${args_.notice}` : ''
// one agent per page: a page listed twice would have two agents writing the same file
const pages = [...new Set(args_.pages || [])]
if (stage === 'prepare') return { prepared: { campaign: CAMPAIGN, dir: DIR, version: VERSION, commit: COMMIT, section6: SECTION6, tree: TREE, glossary_checkout: GLOSSARY_CHECKOUT, pages } }
if (!pages.length) throw new Error('args_.pages is empty; run skills/write-campaign/scripts/prepare.sh first')

const g = id => id.replace(/\//g, '_')
const paths = id => ({ id, page: `${GLOSSARY_CHECKOUT}/docs/${DIR}/${id}.md`, brief: `${W}/briefs/${g(id)}.md`, scratch: `${W}/${DIR}/${id}` })
const section6Text = SECTION6 === 'none' ? 'no section six' : `section six headed ${SECTION6}`

// the parameters skills/write-campaign/prompts/writer.md and skills/write-campaign/proofread/common.md are written against, by the names they use
const FACTS = (p) => `Parameters. KG_GLOSSARY_CHECKOUT: ${GLOSSARY_CHECKOUT}, this repository. KG_TREE: ${TREE}, the pinned tree at tag ${VERSION} (VERSION), commit ${COMMIT} (COMMIT). PY: ${PY}, the interpreter. DIR: ${DIR}, the knowledge base under docs/${DIR}/, with ${section6Text} (SECTION6: ${SECTION6}). PAGE: ${p.page} (PAGE_ID: ${p.id}). BRIEF: ${p.brief}, the campaign spec's content for this page. SCRATCH: ${p.scratch}, the page's scratch directory. APPENDIX: ${APPENDIX}, the rules appendix. SPEC: ${SPEC}.`

const writerPrompt = (p) => `You write one page of a kernel-glossary knowledge base. Read ${PROMPTS}/writer.md and carry it out with these parameters, which are the names that file uses.

${FACTS(p)}${NOTICE}

Hand over by returning the structured output and nothing else.`

const proofreadPrompt = (p, w) => `You are the proofreader and repairer of one page of a kernel-glossary knowledge base: ${p.id} in docs/${DIR}, documented at ${VERSION}, written by another agent. You read the page once, in order, and repair what fails a rule as you read, severity 1 first; you hand nothing over to another agent. The only files you write are the page ${p.page} and files under ${p.scratch}/proofread (create it); never another page, the spec or this repository; no git command that changes state.

${FACTS(p)}${NOTICE}

The standard the page is written to, the aids, the research tools on this machine and the printing limits are the first section of ${PROMPTS}/writer.md, "The standard, the aids and the limits"; read that section and not the procedure after it.

The writer's report, hints and not evidence: ${w ? JSON.stringify(w) : `read ${p.scratch}/writer-report.json if it exists`}.

Read ${PROOFREAD}/common.md first: it gives the procedure, the severity table and the report. Then read ${PROCEDURES.map(n => `${PROOFREAD}/${n}.md`).join(', ')}, each a list of rule-id prefixes and reading steps; read the rule files those prefixes name, whole, and follow the steps in that order as your single pass. Budget: at most ${BUDGET} commands in all, the brief read for its MISSION and CAMPAIGN FACTS only (its research pack you need not read), the page read once in subsection-sized slices, the checker run once at the start and once at the end, a family of checkers again after a repair with --prefix. Return the structured output and nothing else.`

const WRITER = {
  type: 'object',
  properties: {
    page: { type: 'string' }, built_with_expand: { type: 'boolean' }, lines: { type: 'integer' }, catalog_entries: { type: 'integer' }, units: { type: 'integer' }, figures: { type: 'integer' },
    qa: { type: 'object', properties: { runs: { type: 'integer' }, automatic_passed: { type: 'string' }, violations: { type: 'array', items: { type: 'string' } }, candidates_kept: { type: 'array', items: { type: 'string' } } }, required: ['runs', 'automatic_passed', 'violations', 'candidates_kept'] },
    scope_left_out: { type: 'array', items: { type: 'string' } }, unreproduced_hints: { type: 'array', items: { type: 'string' } }, open_issues: { type: 'array', items: { type: 'object', properties: { kind: { type: 'string', enum: ['Not cross-checked', 'Code not shown', 'Simplified', 'Taken as given', 'form'] }, place: { type: 'string' }, issue: { type: 'string' } }, required: ['kind', 'place', 'issue'] } }, tooling: { type: 'string' },
  },
  required: ['page', 'built_with_expand', 'lines', 'catalog_entries', 'units', 'figures', 'qa', 'scope_left_out', 'unreproduced_hints', 'open_issues', 'tooling'],
}
const PROOFREAD_REPORT = {
  type: 'object',
  properties: {
    changed: { type: 'array', items: { type: 'object', properties: { rule: { type: 'string' }, line: { type: 'integer' }, what: { type: 'string' } }, required: ['rule', 'line', 'what'] } },
    clean: { type: 'array', items: { type: 'string' } },
    left: { type: 'array', items: { type: 'object', properties: { rule: { type: 'string' }, line: { type: 'integer' }, reason: { type: 'string' } }, required: ['rule', 'line', 'reason'] } },
    qa: { type: 'object', properties: { runs: { type: 'integer' }, automatic_passed: { type: 'string' }, violations: { type: 'array', items: { type: 'string' } } }, required: ['runs', 'automatic_passed', 'violations'] },
    commands: { type: 'integer' },
    notes: { type: 'string' },
  },
  required: ['changed', 'clean', 'left', 'qa', 'commands', 'notes'],
}

// the run's output tokens so far, main loop and every agent, for the narrator line after each page (the host's task panel shows each agent's own)
const spent = () => `${(budget.spent() / 1e6).toFixed(1)}M output tokens`
const write = (id) => agent(writerPrompt(paths(id)), { label: `write:${id}`, phase: 'Write', schema: WRITER, model: MODEL, effort: EFFORT })
  .then(w => { log(w ? `${id}: written, ${w.lines} lines, ${w.qa.automatic_passed.slice(0, 80)}, violations ${w.qa.violations.length}, open issues ${w.open_issues.length}; ${spent()} spent so far` : `${id}: the writer returned nothing; ${spent()} spent so far`); return w })
const proofread = (id, w) => agent(proofreadPrompt(paths(id), w), { label: `proofread:${id}`, phase: 'Proofread', schema: PROOFREAD_REPORT, model: MODEL, effort: EFFORT })
  .then(v => { log(v ? `${id}: proofread, changed ${v.changed.length}, left ${v.left.length}, ${v.qa.automatic_passed.slice(0, 80)}, ${v.commands} commands; ${spent()} spent so far` : `${id}: the proofreader returned nothing; ${spent()} spent so far`); return v })

if (stage === 'write') {
  const results = await parallel(pages.map(id => () => write(id).then(w => ({ id, w }))))
  return results.filter(Boolean).map(r => ({ page: r.id, writer: r.w }))
}
if (stage === 'proofread') {
  const reports = args_.writerReports || {}
  const results = await parallel(pages.map(id => () => proofread(id, reports[id] || null).then(v => ({ id, v }))))
  return results.filter(Boolean).map(r => ({ page: r.id, proofread: r.v }))
}
if (stage === 'both') {
  const results = await pipeline(pages, async (id) => ({ id, w: await write(id) }), async (r) => ({ ...r, v: r.w ? await proofread(r.id, r.w) : null }))
  return results.filter(Boolean).map(r => ({ page: r.id, writer: r.w, proofread: r.v }))
}
throw new Error('the stage must be "write", "proofread", "both" or "prepare"')
