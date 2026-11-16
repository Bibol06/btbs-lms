import { ct } from '../../i18n/content'
import { t as tr } from '../../i18n/language'
import { useEffect, useState } from 'react'
import { apiRequest } from '../../api'
import { errorMessage, formatDate } from '../study/types'

type Notification = { id: number; kind: string; title: string; course: string; target: string; created_at: string; read_at: string | null }

export function NotificationCount() {
  const [count, setCount] = useState(0)
  useEffect(() => {
    let alive = true
    async function load() {
      try { const data = await apiRequest<{ unread: number }>('/api/communication/notifications/'); if (alive) setCount(data.unread) } catch { /* The page displays connection errors. */ }
    }
    void load(); const timer = window.setInterval(load, 15000)
    window.addEventListener('lms-notifications-updated', load)
    return () => { alive = false; window.clearInterval(timer); window.removeEventListener('lms-notifications-updated', load) }
  }, [])
  return <>{count ? ` (${count})` : ''}</>
}

export default function Notifications() {
  const [page, setPage] = useState(1)
  const [revision, setRevision] = useState(0)
  const [data, setData] = useState<{ notifications: Notification[]; total: number; unread: number } | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let alive = true
    apiRequest<typeof data>(`/api/communication/notifications/?page=${page}`).then(value => { if (alive) { setData(value); setError('') } }).catch(err => { if (alive) setError(errorMessage(err)) })
    return () => { alive = false }
  }, [page, revision])
  async function read(id?: number) {
    try { await apiRequest('/api/communication/notifications/', 'PATCH', id ? { id } : { all: true }); setRevision(v => v + 1); window.dispatchEvent(new Event('lms-notifications-updated')) }
    catch (err) { setError(errorMessage(err)) }
  }
  return <section className="study-section"><div className="section-heading"><h2>{tr("Уведомления ")}{data ? tr("· {0} непрочитанных", [data.unread]) : ''}</h2><button className="secondary" onClick={() => read()}>{tr("Прочитать все")}</button></div>
    {error && <p className="error" role="alert">{tr(error)}</p>}
    {data?.notifications.map(n => <article className="study-card" key={n.id}><h3>{!n.read_at ? '● ' : ''}{tr(n.title)}</h3><p className="muted">{ct(n, "course")} · {formatDate(n.created_at)}</p><div className="action-row"><a href={n.target} onClick={() => { void read(n.id) }}>{tr("Открыть")}</a>{!n.read_at && <button className="secondary" onClick={() => read(n.id)}>{tr("Отметить прочитанным")}</button>}</div></article>)}
    {data && !data.notifications.length && <p className="empty-state">{tr("Уведомлений пока нет.")}</p>}
    <div className="action-row"><button className="secondary" disabled={page === 1} onClick={() => setPage(v => v - 1)}>{tr("Назад")}</button><span>{tr("Страница ")}{page}</span><button className="secondary" disabled={!data || page*30 >= data.total} onClick={() => setPage(v => v + 1)}>{tr("Дальше")}</button></div>
  </section>
}
