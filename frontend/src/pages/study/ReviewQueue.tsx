import { ct } from '../../i18n/content'
import { t as tr } from '../../i18n/language'
import RoleBadge from '../../components/RoleBadge'
import { useEffect, useState } from 'react'
import { apiRequest } from '../../api'
import { errorMessage, formatDate } from './types'

type Work = { id: number; student: string; student_role_label: string; reviewer_role_label: string; course: string; run: string; assignment: string; submitted_at: string; review_due_at: string | null; review_state: string; reviewer_id: number | null; reviewer: string | null; is_late: boolean; target: string }
type Queue = { total: number; counts: { all: number; overdue: number; soon: number }; next_page: number | null; works: Work[] }

export default function ReviewQueue({ userId, monitor = false, courseId = '', runId = '', reviewerId = '' }: { userId: number; monitor?: boolean; courseId?: string; runId?: string; reviewerId?: string }) {
  const [data, setData] = useState<Queue | null>(null)
  const [filter, setFilter] = useState(() => { const value = new URLSearchParams(location.hash.slice(1)).get('state'); return value && ['all', 'overdue', 'soon'].includes(value) ? value : 'all' })
  const [mine, setMine] = useState(false)
  const [unassigned, setUnassigned] = useState(() => new URLSearchParams(location.hash.slice(1)).get('unassigned') === '1')
  const [page, setPage] = useState(1)
  const [revision, setRevision] = useState(0)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    let alive = true
    async function load() {
      try {
        const params = new URLSearchParams({ state: filter, mine: mine ? '1' : '0', unassigned: unassigned ? '1' : '0', page: String(page), course_id: courseId, run_id: runId, reviewer_id: reviewerId })
        const result = await apiRequest<Queue>(`/api/study/review-queue/?${params}`)
        if (alive) { setData(result); setError('') }
      } catch (err) { if (alive) setError(errorMessage(err)) } finally { if (alive) setLoading(false) }
    }
    void load(); const timer = window.setInterval(load, 30000)
    return () => { alive = false; window.clearInterval(timer) }
  }, [filter, mine, unassigned, page, revision, courseId, runId, reviewerId])
  async function take(work: Work) {
    setBusy(work.id); setError('')
    try { await apiRequest(`/api/study/submissions/${work.id}/reviewer/`, 'PATCH', { reviewer_id: userId }); setRevision(v => v + 1) }
    catch (err) { setError(errorMessage(err)) } finally { setBusy(null) }
  }
  return <section className="review-queue study-section">
    <div className="section-heading"><div><h3>{tr("Проверка работ")}</h3></div><button className="secondary" onClick={() => { setLoading(true); setRevision(v => v + 1) }}>{tr("Обновить очередь")}</button></div>
    <div className="queue-filters" role="group" aria-label={tr("Фильтр очереди")}>{[['all', tr("Все на проверке")], ['overdue', tr("Просрочены")], ['soon', tr("До срока менее суток")]].map(([id, label]) => <button className={filter === id ? '' : 'secondary'} aria-pressed={filter === id} key={id} onClick={() => { if (id !== filter) { setLoading(true); setFilter(id); setPage(1) } }}>{ct(label)} <span>{data?.counts[id as keyof Queue['counts']] ?? '—'}</span></button>)}</div>
    <div className="action-row">{!monitor && <label className="check queue-mine"><input type="checkbox" checked={mine} onChange={e => { setLoading(true); setMine(e.target.checked); if (e.target.checked) setUnassigned(false); setPage(1) }} /> {tr(" Только назначенные мне")}</label>}<label className="check queue-mine"><input type="checkbox" checked={unassigned} onChange={e => { setLoading(true); setUnassigned(e.target.checked); if (e.target.checked) setMine(false); setPage(1) }} /> {tr(" Без ответственного")}</label></div>
    {error && <p className="error" role="alert">{tr(error)}</p>}
    {loading && !error && <p role="status">{tr("Загрузка очереди…")}</p>}
    {data && !loading && !data.works.length && <p className="empty-state">{tr("В этой категории нет работ.")}</p>}
    <div className="review-work-list">{!loading && data?.works.map(work => <article className={`review-work ${work.review_state}`} key={work.id}>
      <div className="section-heading"><div><h4>{ct(work, "assignment")}</h4><p className="muted"><strong>{work.student}</strong><RoleBadge label={tr(work.student_role_label)} /> · {ct(work, "course")} · {ct(work, "run")}</p></div><span className={`deadline-pill ${work.review_state === 'overdue' ? 'danger' : work.review_state === 'soon' ? 'warning' : ''}`}>{work.review_state === 'overdue' ? tr("Проверка просрочена") : work.review_state === 'soon' ? tr("Проверить в ближайшие сутки") : tr("Ожидает проверки")}</span></div>
      <div className="review-work-dates"><span>{tr("Отправлено: ")}{formatDate(work.submitted_at)}</span><strong>{tr("Проверить до: ")}{work.review_due_at ? formatDate(work.review_due_at) : tr("Срок не назначен")}</strong></div>
      <p className="muted">{tr("Ответственный: ")}{work.reviewer || tr("Пока не назначен")}{work.reviewer && <RoleBadge label={tr(work.reviewer_role_label)} />}{work.is_late ? tr(" · Ученик сдал с опозданием") : ''}</p>
      <div className="action-row"><a className="primary-link" href={monitor ? work.target : `#page=review-workspace&submission=${work.id}`}>{monitor ? tr("Открыть работу в курсе →") : tr("Открыть и проверить →")}</a>{!monitor && work.reviewer_id !== userId && <button className="secondary" disabled={busy === work.id} onClick={() => take(work)}>{tr("Взять на проверку")}</button>}</div>
    </article>)}</div>
    {data && (page > 1 || data.next_page) && <div className="action-row"><button className="secondary" disabled={page === 1} onClick={() => { setLoading(true); setPage(p => p - 1) }}>{tr("← Назад")}</button><span>{tr("Страница ")}{page}</span><button className="secondary" disabled={!data.next_page} onClick={() => { setLoading(true); setPage(data.next_page as number) }}>{tr("Далее →")}</button></div>}
  </section>
}
