import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import type { Page } from '@playwright/test'

export type Role = 'guest' | 'student' | 'student_empty' | 'teacher' | 'editor' | 'group_teacher' | 'admin_full' | 'admin_learning' | 'admin_system'
export type Language = 'ru' | 'kk' | 'en'

type Access = {
  password: string
  accounts: Record<string, string>
  courses: Record<'main' | 'edge' | 'empty' | 'draft', number>
  runs: Record<'self_paced' | 'cohort' | 'edge', number>
  steps: Record<string, number>
  lessons: Record<string, number>
  problem: number; quiz: number; assignment: number
}

export const root = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..')
export const qa: Access = JSON.parse(readFileSync(resolve(root, '.local/qa/qa-accounts.json'), 'utf-8'))
export const catalog: Record<string, [string, string]> = JSON.parse(readFileSync(resolve(root, 'frontend/src/i18n/messages.json'), 'utf-8'))

/** Sign in through the API (same CSRF flow as the app) and set the interface language on the profile. */
export async function signIn(page: Page, role: Role, language: Language) {
  await page.goto('/')
  await page.evaluate(lang => { localStorage.setItem('btbs.language', lang) }, language)
  if (role === 'guest') return
  const csrf = async () => {
    await page.request.get('/api/auth/csrf/')
    const cookies = await page.context().cookies()
    return cookies.find(cookie => cookie.name === 'csrftoken')?.value ?? ''
  }
  // Reuse one session per role: dozens of password logins in a row trip the login guard (403),
  // which is the guard working, not a UI failure.
  const sessionFile = resolve(root, '.local/qa/auth', `${role}.json`)
  if (existsSync(sessionFile)) {
    await page.context().addCookies(JSON.parse(readFileSync(sessionFile, 'utf-8')))
    if (!(await page.request.get('/api/auth/me/')).ok()) await page.context().clearCookies()
  }
  if (!(await page.request.get('/api/auth/me/')).ok()) {
    const login = await page.request.post('/api/auth/login/', { headers: { 'X-CSRFToken': await csrf() }, data: { username: qa.accounts[role], password: qa.password } })
    if (!login.ok()) throw new Error(`login ${role}: ${login.status()}`)
    mkdirSync(dirname(sessionFile), { recursive: true })
    writeFileSync(sessionFile, JSON.stringify(await page.context().cookies()))
  }
  const saved = await page.request.patch('/api/auth/preferences/', { headers: { 'X-CSRFToken': await csrf() }, data: { language } })
  if (!saved.ok()) throw new Error(`language ${role}: ${saved.status()}`)
}
