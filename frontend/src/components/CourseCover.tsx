import './CourseCover.css'

/** Decorative BTBS artwork; course data and original brand assets are untouched. */
export default function CourseCover({ courseId, title, compact = false }: {
  courseId: number; title: string; compact?: boolean
}) {
  const words = title.match(/[\p{L}\p{N}+#]+/gu) ?? []
  const initials = /Python/i.test(title) ? 'Py' : /C\+\+/i.test(title) ? 'C++' :
    words.slice(0, 2).map(word => [...word][0]).join('').toUpperCase() || 'BT'
  return <div className={`btbs-course-cover ${compact ? 'btbs-course-cover-compact' : ''}`} data-tone={courseId % 3} aria-hidden="true" translate="no">
    <svg className="btbs-course-cover-pattern" viewBox="0 0 340 140" fill="none">
      <circle cx="273" cy="58" r="76" /><circle cx="273" cy="58" r="48" />
      <path d="M195 105 231 62 283 97 316 44M231 62 263 26 316 44M263 26 283 97" />
      <circle cx="195" cy="105" r="5" /><circle cx="231" cy="62" r="7" /><circle cx="283" cy="97" r="6" /><circle cx="316" cy="44" r="5" /><circle cx="263" cy="26" r="4" />
    </svg>
    <span className="btbs-course-cover-brand" lang="en">BTBS</span>
    <strong className="btbs-course-cover-initials">{initials}</strong>
  </div>
}
