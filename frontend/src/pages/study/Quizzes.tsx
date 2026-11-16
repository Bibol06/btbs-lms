import { ct } from '../../i18n/content'
import { t as tr, countLabel } from '../../i18n/language'
import { BankPicker } from '../workspace/AuthorTools'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { apiRequest } from '../../api'
import { type Quiz, type Question, type Attempt, errorMessage, formatDate, inputDate, isoDate } from './types'
import { useNow } from './useNow'
import ConfirmAction from './ConfirmAction'
import ScheduleForm from './ScheduleForm'

export type Running = { attempt: Attempt; questions: Required<Pick<Question, 'id' | 'body' | 'options'>>[]; answers: Record<string, number>; message?: string }
const blankQuestion = (): Question => ({ body: '', options: ['', '', '', ''], correct_index: 0 })

export function QuizEditor({ courseId, initial, initialTitle = '', onSaved, onCancel }: { courseId: number; initial?: Quiz; initialTitle?: string; onSaved: (id: number, title: string) => void; onCancel: () => void }) {
  const [questions, setQuestions] = useState<Question[]>(initial?.questions ?? [blankQuestion()])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  function update(index: number, patch: Partial<Question>) {
    setQuestions(current => current.map((q, i) => i === index ? { ...q, ...patch } : q))
  }
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    setBusy(true); setError('')
    try {
      const result = await apiRequest<{ id: number }>(initial ? `/api/study/quizzes/${initial.id}/` : `/api/study/courses/${courseId}/quizzes/`, initial ? 'PATCH' : 'POST', {
        title: form.get('title'), max_attempts: Number(form.get('max_attempts')),
        time_limit_sec: Number(form.get('minutes')) * 60, opens_at: isoDate(form.get('opens_at')),
        closes_at: isoDate(form.get('closes_at')), is_published: form.has('is_published'), questions,
      })
      onSaved(initial?.id ?? result.id, String(form.get('title') || '').trim())
    } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }
  return <form className="study-form" onSubmit={save}>
    <h3>{initial ? tr("Редактирование теста") : tr("Новый тест")}</h3>
    <label>{tr("Название теста")}<input name="title" defaultValue={initial?.title ?? initialTitle} maxLength={200} required autoFocus /></label>
    <div className="form-grid">
      <label>{tr("Время (минут)")}<input type="number" name="minutes" min={1} max={240} defaultValue={(initial?.time_limit_sec ?? 900) / 60} required /></label>
      <label>{tr("Попыток")}<input type="number" name="max_attempts" min={1} max={100} defaultValue={initial?.max_attempts ?? 3} required /></label>
      <label>{tr("Открыть (местное время)")}<input type="datetime-local" name="opens_at" defaultValue={inputDate(initial?.opens_at)} /></label>
      <label>{tr("Закрыть (местное время)")}<input type="datetime-local" name="closes_at" defaultValue={inputDate(initial?.closes_at)} /></label>
    </div>
    
    <BankPicker courseId={courseId} add={q => setQuestions(v => v.length < 100 ? [...v, q] : v)} />
    {questions.map((q, index) => <fieldset key={index}>
      <legend>{tr("Вопрос ")}{index + 1}</legend>
      <label>{tr("Текст вопроса")}<textarea value={q.body} onChange={e => update(index, { body: e.target.value })} maxLength={10000} required /></label>
      {q.options.map((option, oi) => <div className="option-editor" key={oi}>
        <label className="check"><input type="radio" name={`correct-${index}`} checked={q.correct_index === oi} onChange={() => update(index, { correct_index: oi })} /> {tr(" Верный")}</label>
        <input aria-label={tr("Вопрос {0}, вариант {1}", [index + 1, oi + 1])} value={option} maxLength={1000} required onChange={e => update(index, { options: q.options.map((v, i) => i === oi ? e.target.value : v) })} />
      </div>)}
      {questions.length > 1 && <button type="button" className="danger" onClick={() => setQuestions(current => current.filter((_, i) => i !== index))}>{tr("Удалить вопрос")}</button>}
    </fieldset>)}
    <button type="button" className="secondary" disabled={questions.length >= 100} onClick={() => setQuestions(current => [...current, blankQuestion()])}>{tr("+ Вопрос")}</button>
    <label className="check"><input type="checkbox" name="is_published" defaultChecked={initial?.is_published} /> {tr(" Опубликовать тест")}</label>
    {error && <p role="alert" className="error">{tr(error)}</p>}
    <div className="action-row"><button disabled={busy}>{tr("Сохранить тест")}</button><button type="button" disabled={busy} className="secondary" onClick={onCancel}>{tr("Отмена")}</button></div>
  </form>
}

export function QuizPlayer({ running, title, onFinished, onClose, embedded = false }: { running: Running; title: string; onFinished: (message: string) => void; onClose: () => void; embedded?: boolean }) {
  const [confirming, setConfirming] = useState(false)
  const [questionIndex, setQuestionIndex] = useState(0)
  const [answers, setAnswers] = useState(running.answers)
  const now = useNow()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [clockOffset] = useState(() => running.attempt.server_now ? Date.parse(running.attempt.server_now) - Date.now() : 0)
  const [saveState, setSaveState] = useState('saved')
  const onFinishedRef = useRef(onFinished)
  useEffect(() => { onFinishedRef.current = onFinished }, [onFinished])
  const remaining = Math.max(0, Math.ceil((new Date(running.attempt.deadline_at).getTime() - now - clockOffset) / 1000))
  useEffect(() => {
    let alive = true
    let timer: number
    let failures = 0
    async function finishSaved() {
      try {
        const result = await apiRequest<{ attempt: Attempt; message: string }>(`/api/study/attempts/${running.attempt.id}/`, 'POST', { finish_saved: true })
        if (!alive) return
        if (result.attempt.status === 'active') timer = window.setTimeout(finishSaved, 1000)
        else onFinishedRef.current(tr("{0} Результат: {1}/{2}", [result.message, result.attempt.score, result.attempt.max_score]))
      } catch (err) {
        if (!alive) return
        failures += 1
        if (failures < 3) timer = window.setTimeout(finishSaved, 2000)
        else setError(tr("{0}. Сохранённые ответы остаются на сервере. Вернитесь к результатам после восстановления связи.", [errorMessage(err)]))
      }
    }
    timer = window.setTimeout(finishSaved, Math.max(0, Date.parse(running.attempt.deadline_at) - Date.now() - clockOffset) + 250)
    return () => { alive = false; window.clearTimeout(timer) }
  }, [running.attempt.id, running.attempt.deadline_at, clockOffset])
  async function choose(id: number, option: number) {
    const previous = answers
    const next = { ...answers, [id]: option }
    setAnswers(next); setSaveState('saving'); setBusy(true); setError('')
    try {
      const result = await apiRequest<{ attempt: Attempt; message: string }>(`/api/study/attempts/${running.attempt.id}/`, 'PATCH', { answers: next })
      if (result.attempt.status !== 'active') onFinished(result.message)
      else { setAnswers(next); setSaveState('saved') }
    } catch (err) { setAnswers(previous); setSaveState('error'); setError(tr("Ответ не сохранён: {0}. После восстановления связи выберите вариант ещё раз.", [errorMessage(err)])) } finally { setBusy(false) }
  }
  async function finish(event: FormEvent) {
    event.preventDefault()
    const completeSingleQuestion = embedded && running.questions.length === 1 && answers[String(running.questions[0].id)] !== undefined
    if (!confirming && !completeSingleQuestion) { setConfirming(true); return }
    setBusy(true); setError('')
    try {
      const result = await apiRequest<{ attempt: Attempt; message: string }>(`/api/study/attempts/${running.attempt.id}/`, 'POST', { answers })
      onFinished(tr("{0}. Результат: {1}/{2}", [result.message, result.attempt.score, result.attempt.max_score]))
    } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }
  return <form className="study-form quiz-player" onSubmit={finish}>
    <div className="section-heading">{embedded ? <strong>{tr("Выберите ответ и отправьте на проверку")}</strong> : <h3>{ct(title)}</h3>}<strong className="timer" role="timer" aria-label={tr("Оставшееся время")}>{Math.floor(remaining / 60)}:{String(remaining % 60).padStart(2, '0')}</strong></div>
    
    <p className={saveState === 'error' ? 'error' : 'muted'} role="status">{saveState === 'saving' ? tr("Сохраняем ответ…") : saveState === 'saved' ? tr("Выбранные ответы сохранены на сервере.") : tr("Последний выбор не удалось сохранить.")}</p>
    {embedded && running.questions.length > 1 && <div className="inline-question-navigation" role="group" aria-label={tr('Вопросы задания')}>{running.questions.map((question, index) => <button type="button" key={question.id} className={index === questionIndex ? 'current' : 'secondary'} aria-current={index === questionIndex ? 'step' : undefined} aria-label={`${tr('Вопрос ')}${index + 1}`} disabled={busy} onClick={() => setQuestionIndex(index)}>{answers[String(question.id)] !== undefined ? '✓ ' : ''}{index + 1}</button>)}</div>}
    {(embedded ? [running.questions[questionIndex]] : running.questions).map((q, offset) => <fieldset key={q.id} disabled={busy || remaining === 0}>
      <legend>{(embedded ? questionIndex : offset) + 1}. {ct(q, "body")}</legend>
      {q.options.map((_v, i) => <label className="quiz-option" key={i}>
        <input type="radio" name={`question-${q.id}`} checked={answers[String(q.id)] === i} onChange={() => choose(q.id, i)} />{ct(q, 'options', i)}
      </label>)}
    </fieldset>)}
    {embedded && running.questions.length > 1 && <div className="inline-question-pager"><button type="button" className="secondary" disabled={busy || questionIndex === 0} onClick={() => setQuestionIndex(value => value - 1)}>{tr('← Предыдущий вопрос')}</button><span>{tr('Выбрано ответов: {0}/{1}', [running.questions.filter(question => answers[String(question.id)] !== undefined).length, running.questions.length])}</span><button type="button" className="secondary" disabled={busy || questionIndex === running.questions.length - 1} onClick={() => setQuestionIndex(value => value + 1)}>{tr('Следующий вопрос →')}</button></div>}
    {error && <p role="alert" className="error">{tr(error)}</p>}
    {confirming && <p role="status">{tr("Завершить тест и отправить ответы на проверку? Ответы больше нельзя будет изменить.")}</p>}
    <div className="action-row"><button disabled={busy || remaining === 0}>{confirming ? tr("Подтвердить отправку") : embedded ? tr("Отправить на проверку") : tr("Завершить тест")}</button>{confirming && <button type="button" className="secondary" onClick={() => setConfirming(false)}>{tr("Отмена")}</button>}<button type="button" className="secondary" onClick={onClose} disabled={busy}>{embedded ? tr("Свернуть задание") : tr("Вернуться к списку")}</button></div>
  </form>
}

export default function Quizzes({ courseId, runId, quizzes, manage, canEdit, refresh }: { courseId: number; runId: number; quizzes: Quiz[]; manage: boolean; canEdit: boolean; refresh: () => void }) {
  const now = useNow()
  const [editor, setEditor] = useState<Quiz | 'new' | null>(null)
  const [active, setActive] = useState<{ quiz: Quiz; running: Running } | null>(null)
  const [busy, setBusy] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  async function start(q: Quiz) {
    setBusy(q.id); setError(''); setMessage('')
    try {
      const running = await apiRequest<Running>(`/api/study/quizzes/${q.id}/start/?run_id=${runId}`, 'POST', {})
      if (running.attempt.status === 'active') setActive({ quiz: q, running })
      else { setMessage(tr("{0}. Результат: {1}/{2}", [running.message || 'Тест завершён', running.attempt.score, running.attempt.max_score])); refresh() }
    }
    catch (err) { setError(errorMessage(err)); refresh() } finally { setBusy(null) }
  }
  async function change(q: Quiz, remove = false) {
    setBusy(q.id); setError('')
    try {
      await apiRequest(`/api/study/quizzes/${q.id}/`, remove ? 'DELETE' : 'PATCH', remove ? undefined : { is_published: !q.is_published })
      refresh()
    } catch (err) { setError(errorMessage(err)) } finally { setBusy(null) }
  }
  function finished(msg: string) { setActive(null); setMessage(msg); refresh() }
  if (active) return <QuizPlayer running={active.running} title={ct(active.quiz, "title")} onFinished={finished} onClose={() => { setActive(null); refresh() }} />
  return <section className="study-section">
    <div className="section-heading"><h2>{tr("Тестирование")}</h2>{canEdit && <button onClick={() => setEditor('new')}>{tr("+ Новый тест")}</button>}</div>
    {error && <p role="alert" className="error">{tr(error)}</p>}{message && <p role="status" className="success">{tr(message)}</p>}
    {editor && <QuizEditor key={editor === 'new' ? 'new' : editor.id} courseId={courseId} initial={editor === 'new' ? undefined : editor} onSaved={() => { setEditor(null); refresh() }} onCancel={() => setEditor(null)} />}
    {!quizzes.length && <p className="empty-state">{tr("Тестов пока нет.")}</p>}
    {quizzes.map(q => {
      const open = (!q.opens_at || now >= new Date(q.opens_at).getTime()) && (!q.closes_at || now < new Date(q.closes_at).getTime())
      const resumable = q.attempts.some(a => a.status === 'active')
      return <article className="study-card" key={q.id}>
        <div className="section-heading"><h3>{ct(q, "title")}</h3>{manage && <span className="badge">{q.is_published ? tr("Опубликован") : tr("Черновик")}</span>}</div>
        <p>{countLabel(q.questions_count, "question")} · {q.time_limit_sec / 60} {tr(" мин. · Попыток: ")}{q.max_attempts}</p>
        <p className="muted">{tr("Открытие: ")}{formatDate(q.opens_at)} {tr(" · Закрытие: ")}{formatDate(q.closes_at)}</p>
        {manage ? <>
          <div className="action-row">
            {canEdit && !q.has_attempts && <button className="secondary" onClick={() => setEditor(q)}>{tr("Редактировать тест")}</button>}
            {canEdit && <button className="secondary" disabled={busy === q.id} onClick={() => change(q)}>{q.is_published ? tr("Снять с публикации") : tr("Опубликовать")}</button>}
            {canEdit && !q.has_attempts && <ConfirmAction label={tr("Удалить тест")} question={tr("Удалить тест «{0}»?", [q.title])} disabled={busy === q.id} onConfirm={() => change(q, true)} />}
          </div>
          <ScheduleForm courseId={courseId} runId={runId} kind="quiz" activity={q} onSaved={refresh} />
          <details><summary>{tr("Вопросы и правильные ответы")}</summary>{q.questions?.map((v, i) => <p key={v.id}>{i + 1}. {ct(v, "body")} — <strong>{ct(v, 'options', v.correct_index)}</strong></p>)}</details>
        </> : <>
          {q.attempts.map(a => <p key={a.id}>{tr("Попытка ")}{a.attempt_no}: {a.status === 'active' ? tr("Идёт") : a.status === 'expired' ? tr("Время истекло · {0}/{1}", [a.score, a.max_score]) : tr("{0}/{1} баллов{2}", [a.score, a.max_score, a.auto_submitted ? tr(' · Проверено автоматически по таймеру') : ''])}</p>)}
          <button disabled={busy === q.id || !open || (!resumable && q.attempts.length >= q.max_attempts)} onClick={() => start(q)}>{resumable ? tr("Продолжить тест") : tr("Начать тест")}</button>
          {!open && <p className="muted">{tr("Тест недоступен по расписанию.")}</p>}
        </>}
      </article>
    })}
  </section>
}
