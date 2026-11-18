import AxeBuilder from '@axe-core/playwright'
import type { Page } from '@playwright/test'
import { catalog, type Language } from './qa'

export type Finding = { check: string; detail: string; sample?: string }

/** Collects console errors, uncaught exceptions and failed API calls while a page is used. */
export function watch(page: Page, expectedStatuses: (url: string, status: number) => boolean = () => false) {
  const findings: Finding[] = []
  trackApi(page)
  page.on('console', message => {
    if (message.type() === 'error' || message.type() === 'warning') {
      const text = message.text()
      if (/Download the React DevTools|\[vite\]/.test(text)) return
      findings.push({ check: message.type() === 'error' ? 'console-error' : 'console-warning', detail: text.slice(0, 300) })
    }
  })
  page.on('pageerror', error => findings.push({ check: 'page-exception', detail: String(error.message).slice(0, 300) }))
  page.on('response', response => {
    const url = response.url(), status = response.status()
    if (status >= 400 && /\/api\//.test(url) && !expectedStatuses(url, status)) findings.push({ check: 'http-error', detail: `${status} ${new URL(url).pathname}` })
  })
  return findings
}

const pendingApi = new WeakMap<Page, Set<object>>()

function trackApi(page: Page) {
  if (pendingApi.has(page)) return pendingApi.get(page)!
  const pending = new Set<object>()
  pendingApi.set(page, pending)
  page.on('request', request => { if (request.url().includes('/api/')) pending.add(request) })
  const done = (request: object) => pending.delete(request)
  page.on('requestfinished', done)
  page.on('requestfailed', done)
  return pending
}

/** Wait until the page has rendered its data. The app polls (notifications, presence), so
 *  "network idle" never happens; instead wait for a 500 ms window without pending API calls
 *  and for loaders ("Загрузка…") to disappear. */
export async function settle(page: Page) {
  const pending = trackApi(page)
  await page.waitForLoadState('load')
  const deadline = Date.now() + 8_000
  let quietSince = 0
  while (Date.now() < deadline) {
    if (pending.size === 0) { quietSince ||= Date.now(); if (Date.now() - quietSince >= 500) break }
    else quietSince = 0
    await page.waitForTimeout(100)
  }
  await page.waitForFunction(() => !/Загрузка|Loading|Жүктелу/.test(document.body.innerText), null, { timeout: 3_000 }).catch(() => undefined)
  await page.waitForTimeout(300)
}

/** In-page layout/text checks. Runs in the browser; keep it dependency-free. */
async function domChecks(page: Page) {
  return page.evaluate(() => {
    const out: { check: string; detail: string; sample?: string }[] = []
    const visible = (el: Element) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' }
    const path = (el: Element) => { const parts: string[] = []; let node: Element | null = el; for (let i = 0; node && i < 4; i++, node = node.parentElement) parts.unshift(node.tagName.toLowerCase() + (node.classList.length ? '.' + [...node.classList].slice(0, 2).join('.') : '')); return parts.join(' > ') }
    const doc = document.documentElement
    if (doc.scrollWidth > doc.clientWidth + 1) out.push({ check: 'horizontal-scroll', detail: `page ${doc.scrollWidth}px > viewport ${doc.clientWidth}px` })
    const skip = (el: Element) => Boolean(el.closest('.cm-editor, textarea, pre, code, svg, iframe, video, .practice-output'))
    const textEls = [...document.body.querySelectorAll('*')].filter(el => !skip(el) && visible(el) && [...el.childNodes].some(n => n.nodeType === 3 && n.textContent!.trim()))
    for (const el of textEls) {
      const r = el.getBoundingClientRect(), s = getComputedStyle(el)
      const text = (el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 80)
      if (r.right > window.innerWidth + 1 && !el.closest('[style*="overflow"], .table-scroll, .management-table-wrap')) out.push({ check: 'text-off-screen', detail: path(el), sample: text })
      const clipped = el.scrollWidth > el.clientWidth + 1 && ['hidden', 'clip'].includes(s.overflowX)
      if (clipped && s.textOverflow !== 'ellipsis') out.push({ check: 'text-clipped-no-ellipsis', detail: path(el), sample: text })
      if (clipped && s.textOverflow === 'ellipsis' && !el.closest('[title]') && !el.getAttribute('aria-label')) out.push({ check: 'ellipsis-without-title', detail: path(el), sample: text })
      // Text wider than a bordered/filled box it sits in (card spill).
      const box = el.parentElement?.closest('.card, .study-card, .course-card, .player-article, .course-plan-module, .player-modal, .lesson-content, .course-rail, .lesson-sidebar, .account-popover')
      if (box) { const b = box.getBoundingClientRect(); if (r.right > b.right + 2 || r.left < b.left - 2) out.push({ check: 'text-outside-card', detail: path(el), sample: text }) }
    }
    const bodyText = [...textEls].map(el => [...el.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join(' ')).join('\n')
    for (const token of bodyText.match(/\b(undefined|NaN)\b|\bnull\b|\[object Object\]|Invalid Date/g) ?? []) out.push({ check: 'raw-value', detail: token })
    // Identical labels among siblings in lists/navigation (e.g. two "шаг 1 · 1").
    for (const list of document.querySelectorAll('ul, ol, nav, [role=list], .course-plan-lesson, .step-strip, .player-segments, .lesson-sidebar, .module-outline')) {
      const labels = [...list.children].filter(visible).map(el => (el as HTMLElement).innerText?.trim().replace(/\s+/g, ' ')).filter(Boolean)
      const seen = new Set<string>()
      for (const label of labels) { if (seen.has(label)) out.push({ check: 'duplicate-label', detail: path(list), sample: label.slice(0, 80) }); seen.add(label) }
    }
    // Data-quality smells in visible titles.
    for (const el of document.querySelectorAll('h1, h2, h3, h4, strong, .course-plan-step-title, .lesson-item, .step-strip button, option')) {
      const t = (el.textContent || '').trim()
      if (!t || skip(el) || !visible(el)) continue
      if (/^\d+\.?$/.test(t)) out.push({ check: 'data-digits-title', detail: path(el), sample: t })
      if (/\.(mp4|webm|pdf|docx?|pptx?|zip)\b|\b(360p|480p|720p|1080p|h264|x264)\b|\w_\w+_\w/i.test(t)) out.push({ check: 'data-filename-title', detail: path(el), sample: t.slice(0, 80) })
    }
    for (const img of document.querySelectorAll('img')) if (visible(img) && img.complete && img.naturalWidth === 0) out.push({ check: 'broken-image', detail: img.getAttribute('src') || '' })
    // UI chrome strings for the translation check (authored content is excluded by selector choice).
    const chrome = [...document.querySelectorAll('button, label, th, [role=tab], .eyebrow, .muted, .sidebar nav, summary, .player-topbar, .course-plan-head')]
      .filter(el => visible(el) && !skip(el) && !el.closest('.course-plan-step, .lesson-item, .rich-content, .lesson-text, .course-card h3, .account-identity'))
      .map(el => ((el as HTMLElement).innerText || '').trim()).filter(t => t && t.length < 120)
    const attrs = [...document.querySelectorAll('[placeholder], [aria-label], [title]')].filter(visible).flatMap(el => ['placeholder', 'aria-label', 'title'].map(a => el.getAttribute(a) || '')).filter(Boolean)
    return { out, chrome: [...new Set([...chrome, ...attrs])] }
  })
}

async function mediaChecks(page: Page) {
  return page.evaluate(async () => {
    const out: { check: string; detail: string }[] = []
    for (const video of document.querySelectorAll('video')) {
      if (video.readyState < 1 && !video.error) await new Promise(done => { video.addEventListener('loadedmetadata', done, { once: true }); video.addEventListener('error', done, { once: true }); setTimeout(done, 6000) })
      if (video.error) out.push({ check: 'video-error', detail: `code ${video.error.code} ${video.currentSrc}` })
      else if (video.readyState < 1) out.push({ check: 'video-no-metadata', detail: video.currentSrc })
      else {
        video.muted = true
        try { await video.play(); await new Promise(done => setTimeout(done, 1500)); if (video.currentTime === 0) out.push({ check: 'video-does-not-play', detail: video.currentSrc }); video.pause() }
        catch (error) { out.push({ check: 'video-play-rejected', detail: String(error).slice(0, 160) }) }
      }
    }
    return out
  })
}

const cyrillic = /[А-Яа-яЁёӘәҒғҚқҢңӨөҰұҮүҺһІі]/
/** Russian UI strings left untranslated in kk/en. */
function translationFindings(strings: string[], language: Language): Finding[] {
  if (language === 'ru') return []
  const index = language === 'kk' ? 0 : 1
  const out: Finding[] = []
  for (const raw of strings) {
    for (const text of raw.split('\n').map(t => t.trim()).filter(Boolean)) {
      const entry = catalog[text]
      if (entry && entry[index] !== text) out.push({ check: 'untranslated', detail: text.slice(0, 100) })
      else if (!entry && language === 'en' && cyrillic.test(text)) out.push({ check: 'cyrillic-in-en', detail: text.slice(0, 100) })
    }
  }
  return out
}

export async function audit(page: Page, language: Language, withAxe: boolean, withMedia = true) {
  const { out, chrome } = await domChecks(page)
  const findings: Finding[] = [...out, ...(withMedia ? await mediaChecks(page) : []), ...translationFindings(chrome, language)]
  if (withAxe) {
    const result = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).exclude('.cm-editor').exclude('iframe').analyze()
    for (const v of result.violations.filter(v => v.impact === 'serious' || v.impact === 'critical')) {
      findings.push({ check: `axe-${v.impact}`, detail: `${v.id}: ${v.help}`, sample: v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | ') })
    }
  }
  return findings
}
