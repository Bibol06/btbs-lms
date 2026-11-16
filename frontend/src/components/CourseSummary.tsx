import { ct } from '../i18n/content'
import { t } from '../i18n/language'
import './CourseSummary.css'

export default function CourseSummary({ course, courseId, showLink = true }: {
  course: unknown; courseId: number; showLink?: boolean
}) {
  const description = ct(course, 'description')
    .replace(/!\[[^\]\n]*\]\([^)\n]+\)/g, '')
    .replace(/\[([^\]\n]+)\]\([^)\n]+\)/g, '$1')
    .replace(/^#{1,3}\s+/gm, '').replace(/\*\*([^*\n]+)\*\*/g, '$1')
    .replace(/`([^`\n]+)`/g, '$1').replace(/\s+/g, ' ').trim()
  return <div className="btbs-course-summary">
    {description && <p className="btbs-course-description">{description}</p>}
    {showLink && <a className="btbs-course-about" href={`#course=${courseId}&tab=overview`}>{t('О курсе')}</a>}
  </div>
}
