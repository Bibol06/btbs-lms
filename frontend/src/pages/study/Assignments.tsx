import MaterialViewer from '../../components/MaterialViewer'
import { ct } from '../../i18n/content'
import { t as tr } from '../../i18n/language'
import { GradingForm, RubricPanel, RubricResult, ReviewHistory } from '../workspace/Grading'
import RoleBadge from '../../components/RoleBadge'
import { useEffect, useState, type FormEvent } from 'react'

import { apiRequest } from '../../api'

import { type Assignment, type Reviewer, errorMessage, formatDate, isoDate } from './types'

import { useNow } from './useNow'

import ConfirmAction from './ConfirmAction'

import ScheduleForm from './ScheduleForm'
import DeadlineFields from './DeadlineFields'
import { Extensions, ReviewerForm, SubmissionStatus } from './DeadlineTools'


function AssignmentEditor({ courseId, initial, onSaved, onCancel }: {

  courseId: number; initial?: Assignment; onSaved: () => void; onCancel: () => void

}) {

  const [busy, setBusy] = useState(false)

  const [error, setError] = useState('')

  async function save(event: FormEvent<HTMLFormElement>) {

    event.preventDefault()

    const form = new FormData(event.currentTarget)

    setBusy(true); setError('')

    try {

      await apiRequest(initial ? `/api/study/assignments/${initial.id}/` : `/api/study/courses/${courseId}/assignments/`, initial ? 'PATCH' : 'POST', {

        title: form.get('title'), description: form.get('description'), due_at: isoDate(form.get('due_at')),

        max_score: Number(form.get('max_score')), max_attempts: Number(form.get('max_attempts')),

        is_published: form.has('is_published'), allow_late: form.has('allow_late'), cutoff_at: isoDate(form.get('cutoff_at')), review_hours: Number(form.get('review_hours')),

      })

      onSaved()

    } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }

  }

  return <form className="study-form" onSubmit={save}>

    <h3>{initial ? tr("Редактирование задания") : tr("Новое задание")}</h3>

    <label>{tr("Название задания")}<input name="title" defaultValue={initial?.title} required maxLength={200} /></label>

    <label>{tr("Условие")}<textarea name="description" defaultValue={initial?.description} maxLength={50000} rows={5} /></label>

    <div className="form-grid">



      <label>{tr("Максимальный балл")}<input type="number" name="max_score" min={1} max={10000} defaultValue={initial?.max_score ?? 100} readOnly={Boolean(initial?.submissions.length)} required /></label>

      <label>{tr("Количество попыток")}<input type="number" name="max_attempts" min={1} max={100} defaultValue={initial?.max_attempts ?? 3} readOnly={Boolean(initial?.submissions.length)} required /></label>

    </div>

    <DeadlineFields initial={initial} />
    <label className="check"><input type="checkbox" name="is_published" defaultChecked={initial?.is_published} /> {tr(" Опубликовать задание")}</label>

    {error && <p role="alert" className="error">{tr(error)}</p>}

    <div className="action-row"><button disabled={busy}>{tr("Сохранить задание")}</button><button type="button" className="secondary" onClick={onCancel} disabled={busy}>{tr("Отмена")}</button></div>

  </form>

}


function SubmitForm({ assignment, runId, onSaved }: { assignment: Assignment; runId: number; onSaved: () => void }) {

  const now = useNow()

  const [busy, setBusy] = useState(false)

  const [error, setError] = useState('')

  async function submit(event: FormEvent<HTMLFormElement>) {

    event.preventDefault()

    const element = event.currentTarget

    const data = new FormData(element)

    if (data.get('file') instanceof File && (data.get('file') as File).size === 0) data.delete('file')

    setBusy(true); setError('')

    try {

      await apiRequest(`/api/study/assignments/${assignment.id}/submit/?run_id=${runId}`, 'POST', data)

      element.reset(); onSaved()

    } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }

  }

  const limitReached = assignment.submissions.filter(s => s.status !== 'returned').length >= assignment.max_attempts
  const closed = (assignment.window?.closes_at && now >= new Date(assignment.window.closes_at).getTime()) || !assignment.window?.can_submit || limitReached

  if (assignment.submissions[0]?.status === 'submitted') return <p className="deadline-note">{tr("Работа отправлена и ожидает проверки.")}</p>
  return closed ? <p className="muted">{limitReached ? tr("Все попытки использованы.") : tr("Приём работ закрыт.")}</p> : <form className="study-form compact" onSubmit={submit}>

    <label>{tr("Ваш ответ")}<textarea name="text_answer" rows={4} maxLength={50000} placeholder={tr("Напишите решение или приложите файл")} /></label>

    <label>{tr("Файл ответа (до 20 МБ)")}<input type="file" name="file" accept=".pdf,.docx,.pptx,.jpg,.jpeg,.png" /></label>

    {error && <p role="alert" className="error">{tr(error)}</p>}

    <button disabled={busy}>{busy ? tr("Отправляем…") : tr("Отправить работу")}</button>

  </form>

}


export default function Assignments({ courseId, runId, assignments, manage, canEdit, reviewers, refresh, embedded = false }: {

  courseId: number; runId: number; assignments: Assignment[]; manage: boolean; canEdit: boolean; reviewers: Reviewer[]; refresh: () => void; embedded?: boolean

}) {

  const now = useNow()
  const [editor, setEditor] = useState<Assignment | 'new' | null>(null)

  const [error, setError] = useState('')

  const [busy, setBusy] = useState<number | null>(null)

  const submissionId = Number(new URLSearchParams(location.hash.slice(1)).get('submission'))
  useEffect(() => {
    if (submissionId) document.getElementById(`submission-${submissionId}`)?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [submissionId])
  function saved() { setEditor(null); refresh() }

  async function change(a: Assignment, remove = false) {

    setBusy(a.id); setError('')

    try {

      await apiRequest(`/api/study/assignments/${a.id}/`, remove ? 'DELETE' : 'PATCH', remove ? undefined : { is_published: !a.is_published })

      refresh()

    } catch (err) { setError(errorMessage(err)) } finally { setBusy(null) }

  }

  return <section className={`study-section ${embedded ? 'is-embedded' : ''}`}>

    {!(embedded && !canEdit) && <div className="section-heading"><h2>{tr("Домашние задания")}</h2>{canEdit && <button onClick={() => setEditor('new')}>{tr("+ Новое задание")}</button>}</div>}

    {error && <p role="alert" className="error">{tr(error)}</p>}

    {editor && <AssignmentEditor key={editor === 'new' ? 'new' : editor.id} courseId={courseId} initial={editor === 'new' ? undefined : editor} onSaved={saved} onCancel={() => setEditor(null)} />}

    {!assignments.length && <p className="empty-state">{tr("Заданий пока нет.")}</p>}

    {assignments.map(a => <article className="study-card" key={a.id}>

      <div className="section-heading"><h3>{ct(a, "title")}</h3>{manage && <span className={`badge ${a.is_published ? 'is-success' : 'is-warning'}`}>{a.is_published ? tr("Опубликовано") : tr("Черновик")}</span>}</div>

      <p className="preserve-text">{ct(a, "description")}</p><RubricPanel key={`${a.id}-${a.max_score}-${a.submissions.length}`} assignmentId={a.id} runId={runId} canEdit={canEdit} />

      <div className="deadline-summary"><div><small>{a.window?.source === 'personal' ? tr("Ваш индивидуальный срок") : tr("Сдать до")}</small><strong>{formatDate(a.window?.due_at ?? a.due_at)}</strong></div><div><small>{tr("Приём закрывается")}</small><strong>{formatDate(a.window ? a.window.closes_at : a.allow_late ? a.cutoff_at : a.due_at)}</strong></div><div><small>{tr("Проверка после отправки")}</small><strong>{tr("До ")}{a.review_hours} {tr(" ч.")}</strong></div></div>
      <p className="muted">{manage ? <>{tr("До ")}{a.max_score} {tr(" баллов · Попыток: ")}{a.max_attempts}</> : tr("До {0} баллов · использовано попыток: {1}/{2}", [a.max_score, a.submissions.filter(s => s.status !== 'returned').length, a.max_attempts])}{a.allow_late && a.window?.source !== 'personal' ? tr(" · Опоздания разрешены, баллы автоматически не снижаются") : ''}</p>
      {a.window?.source === 'personal' && <p className="deadline-note">{tr("Для вас назначен отдельный срок. ")}{ct(a.window, "note")}</p>}
      {!manage && a.window?.due_at && a.window.allow_late && now >= new Date(a.window.due_at).getTime() && a.window.can_submit && <p className="deadline-note warning">{tr("Сдача с опозданием разрешена.")}</p>}

      {canEdit && <div className="action-row">

        <button className="secondary" onClick={() => setEditor(a)}>{tr("Редактировать")}</button>

        <button className="secondary" disabled={busy === a.id} onClick={() => change(a)}>{a.is_published ? tr("Снять с публикации") : tr("Опубликовать")}</button>

        {!a.submissions.length && <ConfirmAction label={tr("Удалить задание")} question={tr("Удалить задание «{0}»?", [a.title])} disabled={busy === a.id} onConfirm={() => change(a, true)} />}

      </div>}

      {manage && <><ScheduleForm courseId={courseId} runId={runId} kind="assignment" activity={a} onSaved={refresh} /><Extensions assignmentId={a.id} runId={runId} /></>}

      {!manage && a.submissions[0]?.status === 'submitted' && <SubmissionStatus submission={a.submissions[0]} manage={false} />}
      {(manage || a.submissions.length > 0) && <h4>{manage ? tr("Работы студентов ({0})", [a.submissions.length]) : tr("Ваши отправки ({0})", [a.submissions.length])}</h4>}

      {a.submissions.map((s, index) => <details className="submission" id={`submission-${s.id}`} open={submissionId === s.id || (!manage && index === 0 && s.status === 'returned')} key={`${s.id}-${s.graded_at}`}>

        <summary>{manage && <><strong>{s.student}</strong><RoleBadge label={tr(s.student_role_label)} /> · </>}{tr("Попытка ")}{s.attempt_no} · {formatDate(s.submitted_at)} · {s.score === null ? s.status === 'returned' ? tr("На доработке") : tr("На проверке") : tr("{0}/{1} баллов", [s.score, a.max_score])}</summary>

        <SubmissionStatus submission={s} manage={manage} />
        <p className="preserve-text">{ct(s, "text_answer")}</p>

        {s.file_url && <MaterialViewer material={{url:s.file_url, title:s.file_name || tr("Файл"), filename:s.file_name}} />}

        <RubricResult result={s.rubric_result} />{s.feedback && <p className="feedback"><strong>{tr("Комментарий:")}</strong> {ct(s, "feedback")}</p>}

        <ReviewHistory reviews={s.reviews} />

        {manage && <>{s.status === 'submitted' && <ReviewerForm submission={s} reviewers={reviewers} saved={refresh} />}<GradingForm submission={s} assignmentId={a.id} runId={runId} maxScore={a.max_score} onSaved={refresh} /></>}

      </details>)}

      {!manage && <SubmitForm assignment={a} runId={runId} onSaved={refresh} />}

    </article>)}

  </section>

}

