// Permanent UI smoke suite (npm run e2e). Needs the QA environment: tools/qa/start_qa.ps1 (or the CI e2e job).
// Every page below is opened at 1440 and 390 px and must pass the UI audit ("UI linter").
import { expect, test, type Page } from '@playwright/test'
import { audit, settle, watch, type Finding } from './support/audit'
import { qa, signIn, type Role } from './support/qa'

const c = qa.courses, r = qa.runs, s = qa.steps
const pages: [Role, string, string][] = [
  ['guest', 'catalog', '#page=catalog'],
  ['guest', 'course card', `#course=${c.main}`],
  ['student', 'my learning', '#page=learning'],
  ['student', 'deadlines', '#page=deadlines'],
  ['student', 'course start page', `#course=${c.main}&run=${r.cohort}&tab=lessons`],
  ['student', 'player: text', `#course=${c.main}&run=${r.cohort}&step=${s.text}`],
  ['student', 'player: quiz', `#course=${c.main}&run=${r.cohort}&step=${s.quiz}`],
  ['student', 'player: code', `#course=${c.main}&run=${r.cohort}&step=${s.code}`],
  ['student', 'long titles course', `#course=${c.edge}&run=${r.edge}&tab=lessons`],
  ['teacher', 'my courses', '#page=teaching'],
  ['teacher', 'course editor', `#course=${c.main}&run=${r.cohort}&tab=lessons`],
  ['teacher', 'long titles editor', `#course=${c.edge}&run=${r.edge}&tab=lessons`],
  ['teacher', 'student preview', `#page=preview&course_id=${c.edge}&run_id=${r.edge}`],
  ['teacher', 'groups', `#course=${c.main}&run=${r.cohort}&tab=groups`],
  ['teacher', 'analytics', '#page=analytics'],
  ['admin_full', 'users', '#page=users'],
  ['admin_full', 'overview', '#page=admin'],
]

// Problems that fail the build. Data smells (digit or file-name titles) are reported, not failed:
// the QA seed deliberately contains them.
const blocking = new Set(['page-exception', 'console-error', 'http-error', 'horizontal-scroll', 'text-off-screen', 'text-outside-card',
  'text-clipped-no-ellipsis', 'raw-value', 'duplicate-label', 'broken-image', 'video-error', 'video-no-metadata', 'axe-serious', 'axe-critical'])
// Expected responses: the guest session probe and a locked step.
const expected = (url: string, status: number) => (status === 401 && url.includes('/api/auth/me/')) || (status === 403 && url.includes(`/api/learning/steps/${s.locked}/`))

async function open(page: Page, hash: string) {
  await page.goto('about:blank')
  await page.goto('/' + hash)
  await settle(page)
}

for (const [role, label, hash] of pages) {
  test(`UI audit · ${role} · ${label}`, async ({ page }) => {
    await signIn(page, role, 'ru')
    const problems: (Finding & { width: number })[] = []
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: width < 600 ? 844 : 900 })
      const findings = watch(page, expected)
      await open(page, hash)
      findings.push(...await audit(page, 'ru', true, width === 1440))
      problems.push(...findings.filter(f => blocking.has(f.check) && !(f.check === 'console-error' && /status of (401|403)/.test(f.detail))).map(f => ({ ...f, width })))
      page.removeAllListeners('console'); page.removeAllListeners('pageerror'); page.removeAllListeners('response')
    }
    expect(problems, JSON.stringify(problems, null, 2)).toEqual([])
  })
}

test('student: "Got it!" completes a reading step and opens the next one', async ({ page }) => {
  await signIn(page, 'student', 'ru')
  await open(page, `#course=${c.main}&run=${r.cohort}&step=${s.text}`)
  await expect(page.locator('.player-article h1')).toHaveText('Что такое Python')
  await page.locator('.player-got-it').click()
  await expect(page).toHaveURL(new RegExp(`step=${s.video}`))
  await expect(page.locator('.lesson-player .player-segments button').first()).toHaveClass(/is-done/)
})

test('student: practice run shows program output', async ({ page }) => {
  await signIn(page, 'student', 'ru')
  await open(page, `#course=${c.main}&run=${r.cohort}&step=${s.code}`)
  await page.locator('.practice-tabs button', { hasText: 'Ввод' }).click()
  await page.locator('.practice-input textarea').fill('2\n3\n')
  await page.locator('.code-editor-host .cm-content').click()
  await page.keyboard.press('Control+End')
  await page.keyboard.type('\nprint(a + b)')
  await page.locator('.practice-editor-actions button', { hasText: 'Запустить' }).click()
  await expect(page.locator('.practice-output pre').first()).toHaveText('5', { timeout: 60_000 })
})

test('teacher: preview numbers steps uniquely even when titles repeat', async ({ page }) => {
  await signIn(page, 'teacher', 'ru')
  await open(page, `#page=preview&course_id=${c.edge}&run_id=${r.edge}`)
  const labels = await page.locator('.preview-outline button small').allInnerTexts()
  expect(labels.length).toBeGreaterThan(1)
  expect(new Set(labels).size).toBe(labels.length)
})
