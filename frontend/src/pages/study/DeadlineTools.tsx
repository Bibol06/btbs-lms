import { t as tr } from '../../i18n/language'
import RoleBadge from '../../components/RoleBadge'
import { useEffect, useState, type FormEvent } from 'react'
import { apiRequest } from '../../api'
import { errorMessage, formatDate, inputDate, isoDate, type Reviewer, type Submission, type SubmissionWindow } from './types'

export function SubmissionStatus({ submission: s, manage }: { submission: Submission; manage: boolean }) {
  return <div className="submission-status">
    {s.is_late && <span className="deadline-pill warning">{tr("Сдано с опозданием")}</span>}
    {s.status === 'submitted' && <><p><strong>{tr("Ожидаемая проверка:")}</strong> {s.review_due_at ? formatDate(s.review_due_at) : tr("Срок пока не назначен")}{s.reviewer && <span> · {s.reviewer}<RoleBadge label={tr(s.reviewer_role_label)} /></span>}</p>{s.review_state === 'overdue' && <p className="deadline-note warning">{manage ? tr("Срок проверки прошёл. Работу всё ещё можно проверить.") : tr("Проверка задерживается. Работа сохранена — повторно отправлять её не нужно.")}</p>}</>}
    {s.status === 'returned' && <p className="deadline-note warning"><strong>{tr("Нужна доработка.")}</strong> {s.revision_due_at ? tr("Отправьте исправление до {0}.", [formatDate(s.revision_due_at)]) : tr("Уточните новый срок у преподавателя.")}</p>}
    {s.status === 'graded' && <p className="deadline-note done">{tr("Работа проверена. Оценка и комментарий сохранены.")}</p>}
  </div>
}

export function ReviewerForm({ submission, reviewers, saved }: { submission: Submission; reviewers: Reviewer[]; saved: () => void }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError('')
    const form = new FormData(event.currentTarget)
    const payload: Record<string, unknown> = { reviewer_id: Number(form.get('reviewer_id')) }
    if (form.get('review_due_at') !== inputDate(submission.review_due_at)) payload.review_due_at = isoDate(form.get('review_due_at'))
    try { await apiRequest(`/api/study/submissions/${submission.id}/reviewer/`, 'PATCH', payload); saved() }
    catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }
  return <details className="reviewer-settings"><summary>{tr("Ответственный и срок проверки")}</summary><form className="study-form compact" onSubmit={save}>
    <label>{tr("Ответственный преподаватель")}<select name="reviewer_id" required defaultValue={submission.reviewer_id ?? ''}><option value="">{tr("Выберите преподавателя")}</option>{reviewers.map(r => <option value={r.id} key={r.id}>{r.display_name} · {tr(r.role_label)}</option>)}</select></label>
    <label>{tr("Проверить до")}<input type="datetime-local" name="review_due_at" defaultValue={inputDate(submission.review_due_at)} /></label>
    {error && <p className="error" role="alert">{tr(error)}</p>}<button disabled={busy}>{tr("Сохранить ответственного и срок")}</button>
  </form></details>
}

export function Extensions({ assignmentId, runId }: { assignmentId: number; runId: number }) {
  const [open, setOpen] = useState(false)
  const [students, setStudents] = useState<{ id: number; student: string; window: SubmissionWindow }[]>([])
  const [selected, setSelected] = useState('')
  const [revision, setRevision] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  useEffect(() => {
    if (!open) return
    let alive = true
    apiRequest<{ students: typeof students }>(`/api/study/assignments/${assignmentId}/extensions/?run_id=${runId}`)
      .then(data => { if (alive) setStudents(data.students) }).catch(err => { if (alive) setError(errorMessage(err)) })
    return () => { alive = false }
  }, [assignmentId, runId, open, revision])
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(''); setMessage('')
    const form = new FormData(event.currentTarget)
    try {
      await apiRequest(`/api/study/assignments/${assignmentId}/extensions/?run_id=${runId}`, 'POST', { enrollment_id: Number(selected), deadline_at: isoDate(form.get('deadline_at')), reason: form.get('reason') })
      setMessage('Индивидуальный срок сохранён. Ученик получит уведомление.'); setRevision(v => v + 1)
    } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }
  const student = students.find(s => s.id === Number(selected))
  return <details className="extension-settings" onToggle={event => setOpen(event.currentTarget.open)}><summary>{tr("Продлить срок отдельному ученику")}</summary>{open && <form className="study-form compact" onSubmit={save}>
    
    <label>{tr("Ученик")}<select required value={selected} onChange={e => setSelected(e.target.value)}><option value="">{tr("Выберите ученика")}</option>{students.map(s => <option value={s.id} key={s.id}>{s.student} {tr(" · Студент")}</option>)}</select></label>
    {student && <p className="muted">{tr("Текущий срок: ")}{formatDate(student.window.due_at)} {tr(" · Приём до: ")}{formatDate(student.window.closes_at)}</p>}
    <label>{tr("Новый срок сдачи")}<input type="datetime-local" name="deadline_at" required /></label><label>{tr("Причина / комментарий")}<input name="reason" maxLength={500} placeholder={tr("Например: продление по согласованию")} /></label>
    {error && <p className="error" role="alert">{tr(error)}</p>}{message && <p className="success" role="status">{tr(message)}</p>}<button disabled={busy || !selected}>{tr("Назначить индивидуальный срок")}</button>
  </form>}</details>
}
