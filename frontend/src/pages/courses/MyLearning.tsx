import { ct } from '../../i18n/content'
import CourseCover from '../../components/CourseCover'
import MoreMenu, { type MoreMenuItem } from '../../components/MoreMenu'
import { t as tr } from '../../i18n/language'
import { StudentPanels } from '../workspace/WorkspaceHome'
import { useWorkspaceHome } from '../workspace/useWorkspaceHome'
import { useEffect, useState, type FormEvent } from 'react'
import { apiRequest } from '../../api'
import { errorMessage, formatDate } from '../study/types'
import './MyLearning.css'

type Enrollment = { id: number; course_id: number; course: string; run_id: number; run: string; kind: string; status: string; last_step_id: number | null; progress: { percent: number; completed: number; total: number }; pending: number; deadlines: { title: string; due_at: string; label: string }[]; available: boolean }
type Bookmark = { course_id: number; title: string; kind: string }
type LearningData = { enrollments: Enrollment[]; bookmarks: Bookmark[] }
type Filter = 'active' | 'completed' | 'favorite' | 'wishlist' | 'archived'

const FILTERS: [Filter, string][] = [['active', 'Прохожу'], ['completed', 'Завершённые'], ['favorite', 'Избранное'], ['wishlist', 'Хочу пройти'], ['archived', 'Архив']]

const inFilter = (e: Enrollment, filter: Filter) => e.status === filter || (filter === 'archived' && e.status === 'removed')
const studyLink = (e: Enrollment) => `#course=${e.course_id}&run=${e.run_id}${e.last_step_id ? `&step=${e.last_step_id}` : ''}`
const aboutLink = (e: Enrollment) => `#course=${e.course_id}&run=${e.run_id}&tab=overview`
const canStudy = (e: Enrollment) => e.available && ['active', 'completed'].includes(e.status)

function Progress({ e, label }: { e: Enrollment; label: string }) {
  return <div className="ml-progress">
    <span className="ml-progress-bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={e.progress.percent} aria-label={label}><span style={{ width: `${e.progress.percent}%` }} /></span>
    <span className="ml-progress-text">{tr('{0} из {1} шагов · {2}%', [String(e.progress.completed), String(e.progress.total), String(e.progress.percent)])}</span>
  </div>
}

export default function MyLearning() {
  const [data, setData] = useState<LearningData | null>(null)
  const [filter, setFilter] = useState<Filter>('active')
  const [revision, setRevision] = useState(0)
  const [loadError, setLoadError] = useState('')
  const [error, setError] = useState('')
  const home = useWorkspaceHome()
  const personal = new URLSearchParams(location.hash.slice(1)).get('mode') === 'personal'
  useEffect(() => {
    let alive = true
    apiRequest<LearningData>('/api/courses/my-learning/').then(value => { if (alive) { setData(value); setLoadError('') } }).catch(err => { if (alive) setLoadError(errorMessage(err)) })
    return () => { alive = false }
  }, [revision])
  async function join(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget)
    try {
      const result = await apiRequest<{ course_id: number; run_id: number }>('/api/courses/join/', 'POST', { code: form.get('code') })
      window.location.hash = `course=${result.course_id}&run=${result.run_id}`
    } catch (err) { setError(errorMessage(err)) }
  }
  async function changeStatus(id: number, status: string) {
    try { await apiRequest(`/api/courses/enrollments/${id}/`, 'PATCH', { status }); setError(''); setRevision(v => v + 1) }
    catch (err) { setError(errorMessage(err)) }
  }
  async function removeBookmark(courseId: number, kind: string) {
    try { await apiRequest(`/api/courses/${courseId}/bookmark/`, 'DELETE', { kind }); setError(''); setRevision(v => v + 1) }
    catch (err) { setError(errorMessage(err)) }
  }

  const header = <header className="ml-header">
    <h2 id="my-learning-title">{tr('Моё обучение')}</h2>
    <a className="button-link" href={`#page=deadlines${personal ? '&mode=personal' : ''}`}>{tr('Сроки и проверки')}</a>
  </header>

  if (!data) return <section className="my-learning-page" aria-labelledby="my-learning-title" aria-busy={!loadError}>
    {header}
    {loadError ? <div className="ml-empty" role="alert"><h3>{tr('Не удалось загрузить ваши курсы')}</h3><p>{tr(loadError)}</p><button type="button" className="secondary" onClick={() => { setLoadError(''); setRevision(v => v + 1) }}>{tr('Повторить')}</button></div>
      : <><div className="ml-continue ml-skeleton" aria-hidden="true"><div className="ml-continue-body"><span /><span /><span /></div></div>
        <p className="visually-hidden" role="status">{tr('Загрузка ваших курсов…')}</p>
        <ul className="ml-grid" aria-hidden="true">{[0, 1, 2].map(i => <li key={i} className="ml-card ml-skeleton"><div className="ml-card-cover" /><div className="ml-card-body"><span /><span /><span /></div></li>)}</ul></>}
  </section>

  const resume = home.data?.resume
  const current = resume ? data.enrollments.find(e => e.id === resume.enrollment_id && canStudy(e)) : undefined
  const counts = Object.fromEntries(FILTERS.map(([key]) => [key, key === 'favorite' || key === 'wishlist' ? data.bookmarks.filter(b => b.kind === key).length : data.enrollments.filter(e => inFilter(e, key)).length])) as Record<Filter, number>
  const rows = data.enrollments.filter(e => inFilter(e, filter))
  const marks = data.bookmarks.filter(b => b.kind === filter)
  const bookmarkList = filter === 'favorite' || filter === 'wishlist'
  const nothing = !data.enrollments.length && !data.bookmarks.length

  return <section className="my-learning-page" aria-labelledby="my-learning-title">
    {header}
    {error && <p className="error" role="alert">{tr(error)}</p>}

    {current && resume && <article className="ml-continue" aria-labelledby="ml-continue-title">
      <div className="ml-continue-cover"><CourseCover courseId={current.course_id} title={ct(current, 'course')} compact /></div>
      <div className="ml-continue-body">
        <p className="ml-continue-caption">{tr('Продолжить обучение')}</p>
        <h3 id="ml-continue-title" title={ct(current, 'course')}>{ct(current, 'course')}</h3>
        <p className="ml-continue-step" title={ct(resume, 'lesson')}>{tr('Следующий шаг: {0}', [ct(resume, 'lesson')])}</p>
        <Progress e={current} label={tr('Прогресс курса «{0}»', [ct(current, 'course')])} />
      </div>
      <a className="primary-link ml-continue-action" href={resume.target}>{tr('Продолжить')}</a>
    </article>}

    {nothing ? <div className="ml-empty">
      <h3>{tr('Вы пока не записаны ни на один курс')}</h3>
      <p>{tr('Выберите курс в каталоге или вступите в группу по коду преподавателя.')}</p>
      <a className="primary-link" href="#page=catalog">{tr('Перейти в каталог')}</a>
    </div> : <section className="ml-courses" aria-labelledby="ml-courses-title">
      <div className="ml-courses-head">
        <h3 id="ml-courses-title">{tr('Мои курсы')}</h3>
        <div className="ml-segment" role="group" aria-label={tr('Показать курсы')}>
          {FILTERS.map(([key, label]) => <button type="button" key={key} aria-pressed={filter === key} onClick={() => setFilter(key)}>
            {tr(label)}{counts[key] > 0 && <span className="ml-count">{counts[key]}</span>}
          </button>)}
        </div>
      </div>
      {(bookmarkList ? !marks.length : !rows.length) ? <div className="ml-empty ml-empty-inline"><p>{tr('В этом списке пока нет курсов.')}</p></div>
        : <ul className="ml-grid">
          {bookmarkList ? marks.map(b => <li key={`${b.kind}-${b.course_id}`} className="ml-card">
            <div className="ml-card-body">
              <h4 className="ml-card-title"><a href={`#course=${b.course_id}`} title={ct(b, 'title')}>{ct(b, 'title')}</a></h4>
              <p className="ml-card-meta">{tr(b.kind === 'favorite' ? 'Избранное' : 'Хочу пройти')}</p>
            </div>
            <div className="ml-card-cover"><CourseCover courseId={b.course_id} title={ct(b, 'title')} compact /></div>
            <MoreMenu className="ml-card-menu" label={tr('Действия с курсом «{0}»', [ct(b, 'title')])} items={[
              { label: tr('О курсе'), href: `#course=${b.course_id}&tab=overview` },
              { label: tr('Убрать из списка'), onSelect: () => removeBookmark(b.course_id, b.kind) },
            ]} />
          </li>) : rows.map(e => {
            const deadline = e.deadlines[0]
            const items: MoreMenuItem[] = [{ label: tr('О курсе'), href: aboutLink(e) }]
            if (e.status !== 'removed') items.push({ label: e.status === 'archived' ? tr('Вернуть в обучение') : tr('В архив'), onSelect: () => changeStatus(e.id, e.status === 'archived' ? 'active' : 'archived') })
            return <li key={e.id} className="ml-card">
              <div className="ml-card-body">
                <h4 className="ml-card-title"><a href={canStudy(e) ? studyLink(e) : aboutLink(e)} title={ct(e, 'course')}>{ct(e, 'course')}</a></h4>
                <p className="ml-card-meta" title={ct(e, 'run')}>{ct(e, 'run')}</p>
                {e.status === 'removed' ? <p className="ml-card-note">{tr('Доступ отозван преподавателем. Результаты сохранены.')}</p>
                  : e.pending > 0 ? <p className="ml-card-note">{tr('Работ на проверке: ')}{e.pending}</p>
                  : deadline ? <p className="ml-card-note" title={ct(deadline, 'title')}>{tr(deadline.label)}: {formatDate(deadline.due_at)}</p> : null}
                <Progress e={e} label={tr('Прогресс курса «{0}»', [ct(e, 'course')])} />
              </div>
              <div className="ml-card-cover"><CourseCover courseId={e.course_id} title={ct(e, 'course')} compact /></div>
              <MoreMenu className="ml-card-menu" label={tr('Действия с курсом «{0}»', [ct(e, 'course')])} items={items} />
            </li>
          })}
        </ul>}
    </section>}

    {home.data?.role === 'student' && <StudentPanels data={home.data} />}

    <details className="ml-join">
      <summary>{tr('Вступить в группу по коду приглашения')}</summary>
      <form className="ml-join-form" onSubmit={join}>
        <label htmlFor="ml-join-code">{tr('Код приглашения')}</label>
        <div><input id="ml-join-code" name="code" required maxLength={64} autoComplete="off" /><button className="secondary">{tr('Вступить')}</button></div>
      </form>
    </details>
  </section>
}
