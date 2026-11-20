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
  const all = data?.student_tasks ?? []
  const isAction = (task: Task) => !['waiting', 'graded'].includes(task.state)
  const groups: [string, string, (task: Task) => boolean][] = [['action', 'Нужно выполнить', isAction], ['waiting', 'На проверке', task => task.state === 'waiting'], ['graded', 'Проверено', task => task.state === 'graded'], ['all', 'Все', () => true]]
  const tasks = all.filter(groups.find(([id]) => id === filter)?.[2] ?? isAction)
  const revisionCount = all.filter(t => t.state === 'revision').length
  const tone = (task: Task) => ['late', 'revision', 'module_overdue'].includes(task.state) ? 'is-warning' : task.state === 'closed' ? 'is-danger' : task.state === 'graded' ? 'is-success' : task.state === 'waiting' ? 'is-info' : ''
  function kindLabel(task: Task) {
    if (task.kind === 'module') return tr('Модуль')
    return task.kind === 'quiz' ? tr('Тест') : tr('Письменная работа')
  }
  function dueLabel(task: Task) {
    if (task.kind === 'module') return tr('Дедлайн прохождения')
    if (task.state === 'revision') return tr('Исправить и отправить до')
    if (task.source === 'personal') return tr('Ваш индивидуальный срок')
    return task.kind === 'quiz' ? tr('Завершить до') : tr('Сдать до')
  }
  return <section className="page agenda-page" aria-labelledby="agenda-title">
    <header className="page-header">
      <div><h2 className="page-title" id="agenda-title">{tr('Мои задания и сроки')}</h2>
        {data && <p className="page-sub">{tr('Нужно выполнить: {0} · на проверке: {1} · на доработке: {2}', [String(all.filter(isAction).length), String(all.filter(t => t.state === 'waiting').length), String(revisionCount)])}</p>}</div>
      <button className="secondary" onClick={() => setRevision(v => v + 1)}>{tr('Обновить')}</button>
    </header>
    {error && <p className="error" role="alert">{tr(error)}</p>}
    {data && <WeekCalendar tasks={data.student_tasks} />}
    <div className="segment" role="group" aria-label={tr('Фильтр моих задач')}>{groups.map(([id, label, test]) => {
      const count = all.filter(test).length
      return <button type="button" key={id} aria-pressed={filter === id} onClick={() => setFilter(id)}>{tr(label)}{data && count > 0 && <span className="segment-count">{count}</span>}</button>
    })}</div>
    {!data && !error && <p className="muted" role="status">{tr('Загрузка сроков…')}</p>}
    {data && !tasks.length && <div className="empty"><h3>{filter === 'action' ? tr('Все задания выполнены') : tr('В этом списке пока нет задач.')}</h3>{filter === 'action' && <p>{tr('Нет незавершённых заданий. Можно продолжать курс в своём темпе.')}</p>}</div>}
    {tasks.length > 0 && <ul className="list agenda-list">{tasks.map(task => <li className={`list-row agenda-task ${task.state}`} key={task.id}>
      <div className="list-row-main">
        <p className="agenda-kind">{kindLabel(task)}</p>
        <h3 className="list-row-title"><a href={task.target}>{ct(task, 'title')}</a></h3>
        <p className="list-row-meta">{ct(task, 'course')} · {ct(task, 'run')}</p>
        {task.state === 'waiting' && task.review_overdue && <p className="agenda-note">{tr('Проверка просрочена.')}</p>}
      </div>
      <dl className="agenda-dates">
        {task.state === 'waiting' ? <div><dt>{tr('Проверка до:')}</dt><dd>{task.review_due_at ? formatDate(task.review_due_at) : tr('Преподаватель ещё не назначил срок')}</dd>{task.reviewer && <dd className="agenda-reviewer">{task.reviewer}<RoleBadge label={tr(task.reviewer_role_label)} /></dd>}</div>
          : task.state === 'graded' ? <div><dt>{tr('Результат')}</dt><dd>{tr('Результат сохранён.')}</dd></div>
          : <>
            <div><dt>{dueLabel(task)}</dt><dd>{formatDate(task.due_at)}</dd></div>
            {task.kind === 'module' ? Boolean(task.total_steps) && <div><dt>{tr('Пройдено')}</dt><dd>{task.completed_steps}/{task.total_steps}</dd></div>
              : task.kind !== 'quiz' && task.closes_at !== task.due_at && <div><dt>{tr('Окончание приёма')}</dt><dd>{formatDate(task.closes_at)}</dd></div>}
            {task.opens_at && task.state === 'not_started' && <div><dt>{tr('Откроется')}</dt><dd>{formatDate(task.opens_at)}</dd></div>}
          </>}
      </dl>
      <span className={`badge ${tone(task)}`} title={task.kind === 'module' && task.state === 'graded' ? tr('Пройден') : labels[task.state] ?? ''}>{task.kind === 'module' && task.state === 'graded' ? tr('Пройден') : labels[task.state] ?? tr('К выполнению')}</span>
    </li>)}</ul>}
  </section>
}
