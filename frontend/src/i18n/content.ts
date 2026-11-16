import { getLanguage } from './language'

export type CourseLanguagePolicy = { language: 'ru' | 'kk' | 'en' | 'other'; mode: 'original' | 'localized' }
type Variants = Partial<Record<'ru' | 'kk' | 'en', string>>
type TextObject = { _text?: Record<string, Variants | (Variants | null)[]> }

/** Display-only translation: never use for form values, API payloads, identities or executable code. */
export function ct(source: unknown, field?: string, index?: number): string {
  let value: unknown = source
  let variants: Variants | null | undefined
  if (source && typeof source === 'object' && field) {
    value = (source as Record<string, unknown>)[field]
    const prepared = (source as TextObject)._text?.[field]
    if (index !== undefined) {
      value = Array.isArray(value) ? value[index] : undefined
      variants = Array.isArray(prepared) ? prepared[index] : undefined
    } else if (prepared && !Array.isArray(prepared)) variants = prepared
  }
  if (typeof value !== 'string' && typeof value !== 'number') return ''
  return variants?.[getLanguage()] ?? String(value)
}
