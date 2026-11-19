// Full QA sweep: every page × role × width × language with the automatic audit.
// Results: .local/qa/sweep/results.jsonl; screenshots (ru, 1440 and 390): .local/qa/screens/.
// Run: npm run e2e:sweep   (needs tools/qa/start_qa.ps1)
import { appendFileSync, mkdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { test } from '@playwright/test'
import { audit, settle, watch } from './support/audit'
import { root, signIn, type Language } from './support/qa'
import { visits } from './support/sitemap'

// Layout checks need every width in one language; translations are width-independent.
const widthsFor = (language: Language) => language === 'ru' ? [1440, 1024, 768, 390] : [1440]
const languages: Language[] = ['ru', 'kk', 'en']
const out = resolve(root, '.local/qa/sweep')
const shots = resolve(root, '.local/qa/screens')
mkdirSync(out, { recursive: true })

for (const visit of visits) {
  for (const language of languages) {
    test(`${visit.role} ${visit.label} ${language}`, async ({ page }) => {
      await signIn(page, visit.role, language)
      for (const width of widthsFor(language)) {
        const started = Date.now()
        await page.setViewportSize({ width, height: width < 600 ? 844 : 900 })
        const findings = watch(page)
        // A hash-only change does not reload the SPA; start from a blank page so the app
        // boots with the signed-in session and the profile language.
        await page.goto('about:blank')
        await page.goto('/' + visit.hash)
        await settle(page)
        const screenshot = language === 'ru' && (width === 1440 || width === 390) ? resolve(shots, visit.role, `${visit.label}-${width}.png`) : ''
        if (screenshot) { mkdirSync(resolve(shots, visit.role), { recursive: true }); await page.screenshot({ path: screenshot, fullPage: true }) }
        findings.push(...await audit(page, language, language === 'ru' && (width === 1440 || width === 390), language === 'ru' && width === 1440))
        appendFileSync(resolve(out, 'results.jsonl'), JSON.stringify({ role: visit.role, label: visit.label, hash: visit.hash, width, language, screenshot, ms: Date.now() - started, findings }) + '\n')
        page.removeAllListeners('console'); page.removeAllListeners('pageerror'); page.removeAllListeners('response')
      }
    })
  }
}
