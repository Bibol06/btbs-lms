import { ct } from '../../i18n/content'
import DiscussionBody from '../../components/DiscussionBody'
import { localizedLabels, t as tr } from '../../i18n/language'
import { useEffect, useState } from 'react'
import { apiRequest } from '../../api'
import { errorMessage, formatDate } from '../study/types'

type Task = { id: string; title: string; course: string; run: string; state: string; due_at: string | null; target: string }
type HomeData = {
  role: string; resume?: { title: string; lesson: string; target: string } | null; tasks?: Task[]
  feedback?: { id: number; title: string; teacher: string; body: string; score: number | null; max_score: number; target: string; state: string; created_at: string }[]
  works?: { id: number; assignment: string; student: string; run: string; review_state: string; target: string; review_due_at: string | null }[]
  questions?: { id: number; student: string; body: string; target: string }[]; question_count?: number
  attention?: { id: number; student: string; course: string; run: string; reasons: string[]; target: string }[]
  counts?: { pending: number; overdue: number; unassigned: number; attention: number }
  runs?: { id: number; title: string; course: string; kind: string }[]
}

function useWorkspaceHome() {
  const [data, setData] = useState<HomeData | null>(null), [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  const personal = new URLSearchParams(location.hash.slice(1)).get('mode') === 'personal'
  useEffect(() => {
    let alive = true
    apiRequest<HomeData>(`/api/workspace/home/?personal=${personal ? '1' : '0'}`).then(v => { if (alive) { setData(v); setError('') } }).catch(e => { if (alive) setError(errorMessage(e)) })
    return () => { alive = false }
  }, [personal, revision])
  return { data, error, refresh: () => setRevision(v => v+1) }
}

const taskState: Record<string, string> = localizedLabels({ module_overdue: 'Дедлайн просрочен', revision: 'На доработку', late: 'Срок прошёл', closed: 'Приём закрыт', active_quiz: 'Тест уже идёт', open: 'Можно выполнить' })

export default function WorkspaceHome() {
  const { data, error } = useWorkspaceHome()
  if (error) return <p className="error" role="alert">{tr(error)}</p>
  if (!data) return <p className="muted" role="status">{tr("Собираем ближайшие задачи…")}</p>
  if (data.role === 'student') return <div className="hub-home">
    {data.resume && <section className="hub-resume"><div><p className="eyebrow">{tr("Ваш следующий шаг")}</p><h3>{ct(data.resume, "title")}</h3><p>{ct(data.resume, "lesson")}</p></div><a className="primary-link" href={data.resume.target}>{tr("Продолжить обучение →")}</a></section>}
    <div className="hub-columns"><section className="hub-panel"><div className="section-heading"><h3>{tr("Сегодня и скоро")}</h3><a href={`#page=deadlines${location.hash.includes('mode=personal') ? '&mode=personal' : ''}`}>{tr("Все сроки →")}</a></div>
      {!data.tasks?.length && <p className="muted">{tr("Нет незавершённых заданий. Можно продолжать курс в своём темпе.")}</p>}
      {data.tasks?.slice(0, 4).map(t => <a className="hub-row" href={t.target} key={t.id}><div><strong>{ct(t, "title")}</strong><small>{ct(t, "course")} · {ct(t, "run")}</small><span className={`hub-status ${['revision', 'late', 'closed', 'module_overdue'].includes(t.state) ? 'warning' : ''}`}>{taskState[t.state] || tr("К выполнению")}</span></div><time>{t.due_at ? formatDate(t.due_at) : tr("Без срока")}</time></a>)}
    </section><section className="hub-panel"><div className="section-heading"><h3>{tr("Обратная связь")}</h3><span className="muted">{tr("Последние проверки")}</span></div>
      {!data.feedback?.length && <p className="muted">{tr("Здесь появятся оценки и комментарии преподавателя.")}</p>}
      {data.feedback?.slice(0, 3).map(f => <a className="hub-row" href={f.target} key={f.id}><div><strong>{ct(f, "title")}</strong><small>{f.teacher} {tr(" · Преподаватель")}</small><p>{ct(f, "body") || tr("Откройте работу, чтобы посмотреть результат.")}</p></div><span className="hub-score">{f.score === null ? tr("Доработка") : `${f.score}/${f.max_score}`}</span></a>)}
    </section></div>
  </div>
  return <div className="hub-home"><div className="hub-summary">
    {[[data.counts?.pending, tr("Работ на проверке"), 'reviews'], [data.counts?.overdue, tr("Проверок с задержкой"), 'reviews&state=overdue'], data.role === 'admin' ? [data.counts?.unassigned, tr("Без ответственного"), 'reviews&unassigned=1'] : [data.question_count, tr("Вопросов без ответа"), 'questions'], [data.counts?.attention, tr("Нужна поддержка"), 'attention']].map(([value, label, target]) => <a href={`#page=${target}`} key={String(label)}><strong>{value ?? 0}</strong><span>{ct(label)}</span><i>↗</i></a>)}
  </div><div className="hub-columns"><section className="hub-panel"><div className="section-heading"><h3>{data.role === 'admin' ? tr("Проверки, требующие внимания") : tr("Начните с проверки")}</h3><a href="#page=reviews">{tr("Вся очередь →")}</a></div>
    {!data.works?.length && <p className="muted">{tr("Все отправленные работы проверены.")}</p>}
    {data.works?.slice(0, 3).map(w => <a className="hub-row" href={w.target} key={w.id}><div><strong>{ct(w, "assignment")}</strong><small>{w.student} {tr(" · Студент · ")}{ct(w, "run")}</small></div><span className={`hub-status ${w.review_state === 'overdue' ? 'warning' : ''}`}>{w.review_state === 'overdue' ? tr("Проверка просрочена") : w.review_due_at ? formatDate(w.review_due_at) : tr("Ожидает проверки")}</span></a>)}
  </section><section className="hub-panel"><div className="section-heading"><h3>{tr("Вопросы учеников")}</h3><a href="#page=questions">{tr("Ответить →")}</a></div>
    {!data.questions?.length && <p className="muted">{tr("Новых вопросов без преподавательского ответа нет.")}</p>}
    {data.questions?.slice(0, 3).map(q => <a className="hub-row" href={q.target} key={q.id}><div><strong>{q.student}</strong><DiscussionBody comment={q} compact /></div><span>→</span></a>)}
  </section></div></div>
}

export function AttentionPage() {
  const { data, error, refresh } = useWorkspaceHome()
  const [run, setRun] = useState(''), [policy, setPolicy] = useState({ inactive_days: 0, missing_count: 2, low_score_percent: 0 })
  const [message, setMessage] = useState(''), [failure, setFailure] = useState(''), [saving, setSaving] = useState(false)
  useEffect(() => {
    if (!run) return
    let alive = true
    apiRequest<typeof policy>(`/api/workspace/policies/${run}/`).then(v => { if (alive) { setPolicy(v); setFailure('') } }).catch(e => { if (alive) setFailure(errorMessage(e)) })
    return () => { alive = false }
  }, [run])
  return <section className="study-section"><div><p className="eyebrow">{tr("Поддержка обучения")}</p><h2>{tr("Требует внимания")}</h2></div>
    {(error || failure) && <p className="error" role="alert">{tr(error || failure)}</p>}
    <div className="hub-attention-list">{data?.attention?.map(s => <article className="hub-panel" key={s.id}><div className="section-heading"><div><h3>{s.student}<span className="person-role">{tr("Студент")}</span></h3><p className="muted">{ct(s, "course")} · {ct(s, "run")}</p></div><a className="primary-link" href={s.target}>{tr("Открыть прогресс →")}</a></div><ul>{s.reasons.map(r => <li key={r}>{tr(r)}</li>)}</ul></article>)}</div>
    {data && !data.attention?.length && <p className="empty-state">{tr("По текущим правилам сигналов нет.")}</p>}
    <details className="hub-panel"><summary>{tr("Настроить сигналы по группе")}</summary><label className="search-field">{tr("Группа или запуск")}<select aria-label={tr("Группа правил внимания")} value={run} onChange={e => { setRun(e.target.value); setMessage('') }}><option value="">{tr("Выберите запуск")}</option>{data?.runs?.map(r => <option key={r.id} value={r.id}>{ct(r, "course")} · {ct(r, "title")}</option>)}</select></label>
      {run && <form className="study-form compact" onSubmit={async e => { e.preventDefault(); setSaving(true); setFailure(''); try { await apiRequest(`/api/workspace/policies/${run}/`, 'PUT', policy); setMessage('Правила сохранены.'); refresh(); } catch (err) { setFailure(errorMessage(err)) } finally { setSaving(false) } }}><div className="form-grid">{[['inactive_days', tr("Дней без активности"), 365], ['missing_count', tr("Несданных в срок заданий"), 100], ['low_score_percent', tr("Средний результат тестов ниже, %"), 100]].map(([key, label, max]) => <label key={String(key)}>{ct(label)}<input type="number" min={0} max={Number(max)} required value={policy[key as keyof typeof policy]} onChange={e => setPolicy(v => ({ ...v, [key]: Number(e.target.value) }))} /></label>)}</div><button disabled={saving}>{tr("Сохранить правила")}</button></form>}{message && <p role="status" className="success">{tr(message)}</p>}</details>
  </section>
}

export function QuestionsPage() {
  const [data, setData] = useState<{ questions: { id: number; body: string; student: string; course: string; run: string; lesson: string; state: string; target: string }[]; total: number; next_page: number | null } | null>(null)
  const [state, setState] = useState('waiting'), [page, setPage] = useState(1), [error, setError] = useState('')
  useEffect(() => { let alive = true; apiRequest<NonNullable<typeof data>>(`/api/workspace/questions/?state=${state}&page=${page}`).then(v => { if (alive) { setData(v); setError('') } }).catch(e => { if (alive) setError(errorMessage(e)) }); return () => { alive = false } }, [state, page])
  return <section className="study-section"><div><p className="eyebrow">{tr("Общение по курсам")}</p><h2>{tr("Вопросы учеников")}</h2></div><div className="queue-filters">{[['waiting', tr("Ожидают ответа")], ['answered', tr("Преподаватель ответил")], ['resolved', tr("Решённые")], ['all', tr("Все вопросы")]].map(([id, label]) => <button key={id} className={state === id ? '' : 'secondary'} onClick={() => { setState(id); setPage(1) }}>{ct(label)}</button>)}</div>{error && <p role="alert" className="error">{tr(error)}</p>}
    {data?.questions.map(q => <article className="hub-panel" key={q.id}><div className="section-heading"><strong>{q.student}<span className="person-role">{tr("Студент")}</span></strong><span className="hub-status">{q.state === 'resolved' ? tr("Решён") : q.state === 'answered' ? tr("Преподаватель ответил") : tr("Ожидает ответа")}</span></div><DiscussionBody comment={q} /><p className="muted">{ct(q, "course")} · {ct(q, "run")} · {ct(q, "lesson")}</p><a className="primary-link" href={q.target}>{tr("Открыть обсуждение →")}</a></article>)}
    {data && !data.questions.length && <p className="empty-state">{tr("В этой категории вопросов нет.")}</p>}<div className="action-row"><button className="secondary" disabled={page === 1} onClick={() => setPage(p => p-1)}>{tr("← Назад")}</button><span>{tr("Страница ")}{page}</span><button className="secondary" disabled={!data?.next_page} onClick={() => setPage(p => p+1)}>{tr("Далее →")}</button></div></section>
}
