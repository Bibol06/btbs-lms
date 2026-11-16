import { ct } from '../../i18n/content'
import PreparedText from '../../components/PreparedText'
import { localizedLabels, t as tr } from '../../i18n/language'
import { useEffect, useState } from 'react'
import { apiRequest } from '../../api'
import { errorMessage } from '../study/types'

type Pulse = { can_manage: boolean; choice?: string; note?: string; total?: number; counts?: Record<string, number>; notes?: { id: number; student: string; choice: string; note: string }[] }
const labels: Record<string, string> = localizedLabels({ clear: 'Понятно', hard: 'Сложно', example: 'Нужен пример' })
export default function LessonPulse({ lessonId, runId }: { lessonId: number; runId: number }) {
  const [data, setData] = useState<Pulse | null>(null), [choice, setChoice] = useState(''), [note, setNote] = useState(''), [message, setMessage] = useState(''), [error, setError] = useState(''), [busy, setBusy] = useState(false)
  useEffect(() => { let alive = true; apiRequest<Pulse>(`/api/workspace/lessons/${lessonId}/pulse/?run_id=${runId}`).then(v => { if (alive) { setData(v); setChoice(v.choice || ''); setNote(v.note || '') } }).catch(e => { if (alive) setError(errorMessage(e)) }); return () => { alive = false } }, [lessonId, runId])
  return <section className="hub-panel lesson-pulse"><h3>{data?.can_manage ? tr("Как ученики понимают урок") : tr("Насколько понятен этот урок?")}</h3>{data?.can_manage && <p className="muted">{tr("Ответов: {0}", [data.total ?? 0])}</p>}{error && <p role="alert" className="error">{tr(error)}</p>}
    {data?.can_manage ? <><div className="pulse-counts">{Object.entries(labels).map(([id, label]) => <div key={id}><strong>{data.counts?.[id] ?? 0}</strong><span>{ct(label)}</span></div>)}</div>{data.notes?.map(n => <article key={n.id}><p><strong>{n.student}</strong> · {labels[n.choice]}</p><PreparedText original={n.note} text={ct(n, 'note')} /></article>)}</> : data && <form onSubmit={async e => { e.preventDefault(); setBusy(true); setError(''); try { await apiRequest(`/api/workspace/lessons/${lessonId}/pulse/?run_id=${runId}`, 'PUT', { choice, note }); setMessage('Спасибо, ответ сохранён. Его можно изменить.'); } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) } }}><div className="pulse-choices">{Object.entries(labels).map(([id, label]) => <label className={choice === id ? 'selected' : ''} key={id}><input type="radio" name={`pulse-${lessonId}`} value={id} checked={choice === id} onChange={() => setChoice(id)} required />{ct(label)}</label>)}</div><label className="search-field">{tr("Что стоит пояснить? Необязательно")}<textarea value={note} maxLength={1000} rows={2} onChange={e => setNote(e.target.value)} /></label><button disabled={busy || !choice}>{tr("Сохранить ответ")}</button>{message && <p role="status" className="success">{tr(message)}</p>}</form>}
  </section>
}
