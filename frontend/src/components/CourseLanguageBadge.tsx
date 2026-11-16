import { t } from '../i18n/language'
import type { CourseLanguagePolicy } from '../i18n/content'
import './CourseLanguageBadge.css'

const names: Record<string, string> = { ru: 'Русский', kk: 'Қазақша', en: 'English' }
export default function CourseLanguageBadge({ course }: { course: unknown }) {
  if (!course || typeof course !== 'object') return null
  const data = course as { _course_policy?: CourseLanguagePolicy; content_language?: string; content_translation?: string }
  const policy = data._course_policy || (data.content_language ? { language: data.content_language, mode: data.content_translation || 'original' } : null)
  if (!policy) return null
  return <span className="course-language-badge" title={policy.mode === 'original' ? t('Содержимое сохраняет язык курса') : t('Доступны подготовленные переводы')}>
    <span>{t('Язык курса:')}</span> <strong className="notranslate" translate="no" lang={policy.language === 'other' ? undefined : policy.language}>{names[policy.language] || t('Другой язык')}</strong>
    {policy.mode === 'localized' && <small> · {t('Мультиязычный')}</small>}
  </span>
}
