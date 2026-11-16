import { ct } from '../../i18n/content'
import { t as tr } from '../../i18n/language'
import { useEffect, useState, type FormEvent } from 'react'
import { apiRequest } from '../../api'
import { errorMessage, formatDate, inputDate, isoDate, type Submission } from '../study/types'

type Criterion = { id: string; label: string; max: number }
type Rubric = { version: number; criteria: Criterion[]; locked: boolean; max_score: number }

export function RubricPanel({ assignmentId, runId, canEdit = false }: { assignmentId: number; runId: number; canEdit?: boolean }) {
  const [rubric, setRubric] = useState<Rubric | null>(null), [editing, setEditing] = useState(false), [error, setError] = useState(''), [busy, setBusy] = useState(false)
  useEffect(() => { let alive = true; apiRequest<Rubric>(`/api/workspace/assignments/${assignmentId}/rubric/?run_id=${runId}`).then(v => { if (alive) setRubric(v) }).catch(e => { if (alive) setError(errorMessage(e)) }); return () => { alive = false } }, [assignmentId, runId])
  async function save(e: FormEvent) {
    e.preventDefault(); if (!rubric) return; setBusy(true); setError('')
    try { setRubric(await apiRequest<Rubric>(`/api/workspace/assignments/${assignmentId}/rubric/?run_id=${runId}`, 'PUT', rubric)); setEditing(false) } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }
  return <div className="rubric-panel">{error && <p role="alert" className="error">{tr(error)}</p>}
    {rubric && <>{rubric.criteria.length > 0 && <><strong>{tr("Как оценивается работа")}</strong><div className="rubric-criteria">{rubric.criteria.map(c => <div key={c.id}><span>{ct(c, "label")}</span><strong>{tr("до ")}{c.max}</strong></div>)}</div></>}
      {canEdit && !rubric.locked && <details open={editing} onToggle={e => setEditing(e.currentTarget.open)}><summary>{rubric.criteria.length ? tr("Изменить критерии оценки") : tr("Добавить критерии оценки")}</summary><form className="study-form compact" onSubmit={save}><p className="muted">{tr("Сумма критериев: ")}{rubric.criteria.reduce((s, c) => s+c.max, 0)} {tr(" из ")}{rubric.max_score}</p>
        {rubric.criteria.map((c, i) => <div className="rubric-editor-row" key={c.id}><label>{tr("Критерий")}<input required maxLength={200} value={c.label} onChange={e => setRubric({ ...rubric, criteria: rubric.criteria.map((v, j) => i === j ? { ...v, label: e.target.value } : v) })} /></label><label>{tr("Макс. балл")}<input type="number" min={1} max={10000} required value={c.max} onChange={e => setRubric({ ...rubric, criteria: rubric.criteria.map((v, j) => i === j ? { ...v, max: Number(e.target.value) } : v) })} /></label><button className="secondary" type="button" aria-label={tr("Убрать критерий {0}", [i+1])} onClick={() => setRubric({ ...rubric, criteria: rubric.criteria.filter((_, j) => j !== i) })}>×</button></div>)}
        <div className="action-row"><button type="button" className="secondary" disabled={rubric.criteria.length >= 20} onClick={() => setRubric({ ...rubric, criteria: [...rubric.criteria, { id: crypto.randomUUID(), label: '', max: 1 }] })}>{tr("+ Критерий")}</button><button disabled={busy}>{tr("Сохранить критерии")}</button></div></form></details>}
      {canEdit && rubric.locked && rubric.criteria.length > 0 && <p className="muted">{tr("Критерии зафиксированы после первой сдачи · версия ")}{rubric.version}.</p>}</>}
  </div>
}

export function RubricResult({ result, label = tr("Разбор оценки по критериям") }: { result: Submission['rubric_result']; label?: string }) {
  if (!result?.criteria?.length) return null
  return <div className="rubric-result"><strong>{ct(label)}</strong>{result.criteria.map(c => <div key={c.id}><span>{ct(c, "label")}{c.comment && <small>{ct(c, "comment")}</small>}</span><strong>{c.score}/{c.max}</strong></div>)}</div>
}

export function ReviewHistory({ reviews }: { reviews: Submission['reviews'] }) {
  if (!reviews.length) return null
  return <details className="review-history"><summary>{tr("История проверки (")}{reviews.length})</summary>{reviews.map((r, i) => <article key={i}><p><strong>{r.reviewer}</strong><span className="person-role">{tr(r.reviewer_role_label)}</span> · {formatDate(r.created_at)}</p><p>{r.action === 'returned' ? tr("Возвращено на доработку") : tr("Оценка: {0}", [r.score])}{r.rubric_result?.version ? tr(" · Критерии v{0}", [r.rubric_result.version]) : ''}</p><p className="preserve-text">{ct(r, "feedback")}</p><RubricResult result={r.rubric_result} label={tr("Критерии этой проверки")} /></article>)}</details>
}

export function GradingForm({ submission, maxScore, assignmentId, runId, onSaved }: { submission: Submission; maxScore: number; assignmentId: number; runId: number; onSaved: () => void }) {
  const [rubric, setRubric] = useState<Rubric | null>(null), [scores, setScores] = useState<Record<string, number>>({}), [comments, setComments] = useState<Record<string, string>>({})
  const [action, setAction] = useState('grade'), [error, setError] = useState(''), [busy, setBusy] = useState(false)
  const [due] = useState(() => inputDate(new Date(Date.now()+72*3600000).toISOString()))
  useEffect(() => { let alive = true; apiRequest<Rubric>(`/api/workspace/assignments/${assignmentId}/rubric/?run_id=${runId}`).then(v => { if (alive) { setRubric(v); setScores(Object.fromEntries(v.criteria.map(c => [c.id, submission.rubric_result?.criteria?.find(r => r.id === c.id)?.score ?? 0]))); setComments(Object.fromEntries((submission.rubric_result?.criteria || []).map(c => [c.id, c.comment]))) } }).catch(e => { if (alive) setError(errorMessage(e)) }); return () => { alive = false } }, [assignmentId, runId, submission.rubric_result])
  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const form = new FormData(e.currentTarget); setBusy(true); setError('')
    try {
      await apiRequest(`/api/workspace/reviews/${submission.id}/`, 'PUT', { expected_version: submission.review_version, score: rubric?.criteria.length ? Object.values(scores).reduce((s, v) => s+v, 0) : Number(form.get('score')),
        feedback: form.get('feedback'), return_for_revision: action === 'return', ...(action === 'return' ? { revision_due_at: isoDate(form.get('revision_due_at')) } : {}), criteria_scores: scores, criteria_comments: comments })
      onSaved()
    } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }
  return <form className="study-form compact" onSubmit={save}><label>{tr("Действие")}<select value={action} onChange={e => setAction(e.target.value)}><option value="grade">{tr("Выставить оценку")}</option><option value="return">{tr("Вернуть на доработку")}</option></select></label>
    {action === 'return' ? <label>{tr("Исправить и отправить до")}<input name="revision_due_at" type="datetime-local" required defaultValue={due} /></label> : rubric?.criteria.length ? <><div className="grading-criteria">{rubric.criteria.map(c => <fieldset key={c.id}><legend>{ct(c, "label")}</legend><label>{tr("Балл (0–")}{c.max})<input type="number" required min={0} max={c.max} value={scores[c.id] ?? 0} onChange={e => setScores(v => ({ ...v, [c.id]: Number(e.target.value) }))} /></label><label>{tr("Комментарий к критерию")}<input maxLength={1000} value={comments[c.id] ?? ''} onChange={e => setComments(v => ({ ...v, [c.id]: e.target.value }))} /></label></fieldset>)}</div><strong>{tr("Итого: ")}{Object.values(scores).reduce((s, v) => s+v, 0)}/{maxScore}</strong></> : <label>{tr("Балл (0–")}{maxScore})<input type="number" name="score" min={0} max={maxScore} defaultValue={submission.score ?? 0} required /></label>}
    <label>{tr("Комментарий преподавателя")}<textarea name="feedback" aria-label={tr("Комментарий преподавателя")} required={action === 'return'} maxLength={10000} defaultValue={submission.feedback} rows={4} /></label>
    
    {error && <p role="alert" className="error">{tr(error)}</p>}<button disabled={busy || !rubric}>{busy ? tr("Сохраняем…") : action === 'return' ? tr("Вернуть на доработку с новым сроком") : tr("Сохранить оценку")}</button></form>
}

export default function ReviewWorkspace() {
  const id = Number(new URLSearchParams(location.hash.slice(1)).get('submission'))
  const [data, setData] = useState<{ submission: Submission; assignment: { id: number; title: string; description: string; max_score: number }; course: string; run: string; run_id: number; course_id: number; next_id: number | null } | null>(null)
  const [error, setError] = useState(''), [revision, setRevision] = useState(0), [message, setMessage] = useState('')
  useEffect(() => { let alive = true; apiRequest<NonNullable<typeof data>>(`/api/workspace/reviews/${id}/`).then(v => { if (alive) { setData(v); setError('') } }).catch(e => { if (alive) setError(errorMessage(e)) }); return () => { alive = false } }, [id, revision])
  return <section className="study-section"><div className="section-heading"><div><p className="eyebrow">{tr("Рабочее место преподавателя")}</p><h2>{tr("Проверка работы")}</h2></div><div className="action-row"><button className="secondary" onClick={() => { setMessage(''); setRevision(v => v+1) }}>{tr("Обновить работу")}</button><a className="button-link" href="#page=reviews">{tr("← Вся очередь")}</a></div></div>{error && <p role="alert" className="error">{tr(error)}</p>}{message && <p className="success" role="status">{tr(message)}</p>}
    {data && <><div className="review-workbench"><article className="hub-panel review-answer"><p className="eyebrow">{ct(data, "course")} · {ct(data, "run")}</p><h3>{ct(data.assignment, "title")}</h3><p><strong>{data.submission.student}</strong><span className="person-role">{tr("Студент")}</span></p><p className="muted">{tr("Попытка ")}{data.submission.attempt_no} · {formatDate(data.submission.submitted_at)}</p><details><summary>{tr("Условие задания")}</summary><p className="preserve-text">{ct(data.assignment, "description")}</p></details><h4>{tr("Ответ ученика")}</h4><p className="preserve-text">{ct(data.submission, "text_answer") || tr("Текстовый ответ не приложен.")}</p>{data.submission.file_url && <a className="button-link" href={data.submission.file_url} target="_blank" rel="noreferrer">{tr("Открыть файл: ")}{data.submission.file_name}</a>}<RubricResult result={data.submission.rubric_result} /><ReviewHistory reviews={data.submission.reviews} /></article>
      <aside className="hub-panel review-grading"><h3>{data.submission.status === 'graded' ? tr("Работа проверена") : data.submission.status === 'returned' ? tr("Работа на доработке") : tr("Оценка и обратная связь")}</h3><GradingForm key={`${id}-${data.submission.review_version}`} submission={data.submission} assignmentId={data.assignment.id} runId={data.run_id} maxScore={data.assignment.max_score} onSaved={() => { setMessage('Изменения сохранены.'); setRevision(v => v+1) }} /></aside></div>
      <div className="review-next"><a className="button-link" href={`#course=${data.course_id}&run=${data.run_id}&tab=assignments&submission=${id}`}>{tr("Открыть в курсе")}</a>{data.next_id && <a className="primary-link" href={`#page=review-workspace&submission=${data.next_id}`} onClick={() => setMessage('')}>{tr("Следующая работа →")}</a>}</div></>}
  </section>
}
