import { ct } from '../../i18n/content'
import { localizedLabels, t as tr } from '../../i18n/language'
import { useEffect, useState, type FormEvent } from 'react'
import { apiRequest } from '../../api'
import { errorMessage } from './types'

type Result = { status: string; stdout?: string; stderr?: string; passed?: number; total?: number; details?: { sample: boolean; status: string; stdout?: string; stderr?: string }[] }
type ProblemData = { problem: { id: number; title: string; statement: string; starter_code: string; max_attempts: number; samples: { stdin: string; expected: string }[] }; submissions: { id: number; status: string; passed: number; total: number }[]; attempts_used: number; available: boolean; can_manage: boolean; can_submit: boolean; draft_key: string; editor: { can_edit: boolean; test_cases: { stdin: string; expected: string; is_sample: boolean }[] } | null }
const statuses: Record<string, string> = localizedLabels({ ok: 'Выполнено', accepted: 'Принято', rejected: 'Есть ошибки', wrong_answer: 'Неверный ответ', runtime_error: 'Ошибка выполнения', limit_exceeded: 'Превышен лимит вычислений или памяти', output_limit: 'Слишком большой вывод', time_limit: 'Превышено время', running: 'Проверяется', service_error: 'Ошибка сервиса' })

function ProblemEditor({ data, runId, saved }: { data: ProblemData; runId: number; saved: () => void }) {
  const [cases, setCases] = useState(data.editor?.test_cases ?? [])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget); setBusy(true)
    try { await apiRequest(`/api/code/problems/${data.problem.id}/?run_id=${runId}`, 'PATCH', { title: form.get('title'), statement: form.get('statement'), starter_code: form.get('starter_code'), max_attempts: Number(form.get('max_attempts')), test_cases: cases }); saved() }
    catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }
  return <details><summary>{tr("Редактировать условие и проверочные тесты")}</summary><form className="study-form" onSubmit={save}>
    <label>{tr("Название задачи")}<input name="title" required maxLength={200} defaultValue={data.problem.title} /></label><label>{tr("Условие")}<textarea name="statement" required rows={5} maxLength={30000} defaultValue={data.problem.statement} /></label><label>{tr("Начальный код")}<textarea name="starter_code" className="code-editor" defaultValue={data.problem.starter_code} maxLength={20000} /></label><label>{tr("Лимит отправок")}<input name="max_attempts" type="number" min={1} max={100} required defaultValue={data.problem.max_attempts} /></label>
    {cases.map((c, index) => <fieldset key={index}><legend>{tr("Тест ")}{index+1}</legend><label>{tr("Входные данные")}<textarea value={c.stdin} maxLength={10000} onChange={e => setCases(current => current.map((v, i) => i === index ? { ...v, stdin: e.target.value } : v))} /></label><label>{tr("Ожидаемый вывод")}<textarea value={c.expected} maxLength={10000} onChange={e => setCases(current => current.map((v, i) => i === index ? { ...v, expected: e.target.value } : v))} /></label><label className="check"><input type="checkbox" checked={c.is_sample} onChange={e => setCases(current => current.map((v, i) => i === index ? { ...v, is_sample: e.target.checked } : v))} /> {tr(" Показывать пример студенту")}</label>{cases.length > 1 && <button type="button" className="danger" onClick={() => setCases(current => current.filter((_, i) => i !== index))}>{tr("Удалить пример")}</button>}</fieldset>)}
    <button type="button" className="secondary" disabled={cases.length >= 20} onClick={() => setCases(current => [...current, { stdin: '', expected: '', is_sample: false }])}>{tr("+ Проверочный тест")}</button>{error && <p className="error" role="alert">{tr(error)}</p>}<button disabled={busy}>{tr("Сохранить задачу Python")}</button>
  </form></details>
}

export default function CodeExercise({ problemId, runId, onCompleted }: { problemId: number; runId: number; onCompleted: () => void }) {
  const [data, setData] = useState<ProblemData | null>(null)
  const [code, setCode] = useState('')
  const [stdin, setStdin] = useState('')
  const [result, setResult] = useState<Result | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    let alive = true
    apiRequest<ProblemData>(`/api/code/problems/${problemId}/?run_id=${runId}`).then(value => {
      if (alive) { setData(value); setCode(current => current || sessionStorage.getItem(value.draft_key) || value.problem.starter_code) }
    }).catch(err => { if (alive) setError(errorMessage(err)) })
    return () => { alive = false }
  }, [problemId, runId, revision])
  async function execute(submit: boolean) {
    setBusy(true); setError(''); setResult(null)
    try {
      const value = await apiRequest<Result>(`/api/code/problems/${problemId}/execute/?run_id=${runId}`, 'POST', { code, stdin, submit })
      setResult(value)
      if (submit) { setRevision(v => v + 1); if (value.status === 'accepted') onCompleted() }
    } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }
  if (!data) return <p>{error || tr("Загрузка задачи Python…")}</p>
  return <section className="study-section"><h3>{ct(data.problem, "title")}</h3><p className="preserve-text">{ct(data.problem, "statement")}</p>
    {data.editor && (data.editor.can_edit ? <ProblemEditor key={revision} data={data} runId={runId} saved={() => setRevision(v => v + 1)} /> : <p className="muted">{tr("Редактирование закрыто: уже есть отправки.")}</p>)}
    {data.problem.samples.map((s, i) => <div className="form-grid" key={i}><div><strong>{tr("Пример ввода")}</strong><pre>{s.stdin}</pre></div><div><strong>{tr("Ожидаемый вывод")}</strong><pre>{s.expected}</pre></div></div>)}
    <details open={!data.can_manage}><summary>{data.can_manage ? tr("Пробный запуск преподавателя") : tr("Моё решение на Python")}</summary><div className="study-form"><label>{tr("Решение на Python 3.12")}<textarea className="code-editor" spellCheck={false} rows={14} value={code} maxLength={20000} onKeyDown={e => {
      if (e.key === 'Tab' && !e.shiftKey) {
        e.preventDefault(); const element = e.currentTarget; const start = element.selectionStart
        const next = code.slice(0, start) + '    ' + code.slice(element.selectionEnd)
        setCode(next); sessionStorage.setItem(data.draft_key, next)
        window.requestAnimationFrame(() => element.setSelectionRange(start+4, start+4))
      }
    }} onChange={e => { setCode(e.target.value); sessionStorage.setItem(data.draft_key, e.target.value) }} /></label>
      <label>{tr("Входные данные для input()")}<textarea placeholder={'2\n3'} rows={3} value={stdin} onChange={e => setStdin(e.target.value)} maxLength={10000} /></label>
      {!data.can_manage && <p className="muted">{tr("Отправлено ")}{data.attempts_used}/{data.problem.max_attempts} {tr(" решений.")}</p>}
      {!data.available && <p className="error">{tr("Изолированная среда временно недоступна.")}</p>}
      <div className="action-row"><button className="secondary" disabled={busy || !data.available} onClick={() => execute(false)}>{tr("Запустить со своим вводом")}</button>{!data.can_manage && data.can_submit && <button disabled={busy || !data.available || data.attempts_used >= data.problem.max_attempts} onClick={() => execute(true)}>{busy ? tr("Проверяем…") : tr("Отправить на проверку")}</button>}</div>
    </div></details>
    {error && <p className="error" role="alert">{tr(error)}</p>}
    {result && <div className="study-card" role="status"><h4>{statuses[result.status] ?? result.status}{result.total !== undefined ? tr(" · {0}/{1} тестов", [result.passed, result.total]) : ''}</h4>{result.stdout !== undefined && <pre>{result.stdout || tr("(нет вывода)")}</pre>}{result.stderr && <pre className="error">{result.stderr}</pre>}{result.details?.map((r, i) => <p key={i}>{tr("Тест ")}{i+1}{r.sample ? tr(" (пример)") : tr(" (скрытый)")}: {statuses[r.status] ?? r.status}</p>)}</div>}
    {!data.can_manage && <details><summary>{tr("История отправок")}</summary>{data.submissions.map(s => <p key={s.id}>#{s.id}: {statuses[s.status] ?? s.status} · {s.passed}/{s.total}</p>)}</details>}
  </section>
}
