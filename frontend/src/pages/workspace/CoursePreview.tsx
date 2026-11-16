import MaterialViewer from '../../components/MaterialViewer'
import { ct } from '../../i18n/content'
import RichLessonContent from '../../components/RichLessonContent'
import { t as tr } from '../../i18n/language'
import { useEffect, useState } from 'react'
import { apiRequest } from '../../api'
import { errorMessage } from '../study/types'

type PreviewStep = { id: number; title: string; kind: string; module: string; lesson: string; reason: string; action_reason: string; required: boolean; content: string; video_url: string;
  material?: { title: string; url: string; filename?: string; kind?: string }; assignment?: { title: string; description: string; max_score: number };
  questions?: { id: number; body: string; options: string[] }[]; problem?: { title: string; statement: string; starter_code: string; samples: { stdin: string; expected: string }[] } }
type Preview = { course: string; run: string; run_id: number; steps: PreviewStep[] }

export default function CoursePreview() {
  const params = new URLSearchParams(location.hash.slice(1)), courseId = Number(params.get('course_id')), runId = params.get('run_id') || ''
  const url = `/api/workspace/courses/${courseId}/preview/?run_id=${runId}`
  const [data, setData] = useState<Preview | null>(null), [selected, setSelected] = useState<number | null>(null), [completed, setCompleted] = useState<number[]>([])
  const [answers, setAnswers] = useState<Record<number, Record<string, number>>>({}), [code, setCode] = useState<Record<number, string>>({}), [message, setMessage] = useState(''), [error, setError] = useState(''), [busy, setBusy] = useState(false)
  const [manualScores, setManualScores] = useState<Record<number, number>>({})
  useEffect(() => { let alive = true; apiRequest<Preview>(url).then(v => { if (alive) { setData(v); setSelected(v.steps[0]?.id ?? null) } }).catch(e => { if (alive) setError(errorMessage(e)) }); return () => { alive = false } }, [url])
  const step = data?.steps.find(s => s.id === selected)
  async function execute(simulateReview = false) {
    if (!step) return; setBusy(true); setError(''); setMessage('')
    try {
      const result = await apiRequest<{ passed: boolean; score?: number; total?: number; message: string }>(url, 'POST', { step_id: step.id, completed, answers: answers[step.id] || {}, code: code[step.id] ?? step.problem?.starter_code ?? '', simulate_review: simulateReview, preview_score: manualScores[step.id] ?? step.assignment?.max_score ?? 0 })
      setMessage(`${result.message}${result.total !== undefined ? tr(" Результат: {0}/{1}.", [result.score, result.total]) : ''}`)
      if (result.passed) {
        const next = [...new Set([...completed, step.id])]; setCompleted(next)
        setData(await apiRequest<Preview>(url, 'POST', { completed: next }))
      }
    } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }
  return <section className="study-section preview-page"><div className="preview-banner"><div><strong>{tr("Предпросмотр ученика")}</strong></div><a className="button-link" href={`#course=${courseId}${runId ? `&run=${runId}` : ''}`}>{tr("Выйти из предпросмотра")}</a></div>
    {error && <p role="alert" className="error">{tr(error)}</p>}{data && <><div className="section-heading"><div><p className="eyebrow">{ct(data, "run")}</p><h2>{ct(data, "course")}</h2></div><button className="secondary" onClick={async () => { setCompleted([]); setAnswers({}); setCode({}); setMessage(''); setData(await apiRequest<Preview>(url)); }}>{tr("Сбросить пробное прохождение")}</button></div><p className="muted">{tr("Пробных отметок: ")}{completed.length}</p>
      {!data.steps.length && <p className="empty-state">{tr("Опубликованных шагов пока нет.")}</p>}
      <div className="preview-layout"><aside className="hub-panel preview-outline"><h3>{tr("Программа курса")}</h3>{data.steps.map(s => <button className={selected === s.id ? '' : 'secondary'} key={s.id} onClick={() => { setSelected(s.id); setMessage(''); setError('') }}><small>{ct(s, "module")} · {ct(s, "lesson")}</small>{completed.includes(s.id) ? '✓ ' : s.reason ? '🔒 ' : ''}{ct(s, "title")}</button>)}</aside>
      <div>{step && <article className="hub-panel preview-content"><p className="eyebrow">{ct(step, "lesson")}</p><h3>{ct(step, "title")}</h3>{step.reason ? <p className="deadline-note">{tr(step.reason)}</p> : <>
        {step.kind === 'text' && <RichLessonContent content={ct(step, 'content')} runId={data.run_id} />}{step.kind === 'video' && <a href={step.video_url} target="_blank" rel="noreferrer">{tr("Смотреть видео")}</a>}{step.material && <MaterialViewer material={{ ...step.material, title: ct(step.material, "title") }} />}
        {step.assignment && <><h4>{ct(step.assignment, "title")}</h4><p className="preserve-text">{ct(step.assignment, "description")}</p><label className="search-field">{tr("Пробный ответ")}<textarea rows={5} placeholder={tr("Ответ останется только в этом окне")} /></label></>}
        {step.questions?.map(q => <fieldset className="preview-question" key={q.id}><legend>{ct(q, "body")}</legend>{q.options.map((_o, i) => <label className="quiz-option" key={i}><input type="radio" name={`preview-${q.id}`} checked={answers[step.id]?.[q.id] === i} onChange={() => setAnswers(v => ({ ...v, [step.id]: { ...v[step.id], [q.id]: i } }))} />{ct(q, 'options', i)}</label>)}</fieldset>)}
        {step.problem && <><h4>{ct(step.problem, "title")}</h4><p className="preserve-text">{ct(step.problem, "statement")}</p>{step.problem.samples.map((s, i) => <div className="form-grid" key={i}><pre>{s.stdin}</pre><pre>{s.expected}</pre></div>)}<label className="search-field">{tr("Пробное решение Python")}<textarea className="code-editor" rows={12} value={code[step.id] ?? step.problem.starter_code} onChange={e => setCode(v => ({ ...v, [step.id]: e.target.value }))} /></label></>}
        {step.action_reason && <p className="deadline-note warning">{tr(step.action_reason)}</p>}
        <div className="action-row"><button disabled={busy || Boolean(step.action_reason)} onClick={() => execute()}>{busy ? tr("Проверяем…") : step.kind === 'quiz' || step.kind === 'code' ? tr("Проверить пробное решение") : step.kind === 'assignment' ? tr("Отправить пробный ответ") : tr("Отметить изученным в предпросмотре")}</button></div>
        {step.assignment && <details><summary>{tr("Сымитировать ручную проверку в предпросмотре")}</summary><label className="search-field">{tr("Пробный балл преподавателя")}<input type="number" min={0} max={step.assignment.max_score} value={manualScores[step.id] ?? step.assignment.max_score} onChange={e => setManualScores(v => ({ ...v, [step.id]: Number(e.target.value) }))} /></label><div className="action-row"><button className="secondary" disabled={busy || Boolean(step.action_reason)} onClick={() => execute(true)}>{tr("Применить пробную оценку")}</button></div></details>}
      </>}{message && <p role="status" className="success">{tr(message)}</p>}</article>}</div></div></>}
  </section>
}
