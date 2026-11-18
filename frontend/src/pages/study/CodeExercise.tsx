import { ct } from '../../i18n/content'
import { localizedLabels, t as tr } from '../../i18n/language'
import { lazy, Suspense, useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent as ReactKeyboardEvent, type PointerEvent as ReactPointerEvent } from 'react'
import { apiRequest } from '../../api'
import { errorMessage } from './types'
import ConfirmAction from './ConfirmAction'
import PracticeFields from './PracticeFields'
import { practiceValues } from './practiceValues'
import './CodeExercise.css'

const CodeEditor = lazy(() => import('../../components/CodeEditor'))

type Result = { id?: number; run_token?: string; status: string; stdout?: string; stderr?: string; passed?: number; total?: number; details?: { sample: boolean; status: string; stdout?: string; stderr?: string }[] }
type Slide = { id: number; title: string; lesson: string; url: string }
type ProblemData = { problem: { id: number; title: string; statement: string; starter_code: string; max_attempts: number; context: string; instructions: string[]; hints: string[]; samples: { stdin: string; expected: string }[] }; slides: Slide[]; submissions: { id: number; status: string; passed: number; total: number }[]; attempts_used: number; available: boolean; can_manage: boolean; can_submit: boolean; draft_key: string; editor: { can_edit: boolean; test_cases: { stdin: string; expected: string; is_sample: boolean }[] } | null }
type Tab = 'output' | 'input' | 'slides'
const statuses: Record<string, string> = localizedLabels({ ok: 'Выполнено', accepted: 'Принято', rejected: 'Есть ошибки', wrong_answer: 'Неверный ответ', runtime_error: 'Ошибка выполнения', limit_exceeded: 'Превышен лимит вычислений или памяти', output_limit: 'Слишком большой вывод', time_limit: 'Превышено время', running: 'Проверяется', service_error: 'Ошибка сервиса' })
const SPLIT_KEY = 'lms-practice-split'
const THEME_KEY = 'lms-editor-theme'

function ProblemEditor({ data, runId, saved }: { data: ProblemData; runId: number; saved: () => void }) {
  const [cases, setCases] = useState(data.editor?.test_cases ?? [])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget); setBusy(true)
    try { await apiRequest(`/api/code/problems/${data.problem.id}/?run_id=${runId}`, 'PATCH', { title: form.get('title'), statement: form.get('statement'), starter_code: form.get('starter_code'), max_attempts: Number(form.get('max_attempts')), test_cases: cases, ...practiceValues(form) }); saved() }
    catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }
  return <details className="practice-teacher-editor"><summary>{tr("Редактировать условие и проверочные тесты")}</summary><form className="study-form" onSubmit={save}>
    <label>{tr("Название задачи")}<input name="title" required maxLength={200} defaultValue={data.problem.title} /></label><label>{tr("Условие")}<textarea name="statement" required rows={5} maxLength={30000} defaultValue={data.problem.statement} /></label>
    <PracticeFields initial={data.problem} />
    <label>{tr("Начальный код")}<textarea name="starter_code" className="code-editor" defaultValue={data.problem.starter_code} maxLength={20000} /></label><label>{tr("Лимит отправок")}<input name="max_attempts" type="number" min={1} max={100} required defaultValue={data.problem.max_attempts} /></label>
    {cases.map((c, index) => <fieldset key={index}><legend>{tr("Тест ")}{index+1}</legend><label>{tr("Входные данные")}<textarea value={c.stdin} maxLength={10000} onChange={e => setCases(current => current.map((v, i) => i === index ? { ...v, stdin: e.target.value } : v))} /></label><label>{tr("Ожидаемый вывод")}<textarea value={c.expected} maxLength={10000} onChange={e => setCases(current => current.map((v, i) => i === index ? { ...v, expected: e.target.value } : v))} /></label><label className="check"><input type="checkbox" checked={c.is_sample} onChange={e => setCases(current => current.map((v, i) => i === index ? { ...v, is_sample: e.target.checked } : v))} /> {tr(" Показывать пример студенту")}</label>{cases.length > 1 && <button type="button" className="danger" onClick={() => setCases(current => current.filter((_, i) => i !== index))}>{tr("Удалить пример")}</button>}</fieldset>)}
    <button type="button" className="secondary" disabled={cases.length >= 20} onClick={() => setCases(current => [...current, { stdin: '', expected: '', is_sample: false }])}>{tr("+ Проверочный тест")}</button>{error && <p className="error" role="alert">{tr(error)}</p>}<button disabled={busy}>{tr("Сохранить задачу Python")}</button>
  </form></details>
}

function readTheme(): 'dark' | 'light' {
  try { return localStorage.getItem(THEME_KEY) === 'light' ? 'light' : 'dark' } catch { return 'dark' }
}

function readSplit() {
  try { const value = Number(localStorage.getItem(SPLIT_KEY)); return value >= 25 && value <= 80 ? value : 60 } catch { return 60 }
}

export default function CodeExercise({ problemId, runId, onCompleted, variant = 'inline' }: { problemId: number; runId: number; onCompleted: () => void; variant?: 'inline' | 'player' }) {
  const [data, setData] = useState<ProblemData | null>(null)
  const [code, setCode] = useState('')
  const [stdin, setStdin] = useState('')
  const [result, setResult] = useState<Result | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  const [tab, setTab] = useState<Tab>('output')
  const [slide, setSlide] = useState(0)
  const [hintsShown, setHintsShown] = useState(0)
  const [taskHidden, setTaskHidden] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const [split, setSplit] = useState(readSplit)
  const [theme, setTheme] = useState(readTheme)
  const work = useRef<HTMLDivElement>(null)
  useEffect(() => {
    let alive = true
    apiRequest<ProblemData>(`/api/code/problems/${problemId}/?run_id=${runId}`).then(value => {
      if (alive) { setData(value); setCode(current => current || sessionStorage.getItem(value.draft_key) || value.problem.starter_code) }
    }).catch(err => { if (alive) setError(errorMessage(err)) })
    return () => { alive = false }
  }, [problemId, runId, revision])
  useEffect(() => {
    if (!expanded) return
    const close = (event: KeyboardEvent) => { if (event.key === 'Escape') setExpanded(false) }
    window.addEventListener('keydown', close)
    document.body.classList.add('practice-open')
    return () => { window.removeEventListener('keydown', close); document.body.classList.remove('practice-open') }
  }, [expanded])
  const changeCode = useCallback((next: string) => {
    setCode(next)
    if (data) { try { sessionStorage.setItem(data.draft_key, next) } catch { /* private mode: draft is not kept */ } }
  }, [data])
  async function execute(submit: boolean) {
    setBusy(true); setError(''); setResult(null); setTab('output')
    try {
      let value = await apiRequest<Result>(`/api/code/problems/${problemId}/execute/?run_id=${runId}`, 'POST', { code, stdin, submit })
      // The server queues the check (status "running"); poll until the verdict is ready.
      const poll = value.run_token ? `/api/code/runs/${value.run_token}/` : `/api/code/submissions/${value.id}/`
      for (let wait = 0; value.status === 'running' && wait < 150; wait++) {
        setResult(value)
        await new Promise(resolve => window.setTimeout(resolve, wait < 10 ? 500 : 1000))
        value = await apiRequest<Result>(poll)
      }
      if (value.status === 'running') throw new Error(tr("Проверка заняла слишком много времени. Обновите страницу позже."))
      setResult(value)
      if (submit) { setRevision(v => v + 1); if (value.status === 'accepted') onCompleted() }
    } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }
  const run = useCallback(() => { if (!busy && data?.available) void execute(false) }, [busy, data, code, stdin]) // eslint-disable-line react-hooks/exhaustive-deps
  function toggleTheme() {
    const next = theme === 'dark' ? 'light' : 'dark'
    setTheme(next)
    try { localStorage.setItem(THEME_KEY, next) } catch { /* not kept */ }
  }
  function resize(event: ReactPointerEvent<HTMLDivElement>) {
    const box = work.current?.getBoundingClientRect()
    if (!box) return
    event.currentTarget.setPointerCapture(event.pointerId)
    const move = (e: PointerEvent) => setSplit(Math.min(80, Math.max(25, ((e.clientY - box.top) / box.height) * 100)))
    const stop = () => {
      window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', stop)
      setSplit(value => { try { localStorage.setItem(SPLIT_KEY, String(Math.round(value))) } catch { /* not kept */ } return value })
    }
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', stop)
  }
  function resizeByKey(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
      event.preventDefault()
      setSplit(value => Math.min(80, Math.max(25, value + (event.key === 'ArrowUp' ? -5 : 5))))
    }
  }
  if (!data) return <p>{error || tr("Загрузка задачи Python…")}</p>
  const problem = data.problem
  const outOfAttempts = data.attempts_used >= problem.max_attempts
  const current = data.slides[Math.min(slide, data.slides.length - 1)]
  return <section className={`practice practice-${variant} practice-${theme} ${expanded ? 'practice-expanded' : ''} ${taskHidden ? 'practice-task-hidden' : ''}`} aria-label={tr("Практика: {0}", [ct(problem, "title")])}>
    <header className="practice-toolbar">
      <strong>{ct(problem, "title")}</strong>
      <div className="practice-toolbar-actions">
        <button type="button" className="secondary" aria-expanded={!taskHidden} onClick={() => setTaskHidden(v => !v)}>{taskHidden ? tr("Показать задание") : tr("Скрыть задание")}</button>
        {variant === 'inline' && <button type="button" className="secondary" onClick={() => setExpanded(v => !v)}>{expanded ? tr("Свернуть (Esc)") : tr("Во весь экран")}</button>}
      </div>
    </header>
    <div className="practice-body">
      <aside className="practice-task" hidden={taskHidden}>
        <h4>{tr("Задание")}</h4>
        <p className="preserve-text">{ct(problem, "statement")}</p>
        {problem.context && <p className="practice-context preserve-text">{problem.context}</p>}
        {problem.instructions.length > 0 && <><h4>{tr("Инструкции")}</h4><ol className="practice-instructions">{problem.instructions.map((item, i) => <li key={i}>{item}</li>)}</ol></>}
        {problem.samples.map((s, i) => <div className="practice-sample" key={i}><div><strong>{tr("Пример ввода")}</strong><pre>{s.stdin || tr("(пусто)")}</pre></div><div><strong>{tr("Ожидаемый вывод")}</strong><pre>{s.expected}</pre></div></div>)}
        {problem.hints.length > 0 && <div className="practice-hints">
          {problem.hints.slice(0, hintsShown).map((hint, i) => <p key={i} className="practice-hint preserve-text"><strong>{tr("Подсказка {0}", [i + 1])}</strong><br />{hint}</p>)}
          {hintsShown < problem.hints.length && <button type="button" className="secondary" onClick={() => setHintsShown(v => v + 1)}>💡 {hintsShown ? tr("Ещё подсказка") : tr("Подсказка")} ({problem.hints.length - hintsShown})</button>}
        </div>}
        {!data.can_manage && <p className="muted">{tr("Отправлено ")}{data.attempts_used}/{problem.max_attempts} {tr(" решений.")}</p>}
        {!data.can_manage && data.submissions.length > 0 && <details><summary>{tr("История отправок")}</summary>{data.submissions.map(s => <p key={s.id}>#{s.id}: {statuses[s.status] ?? s.status} · {s.passed}/{s.total}</p>)}</details>}
        {data.editor && (data.editor.can_edit ? <ProblemEditor key={revision} data={data} runId={runId} saved={() => setRevision(v => v + 1)} /> : <p className="muted">{tr("Редактирование закрыто: уже есть отправки.")}</p>)}
      </aside>
      <div className="practice-work" ref={work}>
        <div className="practice-editor" style={{ flexBasis: `${split}%` }}>
          <div className="practice-editor-bar">
            <span className="practice-file">solution.py</span>
            <button type="button" className="practice-theme-toggle" aria-pressed={theme === 'light'} onClick={toggleTheme}>{theme === 'dark' ? `☀ ${tr("Светлая тема")}` : `☾ ${tr("Тёмная тема")}`}</button>
            <div className="practice-editor-actions">
              <ConfirmAction label={tr("Сбросить код")} question={tr("Вернуть начальный код? Ваш текущий код пропадёт.")} onConfirm={() => changeCode(problem.starter_code)} disabled={busy} />
              <button type="button" className="secondary" title="Ctrl+Enter" disabled={busy || !data.available} onClick={() => execute(false)}>▶ {tr("Запустить")}</button>
              {!data.can_manage && data.can_submit && <button type="button" disabled={busy || !data.available || outOfAttempts} onClick={() => execute(true)}>{busy ? tr("Проверяем…") : tr("Отправить на проверку")}</button>}
            </div>
          </div>
          <Suspense fallback={<textarea className="code-editor practice-fallback" spellCheck={false} value={code} onChange={e => changeCode(e.target.value)} aria-label={tr("Решение на Python 3.12")} />}>
            <CodeEditor value={code} onChange={changeCode} onRun={run} label={tr("Решение на Python 3.12")} theme={theme} />
          </Suspense>
        </div>
        <div className="practice-splitter" role="separator" aria-orientation="horizontal" aria-valuenow={Math.round(split)} aria-valuemin={25} aria-valuemax={80} aria-label={tr("Граница редактора и панели вывода")} tabIndex={0} onPointerDown={resize} onKeyDown={resizeByKey} />
        <div className="practice-panel">
          <div className="practice-tabs" role="tablist">
            <button type="button" role="tab" aria-selected={tab === 'output'} onClick={() => setTab('output')}>{tr("Вывод")}</button>
            <button type="button" role="tab" aria-selected={tab === 'input'} onClick={() => setTab('input')}>{tr("Ввод для input()")}{stdin ? ' •' : ''}</button>
            <button type="button" role="tab" aria-selected={tab === 'slides'} onClick={() => setTab('slides')}>{tr("Слайды")}{data.slides.length ? ` (${data.slides.length})` : ''}</button>
          </div>
          <div className="practice-tab-body" role="tabpanel">
            {tab === 'output' && <div className="practice-output" role="status" aria-live="polite">
              {!data.available && <p className="error">{tr("Изолированная среда временно недоступна.")}</p>}
              {error && <p className="error" role="alert">{tr(error)}</p>}
              {!result && !error && <p className="muted">{busy ? tr("Проверяется") + '…' : tr("Нажмите «Запустить» (Ctrl+Enter), чтобы увидеть вывод программы.")}</p>}
              {result && <><p className={`practice-verdict practice-verdict-${result.status}`}>{statuses[result.status] ?? result.status}{result.total !== undefined && result.status !== 'running' ? tr(" · {0}/{1} тестов", [result.passed, result.total]) : ''}</p>
                {result.stdout !== undefined && <pre>{result.stdout || tr("(нет вывода)")}</pre>}
                {result.stderr && <pre className="error">{result.stderr}</pre>}
                {result.details?.map((r, i) => <p key={i}>{tr("Тест ")}{i+1}{r.sample ? tr(" (пример)") : tr(" (скрытый)")}: {statuses[r.status] ?? r.status}</p>)}</>}
            </div>}
            {tab === 'input' && <label className="practice-input">{tr("Эти строки получит input() при запуске")}<textarea placeholder={'2\n3'} value={stdin} onChange={e => setStdin(e.target.value)} maxLength={10000} /></label>}
            {tab === 'slides' && (current ? <div className="practice-slides">
              {data.slides.length > 1 && <select aria-label={tr("Слайды урока")} value={slide} onChange={e => setSlide(Number(e.target.value))}>{data.slides.map((s, i) => <option key={s.id} value={i}>{s.lesson} — {s.title}</option>)}</select>}
              <iframe key={current.url} src={current.url} title={current.title} referrerPolicy="no-referrer" />
            </div> : <p className="muted">{tr("Преподаватель пока не прикрепил PDF-слайды к этому модулю.")}</p>)}
          </div>
        </div>
      </div>
    </div>
  </section>
}
