import { useEffect, useState } from 'react'
import { apiRequest } from '../../api'
import { ct } from '../../i18n/content'
import { t } from '../../i18n/language'
import { errorMessage, formatDate } from '../study/types'

export type ReadinessIssue = { scope: string; id: number; title: string; reason: string; date: string | null; message: string; level: string }
type Readiness = { is_published: boolean; summary: { modules: number; lessons: number; steps: number; published_steps: number; available_steps: number; blocking_count: number; ready_now: boolean }; issues: ReadinessIssue[] }

export default function CourseReadiness({ courseId, runId, compact, revision, onChanged, onDetails, onEditIssue }: {
  courseId: number; runId: number; compact?: boolean; revision: number; onChanged: () => void; onDetails: () => void; onEditIssue: (issue: ReadinessIssue) => void
}) {
  const [data, setData] = useState<Readiness | null>(null)
  const [error, setError] = useState(''), [busy, setBusy] = useState(false)
  useEffect(() => {
    let alive = true
    apiRequest<Readiness>(`/api/courses/${courseId}/readiness/?run_id=${runId}`).then(result => { if (alive) { setData(result); setError('') } }).catch(err => { if (alive) setError(errorMessage(err)) })
    return () => { alive = false }
  }, [courseId, runId, revision])
  async function act(path: string, body: unknown) {
    setBusy(true); setError('')
    try { const result = await apiRequest<{ readiness: Readiness }>(`/api/courses/${courseId}/${path}?run_id=${runId}`, 'POST', body); setData(result.readiness); onChanged() }
    catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }
  if (compact) {
    if (!data || (data.summary.ready_now && data.summary.blocking_count === 0)) return null
    const scheduled = data.issues.find(issue => issue.reason === 'module_scheduled')
    return <aside className="course-readiness-banner"><div><strong>{t('Проверьте доступ ученика')}</strong><p>{scheduled?.date ? t('Модуль откроется {0}. До этой даты ученик видит замок.', [formatDate(scheduled.date)]) : t('Часть материалов ещё не готова к прохождению.')}</p></div><button className="secondary" onClick={onDetails}>{t('Проверить доступ')}</button></aside>
  }
  return <section className="course-readiness-panel"><div className="section-heading"><div><p className="eyebrow">{t('Перед началом обучения')}</p><h2>{t('Готовность и публикация')}</h2></div><button disabled={busy || !data} onClick={() => act('publish/', { scope: 'course', include_descendants: true })}>{t('Опубликовать готовые материалы')}</button></div>
    {error && <p className="error" role="alert">{t(error)}</p>}
    {!data && !error && <p role="status">{t('Проверяем курс…')}</p>}
    {data && <><div className="course-readiness-metrics"><div><strong>{data.summary.modules}</strong><span>{t('Модулей')}</span></div><div><strong>{data.summary.lessons}</strong><span>{t('Уроков')}</span></div><div><strong>{data.summary.available_steps}/{data.summary.steps}</strong><span>{t('Шагов доступно сейчас')}</span></div></div>
      
      {!data.issues.length && <p className="empty-state">{t('Проверка завершена: препятствий не найдено.')}</p>}
      <div className="readiness-issues">{data.issues.map((issue, index) => <article className={`readiness-issue ${issue.level}`} key={`${issue.scope}-${issue.id}-${issue.reason}-${index}`}><div><strong>{ct(issue, 'title')}</strong><p>{t(issue.message)}</p>{issue.date && <time>{formatDate(issue.date)}</time>}</div><div className="action-row">
        {issue.reason === 'module_scheduled' && <button className="secondary" disabled={busy} onClick={() => act(`modules/${issue.id}/open-now/`, {})}>{t('Открыть сейчас')}</button>}
        {['module_draft', 'lesson_draft'].includes(issue.reason) && <button className="secondary" disabled={busy} onClick={() => act('publish/', { scope: issue.scope, target_id: issue.id, include_descendants: true })}>{t('Опубликовать с содержимым')}</button>}
        {['missing_content', 'quiz_empty', 'empty_course', 'published_empty', 'lesson_empty', 'step_draft'].includes(issue.reason) && <button className="secondary" onClick={() => onEditIssue(issue)}>{t('Открыть содержание')}</button>}
      </div></article>)}</div>
    </>}
  </section>
}
