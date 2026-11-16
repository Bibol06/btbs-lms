import { ct } from '../../i18n/content'
import CourseCover from '../../components/CourseCover'
import { t as tr } from '../../i18n/language'
import WorkspaceHome from '../workspace/WorkspaceHome'
import { useEffect, useState, type FormEvent } from 'react'
import { apiRequest } from '../../api'
import { errorMessage, formatDate } from '../study/types'
import './MyLearning.css'

type LearningData = {
  enrollments: { id: number; course_id: number; course: string; run_id: number; run: string; kind: string; status: string; last_step_id: number | null; progress: { percent: number; completed: number; total: number }; pending: number; deadlines: { title: string; due_at: string; label: string }[]; available: boolean }[]
  bookmarks: { course_id: number; title: string; kind: string }[]
}

export default function MyLearning() {
  const [data, setData] = useState<LearningData | null>(null)
  const [filter, setFilter] = useState('active')
  const [revision, setRevision] = useState(0)
  const [error, setError] = useState('')
  useEffect(() => {
    let alive = true
    apiRequest<LearningData>('/api/courses/my-learning/').then(value => { if (alive) { setData(value); setError('') } }).catch(err => { if (alive) setError(errorMessage(err)) })
    return () => { alive = false }
  }, [revision])
  async function join(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const form = new FormData(e.currentTarget)
    try {
      const result = await apiRequest<{ course_id: number; run_id: number }>('/api/courses/join/', 'POST', { code: form.get('code') })
      window.location.hash = `course=${result.course_id}&run=${result.run_id}`
    } catch (err) { setError(errorMessage(err)) }
  }
  async function changeStatus(id: number, status: string) {
    try { await apiRequest(`/api/courses/enrollments/${id}/`, 'PATCH', { status }); setRevision(v => v + 1) }
    catch (err) { setError(errorMessage(err)) }
  }
  async function removeBookmark(courseId: number, kind: string) {
    try { await apiRequest(`/api/courses/${courseId}/bookmark/`, 'DELETE', { kind }); setRevision(v => v + 1) }
    catch (err) { setError(errorMessage(err)) }
  }
  if (!data) return <p role="status">{error || tr("Загрузка ваших курсов…")}</p>
  const rows = data?.enrollments.filter(e => e.status === filter || (filter === 'archived' && e.status === 'removed')) ?? []
  return <section className="study-section my-learning-page"><div className="section-heading"><div><p className="eyebrow">{tr("Личный кабинет ученика")}</p><h2>{tr("Моё обучение")}</h2></div><a className="button-link" href={`#page=deadlines${new URLSearchParams(location.hash.slice(1)).get('mode') === 'personal' ? '&mode=personal' : ''}`}>{tr("Все мои сроки, доработки и проверки →")}</a></div>
    <WorkspaceHome /><div className="learning-overview learning-overview-compact"><div><strong>{data.enrollments.filter(e => e.status === 'active').length}</strong><span>{tr("Прохожу сейчас")}</span></div><div><strong>{data.enrollments.filter(e => e.status === 'completed').length}</strong><span>{tr("Завершённых курсов")}</span></div><div><strong>{data.enrollments.reduce((sum, e) => sum + e.pending, 0)}</strong><span>{tr("Работ на проверке")}</span></div></div>
    <div className="course-tabs">{[['active', tr("Прохожу")], ['completed', tr("Завершённые")], ['favorite', tr("Избранное")], ['wishlist', tr("Хочу пройти")], ['archived', tr("Архив")]].map(([key, label]) => <button key={key} className={filter === key ? '' : 'secondary'} onClick={() => setFilter(key)}>{ct(label)}</button>)}</div>
    {error && <p className="error" role="alert">{tr(error)}</p>}
    <div className="my-learning-courses">{['favorite', 'wishlist'].includes(filter) ? <>
      {!data.bookmarks.some(bookmark => bookmark.kind === filter) && <p className="empty-state">{tr("В этом списке пока нет курсов.")}</p>}
      {data.bookmarks.filter(b => b.kind === filter).map(b => <article className="study-card learning-course-card" key={b.course_id}>
        <CourseCover courseId={b.course_id} title={ct(b, 'title')} compact />
        <div className="learning-course-body"><h3>{ct(b, "title")}</h3><a className="learning-course-about" href={`#course=${b.course_id}&tab=overview`}>{tr('О курсе')}</a><div className="action-row"><a className="primary-link" href={`/#course=${b.course_id}`}>{tr("Открыть курс")}</a><button className="secondary" onClick={() => removeBookmark(b.course_id, b.kind)}>{tr("Убрать из списка")}</button></div></div>
      </article>)}</> : <>
      {!rows.length && <p className="empty-state">{tr("В этом списке пока нет курсов.")}</p>}
      {rows.map(e => <article className="study-card learning-course-card" key={e.id}>
        <CourseCover courseId={e.course_id} title={ct(e, 'course')} compact />
        <div className="learning-course-body"><h3>{ct(e, "course")}</h3><p className="muted learning-course-group">{ct(e, "run")}</p><a className="learning-course-about" href={`#course=${e.course_id}&run=${e.run_id}&tab=overview`}>{tr('О курсе')}</a><progress max={100} value={e.progress.percent} aria-label={`${ct(e, 'course')}: ${e.progress.percent}%`} /><p>{tr("Пройдено ")}{e.progress.completed}/{e.progress.total} {tr(" обязательных шагов · ")}{e.progress.percent}%</p>
        {e.pending > 0 && <p>{tr("Работ на проверке: ")}{e.pending}</p>}{e.deadlines.map(d => <p className="muted" key={d.title}>{ct(d, "title")} — {tr(d.label).toLowerCase()}: {formatDate(d.due_at)}</p>)}
        <div className="action-row">{e.available && ['active', 'completed'].includes(e.status) && <a className="primary-link" href={`/#course=${e.course_id}&run=${e.run_id}${e.last_step_id ? `&step=${e.last_step_id}` : ''}`}>{e.status === 'completed' ? tr("Открыть пройденный курс") : tr("Продолжить обучение →")}</a>}{e.status === 'removed' ? <span>{tr("Доступ отозван преподавателем. Результаты сохранены.")}</span> : <button className="secondary" onClick={() => changeStatus(e.id, e.status === 'archived' ? 'active' : 'archived')}>{e.status === 'archived' ? tr("Вернуть в обучение") : tr("В архив")}</button>}</div>
        </div>
      </article>)}
    </>}</div>
    <details className="study-card"><summary>{tr("Есть код приглашения от преподавателя? Вступить в группу")}</summary><form className="study-form" onSubmit={join}><h3>{tr("Присоединиться к группе")}</h3><label>{tr("Код приглашения")}<input name="code" required maxLength={64} /></label><button>{tr("Вступить в группу")}</button></form></details>
  </section>
}
