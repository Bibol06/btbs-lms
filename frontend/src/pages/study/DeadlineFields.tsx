import { t as tr } from '../../i18n/language'
import { useState } from 'react'
import { inputDate } from './types'

export type DeadlinePolicy = { due_at?: string | null; cutoff_at?: string | null; allow_late?: boolean; review_hours?: number }

export default function DeadlineFields({ initial }: { initial?: DeadlinePolicy }) {
  const [late, setLate] = useState(initial?.allow_late ?? false)
  return <fieldset className="deadline-policy"><legend>{tr("Сдача и проверка")}</legend>
    
    <label>{tr("Сдать до")}<input type="datetime-local" name="due_at" defaultValue={inputDate(initial?.due_at)} /></label>
    <label className="check"><input type="checkbox" name="allow_late" checked={late} onChange={e => setLate(e.target.checked)} /> {tr(" Разрешить сдачу с опозданием")}</label>
    {late ? <><label>{tr("Окончательно закрыть приём")}<input type="datetime-local" name="cutoff_at" defaultValue={inputDate(initial?.cutoff_at)} /></label></> : null}
    <label>{tr("Проверить работу в течение, часов")}<input type="number" name="review_hours" min={1} max={720} defaultValue={initial?.review_hours ?? 48} required /></label>
  </fieldset>
}
