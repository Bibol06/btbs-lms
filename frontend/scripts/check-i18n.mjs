// i18n guard for CI: catalogs complete and identical, no Russian UI text outside tr().
//   node scripts/check-i18n.mjs
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const frontend = fileURLToPath(new URL('..', import.meta.url))
const client = JSON.parse(readFileSync(join(frontend, 'src/i18n/messages.json'), 'utf-8'))
const server = JSON.parse(readFileSync(join(frontend, '../backend/locales/messages.json'), 'utf-8'))
const problems = []

for (const [source, variants] of Object.entries(client)) {
  if (!Array.isArray(variants) || variants.length !== 2 || variants.some(v => typeof v !== 'string' || !v.trim())) problems.push(`catalog: "${source}" needs non-empty kk and en`)
  const slots = (text) => (text.match(/\{\d+\}/g) || []).sort().join()
  if (Array.isArray(variants) && variants.some(v => slots(v) !== slots(source))) problems.push(`catalog: "${source}" placeholders differ in a translation`)
}
const keys = (o) => Object.keys(o).sort().join('\n')
if (keys(client) !== keys(server)) problems.push('catalog: frontend/src/i18n/messages.json and backend/locales/messages.json have different keys')

// JSX text nodes with Russian letters that are not wrapped in tr()/t(). Language names are intentional.
const allowed = new Set(['Русский', 'Қазақша'])
const walk = (dir) => readdirSync(dir).flatMap(name => { const path = join(dir, name); return statSync(path).isDirectory() ? walk(path) : [path] })
for (const file of walk(join(frontend, 'src')).filter(f => f.endsWith('.tsx'))) {
  const text = readFileSync(file, 'utf-8')
  for (const match of text.matchAll(/>([^<>{}]*[А-Яа-яЁё][^<>{}]*)</g)) {
    const value = match[1].trim()
    if (value && !allowed.has(value)) problems.push(`${relative(frontend, file)}: text "${value.slice(0, 60)}" is not wrapped in tr()`)
  }
}

if (problems.length) {
  console.error(problems.join('\n'))
  process.exit(1)
}
console.log(`i18n OK: ${Object.keys(client).length} catalog entries, no raw Russian JSX text`)
