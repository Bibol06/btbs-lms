// Content-title helpers (QA-040..042). Mirrors backend/learning/naming.py for upload titles.
import { t as tr } from './i18n/language'

const QUALITY = /\b(?:\d{3,4}p|[hx]\.?26[45]|hevc|hd|fhd|uhd|4k|60fps|30fps)\b/gi

/** Readable title suggested from an uploaded file name (no extension, underscores, 360p/h264). */
export function readableTitle(filename: string) {
  const stem = filename.replace(/^.*[\\/]/, '').replace(/\.[^.]+$/, '')
  const text = stem.replace(/_+/g, ' ').replace(QUALITY, '')
    .replace(/\(\s*[,;\s]*\)|\[\s*[,;\s]*\]/g, '').replace(/\s+([,;.)\]])/g, '$1')
    .replace(/\s{2,}/g, ' ').replace(/^[\s\-–—_.,;]+|[\s\-–—_.,;]+$/g, '')
  return (text || stem).slice(0, 200)
}

/** Soft warnings shown to authors; they never block saving. */
export function titleWarnings(title: string, siblings: string[] = []) {
  const value = title.trim()
  const warnings: string[] = []
  if (!value) return warnings
  if (/^\d+[.)]?$/.test(value)) warnings.push(tr('Название состоит только из цифр — ученик не поймёт, о чём шаг.'))
  if (/\.(mp4|webm|mov|pdf|docx?|pptx?|zip)$/i.test(value) || /\b(\d{3,4}p|h26[45]|x26[45])\b/i.test(value) || /\w_\w+_\w/.test(value)) {
    warnings.push(tr('Название похоже на имя файла. Предлагаем: «{0}».', [readableTitle(value)]))
  }
  if (siblings.some(other => other.trim().toLowerCase() === value.toLowerCase())) warnings.push(tr('В этом уроке уже есть шаг с таким названием.'))
  return warnings
}
