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
  const pages = data ? Math.max(1, Math.ceil(data.total / 30)) : 1
  return <section className="page notifications-page" aria-labelledby="notifications-title">
    <header className="page-header">
      <div><h2 className="page-title" id="notifications-title">{tr('Уведомления')}</h2>
        {data && <p className="page-sub">{data.unread ? tr('Непрочитанных: {0}', [String(data.unread)]) : tr('Все уведомления прочитаны')}</p>}</div>
      {data && data.unread > 0 && <button className="secondary" onClick={() => read()}>{tr('Прочитать все')}</button>}
    </header>
    {error && <p className="error" role="alert">{tr(error)}</p>}
    {!data && !error && <p className="muted" role="status">{tr('Загрузка…')}</p>}
    {data && !data.notifications.length && <div className="empty"><h3>{tr('Уведомлений пока нет.')}</h3><p>{tr('Здесь появятся оценки, ответы преподавателя и новости курсов.')}</p></div>}
    {data && data.notifications.length > 0 && <ul className="list">{data.notifications.map(n => <li key={n.id} className={`list-row notification-row ${n.read_at ? '' : 'is-unread'}`}>
      <span className="notification-dot" aria-hidden="true" />
      <div className="list-row-main">
        <p className="list-row-title"><a href={n.target} onClick={() => { if (!n.read_at) void read(n.id) }}>{tr(n.title)}</a>{!n.read_at && <span className="visually-hidden"> · {tr('Не прочитано')}</span>}</p>
        <p className="list-row-meta">{ct(n, 'course')} · {formatDate(n.created_at)}</p>
      </div>
      {!n.read_at && <div className="list-row-side"><button className="ghost small" onClick={() => read(n.id)}>{tr('Отметить прочитанным')}</button></div>}
    </li>)}</ul>}
    {pages > 1 && <nav className="pager" aria-label={tr('Страницы уведомлений')}><button className="secondary small" disabled={page === 1} onClick={() => setPage(v => v - 1)}>{tr('Назад')}</button><span>{tr('Страница {0} из {1}', [String(page), String(pages)])}</span><button className="secondary small" disabled={page >= pages} onClick={() => setPage(v => v + 1)}>{tr('Дальше')}</button></nav>}
  </section>
}
