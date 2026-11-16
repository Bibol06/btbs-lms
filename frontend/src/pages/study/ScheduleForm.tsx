import { t as tr } from '../../i18n/language'
import { useState, type FormEvent } from 'react'
import { apiRequest } from '../../api'
import DeadlineFields, { type DeadlinePolicy } from './DeadlineFields'
import { inputDate, isoDate, errorMessage } from './types'

export default function ScheduleForm({ courseId, runId, kind, activity, onSaved }: {
  courseId: number; runId: number; kind: 'assignment' | 'quiz'; activity: DeadlinePolicy & { id: number; due_at?: string | null; opens_at?: string | null; closes_at?: string | null; max_attempts: number; time_limit_sec?: number }; onSaved: () => void
}) {
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const data = new FormData(e.currentTarget); setBusy(true); setError('')
    try {
      await apiRequest(`/api/study/courses/${courseId}/schedule/?run_id=${runId}`, 'PUT', { kind, id: activity.id,
        due_at: isoDate(data.get('due_at')), allow_late: data.has('allow_late'), cutoff_at: isoDate(data.get('cutoff_at')), review_hours: Number(data.get('review_hours') || 48), opens_at: isoDate(data.get('opens_at')), closes_at: isoDate(data.get('closes_at')),
        max_attempts: Number(data.get('max_attempts')), time_limit_sec: Number(data.get('time_limit_sec') || 900) })
      onSaved()
    } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }
  return <details><summary>{tr("Настроить сроки и попытки этой группы")}</summary><form className="study-form compact" onSubmit={save}>
    {kind === 'assignment' ? <DeadlineFields initial={activity} /> : <><label>{tr("Открыть")}<input type="datetime-local" name="opens_at" defaultValue={inputDate(activity.opens_at)} /></label><label>{tr("Закрыть")}<input type="datetime-local" name="closes_at" defaultValue={inputDate(activity.closes_at)} /></label><label>{tr("Время в секундах")}<input type="number" name="time_limit_sec" defaultValue={activity.time_limit_sec} min={60} max={14400} required /></label></>}
    <label>{tr("Количество попыток")}<input type="number" name="max_attempts" min={1} max={100} defaultValue={activity.max_attempts} required /></label>
    {error && <p role="alert" className="error">{tr(error)}</p>}<button disabled={busy}>{tr("Сохранить сроки запуска")}</button>
  </form></details>
}
