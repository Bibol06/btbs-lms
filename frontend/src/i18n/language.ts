import { useSyncExternalStore } from 'react'
import messages from './messages.json'

export type Language = 'kk' | 'ru' | 'en'
export const languages: { code: Language; name: string; short: string; locale: string }[] = [
  { code: 'kk', name: 'Қазақша', short: 'ҚАЗ', locale: 'kk-KZ' },
  { code: 'ru', name: 'Русский', short: 'РУС', locale: 'ru-RU' },
  { code: 'en', name: 'English', short: 'ENG', locale: 'en-GB' },
]
const catalog: Record<string, string[]> = messages
const listeners = new Set<() => void>()
const valid = (value: unknown): value is Language => ['kk', 'ru', 'en'].includes(String(value))
const storageKey = 'btbs.language'
function stored(key: string) { try { return localStorage.getItem(key) } catch { return null } }
function remember(key: string, value: string) { try { localStorage.setItem(key, value) } catch { /* Private browsing can disable storage. */ } }
function initialLanguage(): Language {
  const saved = stored(storageKey)
  if (valid(saved)) return saved
  const browser = navigator.language.split('-')[0]
  return valid(browser) ? browser : 'ru'
}
let userId: number | null = null
let choiceRevision = 0
let saveQueue: Promise<void> = Promise.resolve()
let state: { language: Language; saving: boolean; error: boolean } = { language: initialLanguage(), saving: false, error: false }
function publish(next: Partial<typeof state>) {
  state = { ...state, ...next }
  document.documentElement.lang = state.language
  document.title = t('BTBS — образовательная платформа')
  document.querySelector('meta[name="description"]')?.setAttribute('content', t('BTBS — образовательная платформа. Курсы, практика, общение и прогресс обучения в одном пространстве.'))
  listeners.forEach(listener => listener())
}
document.documentElement.lang = state.language
export const getLanguage = () => state.language
export const getLanguageRevision = () => choiceRevision
export const getLocale = () => languages.find(item => item.code === state.language)!.locale
export function countLabel(count: number, kind: 'lesson' | 'question') {
  const forms = {
    lesson: { ru: { one: 'урок', few: 'урока', many: 'уроков', other: 'урока' }, kk: { other: 'сабақ' }, en: { one: 'lesson', other: 'lessons' } },
    question: { ru: { one: 'вопрос', few: 'вопроса', many: 'вопросов', other: 'вопроса' }, kk: { other: 'сұрақ' }, en: { one: 'question', other: 'questions' } },
  }
  const variants = forms[kind][state.language] as Record<string, string>
  const noun = variants[new Intl.PluralRules(getLocale()).select(count)] || variants.other
  return `${new Intl.NumberFormat(getLocale()).format(count)} ${noun}`
}
export function useLanguage() { return useSyncExternalStore(listener => { listeners.add(listener); return () => listeners.delete(listener) }, () => state) }
export function bindLanguageUser(id: number | null, preferred?: string, requestRevision = choiceRevision) {
  if (id === userId && requestRevision < choiceRevision) return
  userId = id
  const saved = id ? stored(`${storageKey}.${id}`) : stored(storageKey)
  const language = valid(preferred) ? preferred : valid(saved) ? saved : state.language
  remember(storageKey, language)
  if (id) remember(`${storageKey}.${id}`, language)
  publish({ language, saving: false, error: false })
  if (id && !valid(preferred)) void chooseLanguage(language)
}
export async function chooseLanguage(language: Language) {
  if (!valid(language)) return
  const revision = ++choiceRevision
  remember(storageKey, language)
  if (userId) remember(`${storageKey}.${userId}`, language)
  const actor = userId
  publish({ language, error: false, saving: Boolean(actor) })
  if (!actor) return
  saveQueue = saveQueue.catch(() => {}).then(async () => {
    if (userId !== actor || revision !== choiceRevision) return
    try {
      await fetch('/api/auth/csrf/', { credentials: 'include', signal: AbortSignal.timeout(8000) })
      const token = document.cookie.split('; ').find(value => value.startsWith('csrftoken='))?.slice(10) || ''
      const response = await fetch('/api/auth/preferences/', { method: 'PATCH', credentials: 'include', signal: AbortSignal.timeout(8000), headers: { 'Content-Type': 'application/json', 'X-CSRFToken': decodeURIComponent(token) }, body: JSON.stringify({ language }) })
      if (!response.ok) throw new Error('preferences')
      if (userId === actor && revision === choiceRevision) publish({ saving: false })
    } catch { if (userId === actor && revision === choiceRevision) publish({ saving: false, error: true }) }
  })
  await saveQueue
}
window.addEventListener('storage', event => {
  if (event.key === (userId ? `${storageKey}.${userId}` : storageKey) && valid(event.newValue)) publish({ language: event.newValue, error: false })
})

const normalize = (source: string) => source.replace(/\s+/g, ' ').trim()
const reverse = new Map<string, string>()
for (const [source, variants] of Object.entries(catalog)) for (const variant of variants) if (!reverse.has(variant)) reverse.set(variant, source)
const templates = Object.entries(catalog).filter(([source]) => /\{\d+\}/.test(source)).flatMap(([source, variants]) => [source, ...variants].map(variant => ({
  source,
  matcher: new RegExp('^' + variant.split(/(\{\d+\})/).map(part => /^\{\d+\}$/.test(part) ? '([\\s\\S]*?)' : part.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('') + '$'),
  slots: [...variant.matchAll(/\{(\d+)\}/g)].map(match => Number(match[1])),
})))
const sentenceParts = Object.entries(catalog).filter(([source]) => source.length > 30 && /[.!?]$/.test(source) && !/\{\d+\}/.test(source)).flatMap(([source, variants]) => [source, ...variants].map(text => ({ text, source }))).sort((a, b) => b.text.length - a.text.length)
/** System interface text. Use ct for content; never translate identities or executable code. */
export function t(source: string | null | undefined, values?: readonly unknown[]): string {
  if (source == null) return ''
  const key = normalize(source)
  let canonical = catalog[key] ? key : reverse.get(key) || key
  let entry = catalog[canonical], params = values
  if (!entry && !values) {
    for (const template of templates) {
      const match = key.match(template.matcher)
      if (!match) continue
      entry = catalog[template.source]
      canonical = template.source
      const found: string[] = []
      template.slots.forEach((slot, index) => { found[slot] = match[index + 1] })
      params = found
      break
    }
  }
  if (!entry) {
    if (values) return source.replace(/\{(\d+)\}/g, (_, index) => String(values[Number(index)] ?? ''))
    const punctuation = key.match(/^(.*?)([.!?]+)$/)
    if (punctuation && (catalog[punctuation[1]] || reverse.has(punctuation[1]))) return t(punctuation[1]) + punctuation[2]
    const prefix = sentenceParts.find(part => key.startsWith(part.text + ' '))
    if (prefix) return t(prefix.source) + ' ' + t(key.slice(prefix.text.length + 1))
    return source
  }
  const leading = source.match(/^\s*/)?.[0] || '', trailing = source.match(/\s*$/)?.[0] || ''
  const translated = state.language === 'ru' ? canonical : entry[state.language === 'kk' ? 0 : 1]
  const nestedNotice = canonical.startsWith('{0}. Результат:') || canonical.startsWith('{0} Результат:') || canonical.startsWith('{0}. Сохранённые ответы') || canonical.startsWith('Ответ не сохранён: {0}')
  return leading + translated.replace(/\{(\d+)\}/g, (_, index) => {
    const value = params?.[Number(index)]
    return value == null ? `{${index}}` : nestedNotice && Number(index) === 0 && typeof value === 'string' && value !== source ? t(value) : String(value)
  }) + trailing
}

/** Label dictionaries use getters so switching language also updates module-level labels. */
export function localizedLabels<T>(source: T): T {
  if (!source || typeof source !== 'object') return source
  for (const [key, value] of Object.entries(source)) {
    if (typeof value === 'string' && /[А-Яа-яЁё]/.test(value)) Object.defineProperty(source, key, { enumerable: true, configurable: true, get: () => t(value) })
    else if (value && typeof value === 'object') localizedLabels(value)
  }
  return source
}
document.title = t('BTBS — образовательная платформа')
document.querySelector('meta[name="description"]')?.setAttribute('content', t('BTBS — образовательная платформа. Курсы, практика, общение и прогресс обучения в одном пространстве.'))
