import { ct } from '../../i18n/content'
import { localizedLabels, t as tr } from '../../i18n/language'
import { useEffect, useState } from 'react'
import { apiRequest } from '../../api'
import RoleBadge from '../../components/RoleBadge'
import { errorMessage, formatDate } from '../study/types'
import StudentDetail from '../study/StudentDetail'
import { useOverview } from './useOverview'
import { Pagination, RunFilters } from './ManagementParts'
import './Management.css'

type Student = { id: number; display_name: string; role_label: string; enrollment_id: number; course_id: number; course: string; run_id: number; run: string; status: string; last_seen_at: string | null; last_step: string | null; progress: { percent: number; completed: number; total: number }; pending: number; returned: number; graded: number }
type Page = { students: Student[]; page: number; next_page: number | null; total: number }
type Task = { id: string; title: string; kind: string; state: string; due_at: string | null; closes_at: string | null; review_due_at?: string | null; review_overdue?: boolean; reviewer?: string | null; reviewer_role_label?: string }
const statuses: Record<string, string> = localizedLabels({ active: 'Учится', completed: 'Завершено', archived: 'В архиве', removed: 'Доступ отозван' })
const taskStates: Record<string, string> = localizedLabels({ open: 'Можно выполнить', late: 'Срок сдачи прошёл, опоздания разрешены', closed: 'Приём закрыт', not_started: 'Откроется по расписанию', unavailable: 'Недоступно', revision: 'Нужна доработка', waiting: 'На проверке', graded: 'Проверено', active_quiz: 'Тест идёт' })

function LearnerTasks({ student, close }: { student: Student; close: () => void }) {
  const [data, setData] = useState<{ tasks: Task[]; historical: boolean } | null>(null)
  const [error, setError] = useState('')
  useEffect(() => { let alive = true; apiRequest<typeof data>(`/api/study/management/enrollments/${student.enrollment_id}/tasks/`).then(value => { if (alive) setData(value) }).catch(err => { if (alive) setError(errorMessage(err)) }); return () => { alive = false } }, [student.enrollment_id])
  return <section className="management-page"><button className="secondary" onClick={close}>{tr("← Все ученики")}</button><div><h2>{tr("Задания: ")}{student.display_name}<RoleBadge label={tr(student.role_label)} /></h2><p className="muted">{ct(student, "course")} · {ct(student, "run")}</p></div>{error && <p className="error" role="alert">{tr(error)}</p>}{!data && !error && <p>{tr("Загрузка заданий…")}</p>}{data?.historical && <p>{tr("Активное обучение закрыто.")}</p>}{data && !data.historical && !data.tasks.length && <p className="empty-state">{tr("Опубликованных заданий и тестов пока нет.")}</p>}{data?.tasks.map(task => <article className="study-card" key={task.id}><div className="section-heading"><h3>{ct(task, "title")}</h3><span className="deadline-pill">{taskStates[task.state] || task.state}</span></div><p>{task.kind === 'quiz' ? tr("Завершить до") : tr("Сдать до")}: {formatDate(task.due_at)}</p>{task.state === 'waiting' && <><p>{tr("Проверить до: ")}{task.review_due_at ? formatDate(task.review_due_at) : tr("Срок не назначен")} · {task.reviewer || tr("Ответственный не назначен")}<RoleBadge label={tr(task.reviewer_role_label)} /></p>{task.review_overdue && <p className="error">{tr("Преподаватель задерживает проверку.")}</p>}</>}</article>)}</section>
}

export default function StudentsPage({ admin = false }: { admin?: boolean }) {
  const { data: overview, error: overviewError } = useOverview()
  const [data, setData] = useState<Page | null>(null)
  const [search, setSearch] = useState('')
  const [course, setCourse] = useState('')
  const [run, setRun] = useState('')
  const [status, setStatus] = useState('all')
  const [page, setPage] = useState(1)
  const [revision, setRevision] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<{ student: Student; view: 'answers' | 'tasks' } | null>(null)
  useEffect(() => {
    let alive = true
    const query = new URLSearchParams({ search, course_id: course, run_id: run, status, page: String(page) })
    const timer = window.setTimeout(() => { setLoading(true); apiRequest<Page>(`/api/study/management/students/?${query}`).then(value => { if (alive) { setData(value); setError('') } }).catch(err => { if (alive) setError(errorMessage(err)) }).finally(() => { if (alive) setLoading(false) }) }, 200)
    return () => { alive = false; window.clearTimeout(timer) }
  }, [search, course, run, status, page, revision])
  if (selected?.view === 'answers') return <StudentDetail courseId={selected.student.course_id} runId={selected.student.run_id} studentId={selected.student.id} onBack={() => { setSelected(null); setRevision(v => v + 1) }} />
  if (selected) return <LearnerTasks student={selected.student} close={() => setSelected(null)} />
  return <section className="page management-page students-management"><header className="page-header"><div><h2 className="page-title">{admin ? tr("Контроль обучения студентов") : tr("Мои ученики")}</h2></div><button className="secondary" onClick={() => setRevision(v => v + 1)}>{tr("Обновить")}</button></header>
    <div className="management-filters"><label>{tr("Поиск ученика")}<input value={search} onChange={e => { setLoading(true); setSearch(e.target.value); setPage(1) }} placeholder={tr("Фамилия, имя или логин")} /></label><RunFilters runs={overview?.runs || []} course={course} run={run} change={(c, r) => { setLoading(true); setCourse(c); setRun(r); setPage(1) }} /><label>{tr("Статус обучения")}<select aria-label={tr("Статус обучения")} value={status} onChange={e => { setLoading(true); setStatus(e.target.value); setPage(1) }}><option value="all">{tr("Все статусы")}</option>{Object.entries(statuses).map(([key, label]) => <option key={key} value={key}>{ct(label)}</option>)}</select></label></div>
    {(error || overviewError) && <p className="error" role="alert">{error || overviewError}</p>}{loading ? <p role="status">{tr("Загрузка учеников…")}</p> : data && <><Pagination page={page} total={data.total} next={data.next_page} change={p => { setLoading(true); setPage(p) }} />{!data.students.length ? <p className="empty-state">{tr("Учеников с такими условиями нет.")}</p> : <div className="management-table-wrap" tabIndex={0} role="region" aria-label={tr("Таблица прокручивается по горизонтали")}><table className="management-table"><thead><tr><th>{tr("Ученик")}</th><th>{tr("Курс и группа")}</th><th>{tr("Прогресс")}</th><th>{tr("Работы и активность")}</th><th>{tr("Подробности")}</th></tr></thead><tbody>{data.students.map(student => <tr key={student.enrollment_id}><td><strong>{student.display_name}</strong><RoleBadge label={tr(student.role_label)} /><small>{statuses[student.status]}</small></td><td>{ct(student, "course")}<small>{ct(student, "run")}</small></td><td><strong>{student.progress.percent}%</strong><progress max={100} value={student.progress.percent} /><small>{student.progress.completed}/{student.progress.total} {tr(" обязательных шагов")}</small></td><td>{tr("На проверке: ")}{student.pending}<small>{tr("Проверено отправок: ")}{student.graded} {tr(" · Возвратов в истории: ")}{student.returned}</small><small>{student.last_seen_at ? tr("Последнее обучение: {0}", [formatDate(student.last_seen_at)]) : tr("Уроки ещё не открывал")}{student.last_step ? ` · ${student.last_step}` : ''}</small></td><td><div className="row-links"><button type="button" className="link-button" onClick={() => setSelected({ student, view: 'answers' })}>{tr("Ответы и прогресс")}</button><button type="button" className="link-button" onClick={() => setSelected({ student, view: 'tasks' })}>{tr("Задания и сроки")}</button></div></td></tr>)}</tbody></table></div>}</>}
  </section>
}
