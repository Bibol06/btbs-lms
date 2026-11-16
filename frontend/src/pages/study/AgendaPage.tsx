import { ct } from '../../i18n/content'
import { localizedLabels, t as tr } from '../../i18n/language'
import WeekCalendar from '../workspace/WeekCalendar'
import RoleBadge from '../../components/RoleBadge'
import { useEffect, useState } from 'react'
import { apiRequest } from '../../api'
import { errorMessage, formatDate } from './types'
import './Deadlines.css'

type Task = { id: string; kind: string; title: string; course: string; run: string; due_at: string | null; closes_at: string | null; opens_at?: string | null; source?: string; state: string; target: string; review_due_at?: string | null; review_overdue?: boolean; reviewer_role_label?: string; reviewer?: string | null; completed_steps?: number; total_steps?: number }
type Agenda = { student_tasks: Task[]; review_counts: { pending: number; overdue: number }; server_now: string }
const labels: Record<string, string> = localizedLabels({ module_overdue: 'Дедлайн просрочен', open: 'Можно выполнить', late: 'Срок сдачи прошёл — опоздания разрешены', closed: 'Приём закрыт', not_started: 'Откроется по расписанию', unavailable: 'Недоступно', revision: 'Нужна доработка', waiting: 'На проверке', graded: 'Проверено', active_quiz: 'Тест уже идёт' })

export default function AgendaPage() {
  const [data, setData] = useState<Agenda | null>(null)
  const [filter, setFilter] = useState('action')
  const [revision, setRevision] = useState(0)
  const [error, setError] = useState('')
  useEffect(() => {
    let alive = true
    async function load() {
      try { const value = await apiRequest<Agenda>('/api/study/agenda/'); if (alive) { setData(value); setError('') } }
      catch (err) { if (alive) setError(errorMessage(err)) }
    }
    void load(); const timer = window.setInterval(load, 30000)
    return () => { alive = false; window.clearInterval(timer) }
  }, [revision])
  const tasks = data?.student_tasks.filter(task => filter === 'all' || (filter === 'waiting' ? task.state === 'waiting' : filter === 'graded' ? task.state === 'graded' : !['waiting', 'graded'].includes(task.state))) ?? []
  return <section className="study-section agenda-page">
    <div className="section-heading"><div><p className="eyebrow">{tr("Что сделать и когда")}</p><h2>{tr("Мои задания и сроки")}</h2></div><button className="secondary" onClick={() => setRevision(v => v + 1)}>{tr("Обновить")}</button></div>
    {error && <p className="error" role="alert">{tr(error)}</p>}
    <>
      <div className="learning-overview"><div><strong>{data?.student_tasks.filter(t => !['waiting', 'graded'].includes(t.state)).length ?? '—'}</strong><span>{tr("Нужно выполнить")}</span></div><div><strong>{data?.student_tasks.filter(t => t.state === 'waiting').length ?? '—'}</strong><span>{tr("Ожидают проверки")}</span></div><div><strong>{data?.student_tasks.filter(t => t.state === 'revision').length ?? '—'}</strong><span>{tr("Вернули на доработку")}</span></div></div>
      {data && <WeekCalendar tasks={data.student_tasks} />}
      <div className="queue-filters" role="group" aria-label={tr("Фильтр моих задач")}>{[['action', tr("Нужно выполнить")], ['waiting', tr("На проверке")], ['graded', tr("Проверено")], ['all', tr("Все")]].map(([id, label]) => <button key={id} className={filter === id ? '' : 'secondary'} aria-pressed={filter === id} onClick={() => setFilter(id)}>{ct(label)}</button>)}</div>
      {!data && !error && <p>{tr("Загрузка сроков…")}</p>}
      {data && !tasks.length && <p className="empty-state">{tr("В этом списке пока нет задач.")}</p>}
      <div className="agenda-list">{tasks.map(task => <article className={`study-card agenda-task ${task.state}`} key={task.id}>
        <div className="section-heading"><div><p className="eyebrow">{task.kind === 'module' ? tr('Модуль') : task.kind === 'quiz' ? tr("Тест") : tr("Письменная работа")}</p><h3>{ct(task, "title")}</h3></div><span className={`deadline-pill ${['late', 'revision', 'module_overdue'].includes(task.state) ? 'warning' : task.state === 'closed' ? 'danger' : ''}`}>{task.kind === 'module' && task.state === 'graded' ? tr('Пройден') : labels[task.state] ?? task.state}</span></div><p className="muted">{ct(task, "course")} · {ct(task, "run")}</p>
        {task.kind === 'module' ? <div className="deadline-summary"><div><small>{tr('Дедлайн прохождения')}</small><strong>{formatDate(task.due_at)}</strong></div>{Boolean(task.total_steps) && <div><small>{tr('Пройдено')}</small><strong>{task.completed_steps}/{task.total_steps}</strong></div>}</div> : task.state === 'waiting' ? <><p><strong>{tr("Проверка до:")}</strong> {task.review_due_at ? formatDate(task.review_due_at) : tr("Преподаватель ещё не назначил срок")}{task.reviewer && <> · {task.reviewer}<RoleBadge label={tr(task.reviewer_role_label)} /></>}</p>{task.review_overdue && <p className="deadline-note warning">{tr("Проверка просрочена.")}</p>}</> : task.state === 'graded' ? <p className="muted">{tr("Результат сохранён.")}</p> : <div className="deadline-summary"><div><small>{task.state === 'revision' ? tr("Исправить и отправить до") : task.source === 'personal' ? tr("Ваш индивидуальный срок") : task.kind === 'quiz' ? tr("Завершить до") : tr("Сдать до")}</small><strong>{formatDate(task.due_at)}</strong></div>{task.kind !== 'quiz' && <div><small>{tr("Окончание приёма")}</small><strong>{formatDate(task.closes_at)}</strong></div>}{task.opens_at && task.state === 'not_started' && <div><small>{tr("Откроется")}</small><strong>{formatDate(task.opens_at)}</strong></div>}</div>}
        
        <a className="button-link" href={task.target}>{task.kind === 'module' ? tr('Открыть модуль') : task.state === 'waiting' || task.state === 'graded' ? tr("Посмотреть работу и результат →") : task.state === 'active_quiz' ? tr("Продолжить тест →") : tr("Открыть задание →")}</a>
      </article>)}</div>
    </>
  </section>
}
