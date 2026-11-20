// CSS guard (redesign phase 7): design values come from src/styles/tokens.css.
// Fails on raw hex colors, raw font sizes and !important anywhere else in src/**/*.css.
// A line may opt out with the comment `css-guard: allow` (reduced-motion and visually-hidden only).
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('../src/', import.meta.url))
const allowed = new Set(['styles/tokens.css'])
const rules = [
  [/#[0-9a-fA-F]{3,8}\b/, 'raw hex color (use a color token)'],
  [/font-size\s*:\s*[\d.]+(px|rem)\b/, 'raw font-size in px/rem (use --fs-*; em is fine for inline scaling)'],
  [/!important/, '!important'],
]

function walk(dir) {
  return readdirSync(dir).flatMap(name => {
    const path = join(dir, name)
    return statSync(path).isDirectory() ? walk(path) : path.endsWith('.css') ? [path] : []
  })
}

const problems = []
for (const file of walk(root)) {
  const name = relative(root, file).split(sep).join('/')
  if (allowed.has(name)) continue
  readFileSync(file, 'utf8').split('\n').forEach((line, index) => {
    if (line.includes('css-guard: allow')) return
    const code = line.replace(/\/\*.*?\*\//g, '')
    for (const [pattern, message] of rules) if (pattern.test(code)) problems.push(`${name}:${index + 1}: ${message}: ${line.trim().slice(0, 100)}`)
  })
}
if (problems.length) {
  console.error(problems.join('\n'))
  console.error(`\nCSS guard: ${problems.length} problem(s). Use tokens from src/styles/tokens.css.`)
  process.exit(1)
}
console.log('CSS guard OK: no raw colors, raw font sizes or !important outside tokens.css')
