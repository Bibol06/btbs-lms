import { useEffect, useRef, useState } from 'react'
import { apiRequest } from '../../api'
import { ct } from '../../i18n/content'
import { countLabel, t as tr } from '../../i18n/language'
import { QuizPlayer, type Running } from './Quizzes'
import { errorMessage, formatDate, type Quiz, type StudyData } from './types'
import { useNow } from './useNow'
import './InlineStepQuiz.css'

type Props = { courseId: number; runId: number; quizId: number; onCompleted: () => void }

/** A viewing request never starts a graded attempt. Starting/resuming is explicit. */
export default function InlineStepQuiz(props: Props) {
  return <InlineQuizSession key={`${props.courseId}:${props.runId}:${props.quizId}`} {...props} />
}

function InlineQuizSession({ courseId, runId, quizId, onCompleted }: Props) {
  const [data, setData] = useState<StudyData | null>(null)
  const [running, setRunning] = useState<Running | null>(null)
  const [revision, setRevision] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [loadError, setLoadError] = useState('')
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(true)
  const now = useNow()
  const alive = useRef(true)
  const completed = useRef(onCompleted)
  useEffect(() => { completed.current = onCompleted }, [onCompleted])
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])
  useEffect(() => {
    let current = true
    apiRequest<StudyData>(`/api/study/courses/${courseId}/?run_id=${runId}`)
      .then(value => { if (current) { setData(value); setLoadError('') } })
      .catch(cause => { if (current) setLoadError(errorMessage(cause)) })
      .finally(() => { if (current) setLoading(false) })
    return () => { current = false }
  }, [courseId, runId, revision])

  function refresh() { setLoading(true); setRevision(value => value + 1) }
  function finished(text: string) {
    if (!alive.current) return
    setRunning(null); setMessage(text); refresh(); completed.current()
  }
  async function start() {
    setBusy(true); setError(''); setMessage('')
    try {
      const result = await apiRequest<Running>(`/api/study/quizzes/${quizId}/start/?run_id=${runId}`, 'POST', {})
      if (!alive.current) return
      if (result.attempt.status === 'active') setRunning(result)
      else finished(tr('{0}. Результат: {1}/{2}', [result.message || tr('Тест завершён'), result.attempt.score, result.attempt.max_score]))
    } catch (cause) { if (alive.current) { setError(errorMessage(cause)); refresh() } }
    finally { if (alive.current) setBusy(false) }
  }

  const quiz = data?.quizzes.find(value => value.id === quizId)
  return <section className="inline-step-quiz" aria-label={tr('Задание в уроке')}>
    {(error || loadError) && <p className="error" role="alert">{tr(error || loadError)}</p>}
    {loadError && data && <button type="button" className="secondary" disabled={loading} onClick={refresh}>{tr('Повторить')}</button>}
    {message && <p className="inline-quiz-result" role="status">{tr(message)}</p>}
    {!data ? loading ? <p role="status">{tr('Загрузка задания…')}</p> : <button type="button" className="secondary" onClick={refresh}>{tr('Повторить')}</button> : !quiz ? <div className="inline-quiz-unavailable"><p>{tr('Задание пока недоступно.')}</p><button type="button" className="secondary" disabled={loading} onClick={refresh}>{tr('Обновить')}</button></div> : <>
      <div className="inline-quiz-heading"><div><span className="inline-quiz-eyebrow">{tr('Проверка знаний')}</span><h3>{ct(quiz, 'title')}</h3></div><span className="inline-quiz-count">{countLabel(quiz.questions_count, 'question')}</span></div>
      {data?.can_manage ? <TeacherPreview quiz={quiz} canEdit={data.can_edit} courseId={courseId} runId={runId} /> : running ? <QuizPlayer key={running.attempt.id} running={running} title={ct(quiz, 'title')} embedded onFinished={finished} onClose={() => { setRunning(null); refresh() }} /> : <>
        <QuizSummary quiz={quiz} now={now} busy={busy || loading} start={start} />
        {quiz.attempts.length > 0 && <details className="inline-quiz-history"><summary>{tr('История результатов')}</summary>{[...quiz.attempts].sort((a, b) => b.attempt_no - a.attempt_no).map(attempt => <p key={attempt.id}>{tr('Попытка ')}{attempt.attempt_no} · {attempt.status === 'active' ? tr('Идёт') : tr('{0}/{1} баллов{2}', [attempt.score, attempt.max_score, attempt.auto_submitted ? tr(' · Проверено автоматически по таймеру') : ''])}</p>)}</details>}
      </>}
    </>}
  </section>
}

export function TeacherPreview({ quiz, courseId, runId, canEdit }: { quiz: Quiz; courseId: number; runId: number; canEdit: boolean }) {
  return <div className="inline-quiz-preview">
    
    {!quiz.is_published && <p className="inline-quiz-notice">{tr('Тест пока в черновике.')}</p>}
    {!quiz.questions?.length && <p>{tr('В тесте пока нет вопросов')}</p>}
    {quiz.questions?.map((question, index) => <fieldset className="inline-quiz-preview-question" key={question.id ?? index} disabled><legend>{index + 1}. {ct(question, 'body')}</legend>{question.options.map((_value, option) => <label className="quiz-option" key={option}><input type="radio" name={`preview-step-quiz-${quiz.id}-${question.id ?? index}`} checked={false} readOnly />{ct(question, 'options', option)}</label>)}</fieldset>)}
    <a className="inline-quiz-settings" href={`#course=${courseId}&run=${runId}&tab=quizzes&activity=${quiz.id}`}>{canEdit ? tr('Настроить этот тест →') : tr('Расписание и результаты теста →')}</a>
  </div>
}

export function QuizSummary({ quiz, now, busy, start }: { quiz: Quiz; now: number; busy: boolean; start: () => void }) {
  const active = quiz.attempts.find(attempt => attempt.status === 'active')
  const future = Boolean(quiz.opens_at && now < Date.parse(quiz.opens_at))
  const closed = Boolean(quiz.closes_at && now >= Date.parse(quiz.closes_at))
  const exhausted = !active && quiz.attempts.length >= quiz.max_attempts
  const finished = quiz.attempts.filter(attempt => attempt.status !== 'active')
  const best = finished.length ? Math.max(...finished.map(attempt => attempt.score)) : null
  return <div className="inline-quiz-ready">
    {best !== null && <p className="inline-quiz-best">{tr('Лучший результат: {0}/{1}', [best, quiz.questions_count])}</p>}
    
    <div className="inline-quiz-rules"><span>{tr('Время: {0} мин.', [quiz.time_limit_sec / 60])}</span><span>{tr('Доступно попыток: {0}', [Math.max(0, quiz.max_attempts - quiz.attempts.length)])}</span></div>
    {future && <p className="inline-quiz-notice">{tr('Задание откроется: {0}', [formatDate(quiz.opens_at)])}</p>}
    {closed && <p className="inline-quiz-notice">{tr('Приём ответов завершён.')}</p>}
    {exhausted && <p className="inline-quiz-notice">{tr('Все попытки использованы.')}</p>}
    {!quiz.questions_count && <p className="inline-quiz-notice">{tr('В тесте пока нет вопросов')}</p>}
    <button type="button" disabled={busy || future || closed || exhausted || !quiz.questions_count} onClick={start}>{busy ? tr('Загрузка…') : active ? tr('Продолжить задание') : finished.length ? tr('Попробовать ещё раз') : tr('Начать задание')}</button>
    
  </div>
}
