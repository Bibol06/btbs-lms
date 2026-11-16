import { ct } from '../../i18n/content'
import { t as tr, getLocale } from '../../i18n/language'
import { useState } from 'react'

export default function WeekCalendar({ tasks }: { tasks: { id: string; title: string; due_at: string | null; target: string; state: string; course: string }[] }) {
  const [offset, setOffset] = useState(0)
  const start = new Date(); start.setHours(0, 0, 0, 0); start.setDate(start.getDate()-((start.getDay()+6)%7)+offset*7)
  const days = Array.from({ length: 7 }, (_, i) => { const d = new Date(start); d.setDate(start.getDate()+i); return d })
  const sameDay = (a: Date, b: Date) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate()
  return <details className="hub-panel week-calendar"><summary>{tr("Календарь сроков на неделю")}</summary><div className="section-heading"><strong>{days[0].toLocaleDateString(getLocale())} — {days[6].toLocaleDateString(getLocale())}</strong><div className="action-row"><button className="secondary" aria-label={tr("Предыдущая неделя")} onClick={() => setOffset(v => v-1)}>←</button><button className="secondary" onClick={() => setOffset(0)}>{tr("Эта неделя")}</button><button className="secondary" aria-label={tr("Следующая неделя")} onClick={() => setOffset(v => v+1)}>→</button></div></div><div className="week-scroll"><div className="week-grid">{days.map(d => <section className={sameDay(d, new Date()) ? 'today' : ''} key={d.toISOString()}><h4>{d.toLocaleDateString(getLocale(), { weekday: 'short', day: 'numeric', month: 'short' })}</h4>{tasks.filter(t => t.due_at && sameDay(new Date(t.due_at), d)).map(t => <a href={t.target} key={t.id}><strong>{ct(t, "title")}</strong><small>{ct(t, "course")}</small><span>{new Date(t.due_at!).toLocaleTimeString(getLocale(), { hour: '2-digit', minute: '2-digit' })}{t.state === 'graded' ? tr(" · Выполнено") : t.state === 'waiting' ? tr(" · На проверке") : ''}</span></a>)}</section>)}</div></div></details>
}
