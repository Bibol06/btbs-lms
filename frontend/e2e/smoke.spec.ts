// Permanent UI smoke suite (npm run e2e). Needs the QA environment: tools/qa/start_qa.ps1 (or the CI e2e job).
// Every page below is opened at 1440 and 390 px and must pass the UI audit ("UI linter").
import { expect, test, type Page } from '@playwright/test'
import { audit, settle, watch, type Finding } from './support/audit'
import { qa, signIn, type Role } from './support/qa'

const c = qa.courses, r = qa.runs, s = qa.steps
const pages: [Role, string, string][] = [
  ['guest', 'catalog', '#page=catalog'],
  ['guest', 'course card', `#course=${c.main}`],
  ['student', 'catalog', '#page=catalog'],
  ['teacher', 'catalog', '#page=catalog'],
  ['student', 'my learning', '#page=learning'],
  ['student', 'deadlines', '#page=deadlines'],
  ['student', 'notifications', '#page=notifications'],
  ['student', 'profile', '#profile=me'],
  ['student', 'results', `#course=${c.main}&run=${r.cohort}&tab=results`],
  ['student', 'learning plan', `#course=${c.main}&run=${r.cohort}&tab=plan`],
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

test('catalog: search, "my courses" filter and progress on enrolled cards', async ({ page }) => {
  await signIn(page, 'student', 'ru')
  await open(page, '#page=catalog')
  const cards = page.locator('.catalog-card:not(.catalog-skeleton)')
  await expect(cards).not.toHaveCount(0)
  const total = await cards.count()
  // Enrolled cards link to the run their progress belongs to.
  const main = cards.filter({ has: page.locator(`a[href^="#course=${c.main}&run="]`) })
  await expect(main.getByRole('progressbar')).toHaveCount(1)
  await page.getByRole('searchbox', { name: 'Поиск курсов' }).fill('нет-такого-курса-xyz')
  await expect(page.getByRole('heading', { name: 'Ничего не найдено' })).toBeVisible()
  await expect(page).toHaveURL(/q=/)
  await page.getByRole('button', { name: 'Сбросить фильтры' }).first().click()
  await expect(cards).toHaveCount(total)
  await expect(page.getByRole('searchbox', { name: 'Поиск курсов' })).toBeFocused()
  await page.getByRole('button', { name: 'Мои курсы' }).click()
  await expect(page).toHaveURL(/show=mine/)
  const mine = await cards.count()
  expect(mine).toBeGreaterThan(0)
  expect(mine).toBeLessThan(total)
  // Filters survive opening a course and coming back through the menu.
  await main.locator('h3 a').click()
  await expect(page).toHaveURL(new RegExp(`#course=${c.main}&run=`))
  await open(page, '#page=catalog')
  await expect(page.getByRole('button', { name: 'Мои курсы' })).toHaveAttribute('aria-pressed', 'true')
  await expect(cards).toHaveCount(mine)
})

test('catalog: a shared "my courses" link does not hide courses from a guest', async ({ page }) => {
  await signIn(page, 'guest', 'ru')
  await open(page, '#page=catalog&show=mine&lang=xx')
  await expect(page.locator('.catalog-card:not(.catalog-skeleton)')).not.toHaveCount(0)
  await expect(page.getByRole('heading', { name: 'Ничего не найдено' })).toHaveCount(0)
})

test('my learning: Continue card, course filters and the ⋯ menu', async ({ page }) => {
  await signIn(page, 'student', 'ru')
  await open(page, '#page=learning')
  const resume = page.locator('.ml-continue:not(.ml-skeleton)')
  await expect(resume.getByRole('link', { name: 'Продолжить' })).toHaveAttribute('href', /#course=\d+&run=\d+/)
  await expect(resume.getByRole('progressbar')).toHaveCount(1)
  const cards = page.locator('.ml-card:not(.ml-skeleton)')
  await expect(cards).not.toHaveCount(0)
  await expect(page.getByRole('button', { name: /^Прохожу/ })).toHaveAttribute('aria-pressed', 'true')
  // Secondary actions live in the ⋯ menu; Escape closes it and returns focus.
  const trigger = cards.first().getByRole('button', { name: /Действия с курсом/ })
  await trigger.click()
  await expect(page.getByRole('menuitem', { name: 'О курсе' })).toBeFocused()
  await expect(page.getByRole('menuitem', { name: 'В архив' })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('menu')).toHaveCount(0)
  await expect(trigger).toBeFocused()
  await page.getByRole('button', { name: /^Архив/ }).click()
  await expect(page.getByRole('button', { name: /^Архив/ })).toHaveAttribute('aria-pressed', 'true')
})

test('deadlines: summary line, filter segment with counts and task links', async ({ page }) => {
  await signIn(page, 'student', 'ru')
  await open(page, '#page=deadlines')
  await expect(page.getByText(/Нужно выполнить: \d+ · на проверке: \d+ · на доработке: \d+/)).toBeVisible()
  const todo = page.getByRole('button', { name: /^Нужно выполнить/ })
  await expect(todo).toHaveAttribute('aria-pressed', 'true')
  const rows = page.locator('.agenda-list > li')
  await expect(rows).not.toHaveCount(0)
  await expect(rows.first().getByRole('link')).toHaveAttribute('href', /#course=\d+/)
  await page.getByRole('button', { name: /^Все/ }).click()
  await expect(page.getByRole('button', { name: /^Все/ })).toHaveAttribute('aria-pressed', 'true')
  expect(await rows.count()).toBeGreaterThan(0)
})
