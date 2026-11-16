import { ct } from '../../i18n/content'
import { localizedLabels, t as tr } from '../../i18n/language'
import { RubricResult, ReviewHistory } from '../workspace/Grading'
import RoleBadge from '../../components/RoleBadge'
import { useEffect, useState } from 'react'
import { apiRequest } from '../../api'
import { type Submission, type Attempt, errorMessage, formatDate } from './types'

type StudentReport = {
  student: { id: number; username: string; display_name: string; role_label: string }; run: { title: string }
  status: string; enrolled_at: string; last_seen_at: string | null; last_step: string | null
  progress: { completed: number; total: number; percent: number }
  lessons: { id: number; title: string; module: string; completed: boolean; completed_at: string | null; steps: { id: number; title: string; kind: string; required: boolean; is_published: boolean; completed: boolean; completed_at: string | null }[] }[]
  assignments: { id: number; title: string; max_score: number; submissions: Submission[] }[]
  quizzes: { id: number; title: string; attempts: (Attempt & { started_at: string; answers: { id: number; body: string; options: string[]; selected_index: number | null; correct_index: number; correct: boolean }[] })[] }[]
  code_problems: { id: number; title: string; submissions: { id: number; code: string; status: string; passed: number; total: number; created_at: string }[] }[]
}
const statuses: Record<string, string> = localizedLabels({ active: 'В процессе', completed: 'Завершено', archived: 'В архиве', removed: 'Доступ отозван', submitted: 'На проверке', graded: 'Проверено', returned: 'На доработку', finished: 'Завершён', expired: 'Время истекло', accepted: 'Принято', rejected: 'Есть ошибки', running: 'Проверяется', service_error: 'Ошибка сервиса' })
const kinds: Record<string, string> = localizedLabels({ text: 'Теория', video: 'Видео', file: 'Материал', assignment: 'Задание', quiz: 'Тест', code: 'Python' })

export default function StudentDetail({ courseId, runId, studentId, onBack }: { courseId: number; runId: number; studentId: number; onBack: () => void }) {
  const [data, setData] = useState<StudentReport | null>(null)
  const [tab, setTab] = useState('lessons')
  const [error, setError] = useState('')
  useEffect(() => {
    let alive = true
    apiRequest<StudentReport>(`/api/study/courses/${courseId}/students/${studentId}/?run_id=${runId}`)
      .then(value => { if (alive) setData(value) }).catch(err => { if (alive) setError(errorMessage(err)) })
    return () => { alive = false }
  }, [courseId, runId, studentId])
  return <section className="study-section student-detail">
    <button className="secondary back-btn" onClick={onBack}>{tr("← Все ученики")}</button>
    {error && <p className="error" role="alert">{tr(error)}</p>}
    {!data && !error && <p>{tr("Загрузка ответов ученика…")}</p>}
    {data && <>
      <div className="section-heading"><div><h2>{data.student.display_name}<RoleBadge label={tr(data.student.role_label)} /></h2><p className="muted">{ct(data.run, "title")} · {statuses[data.status] ?? data.status}</p></div><a href={`#profile=${data.student.id}`}>{tr("Профиль ученика →")}</a></div>
      <div className="learner-summary"><div><strong>{data.progress.percent}%</strong><span>{data.progress.completed} {tr(" из ")}{data.progress.total} {tr(" обязательных шагов")}</span></div><div><strong>{tr("Последняя активность")}</strong><span>{data.last_seen_at ? formatDate(data.last_seen_at) : tr("Ещё не открывал шаги")}</span></div><div><strong>{tr("Последний открытый шаг")}</strong><span>{data.last_step || tr("Нет")}</span></div></div>
      
      <div className="course-tabs" role="tablist" aria-label={tr("Детали ученика")}>{[['lessons', tr("Прохождение уроков")], ['assignments', tr("Письменные работы")], ['quizzes', tr("Ответы в тестах")], ['code', tr("Решения Python")]].map(([id, label]) => <button role="tab" aria-selected={tab === id} key={id} onClick={() => setTab(id)}>{ct(label)}</button>)}</div>
      {tab === 'lessons' && <>{!data.lessons.length && <p className="empty-state">{tr("В курсе пока нет уроков.")}</p>}{data.lessons.map(l => <article className="study-card" key={l.id}><p className="eyebrow">{ct(l, "module")}</p><div className="section-heading"><h3>{ct(l, "title")}</h3><span className={`status-pill ${l.completed ? 'done' : ''}`}>{l.completed ? tr("✓ Пройден") : tr("Не завершён")}</span></div>{l.completed_at && <p className="muted">{tr("Завершён: ")}{formatDate(l.completed_at)}</p>}<div className="step-progress-list">{l.steps.map(s => <div className="step-progress-row" key={s.id}><span className={`step-status ${s.completed ? 'done' : ''}`}>{s.completed ? '✓' : '○'}</span><div><strong>{ct(s, "title")}</strong><small>{kinds[s.kind]} · {s.is_published ? s.required ? tr("Обязательный") : tr("Дополнительный") : tr("Черновик / скрыт")}</small></div><span className="muted">{s.completed_at ? formatDate(s.completed_at) : s.completed ? tr("Пройден") : tr("Не пройден")}</span></div>)}</div></article>)}</>}
      {tab === 'assignments' && <>{!data.assignments.length && <p className="empty-state">{tr("Письменных заданий пока нет.")}</p>}{data.assignments.map(a => <article className="study-card" key={a.id}><h3>{ct(a, "title")}</h3>{!a.submissions.length && <p className="muted">{tr("Ученик ещё не отправлял работу.")}</p>}{a.submissions.map(s => <details className="attempt-card" key={s.id}><summary>{tr("Попытка ")}{s.attempt_no} · {statuses[s.status] ?? s.status} · {s.score === null ? tr("Без оценки") : `${s.score}/${a.max_score}`} · {formatDate(s.submitted_at)}</summary><h4>{tr("Ответ ученика")}</h4><p className="preserve-text">{ct(s, "text_answer") || tr("Текстовый ответ не приложен.")}</p>{s.file_url && <p><a href={s.file_url} target="_blank" rel="noreferrer">{tr("Скачать ответ: ")}{s.file_name}</a></p>}<RubricResult result={s.rubric_result} />{s.feedback && <p className="feedback">{tr("Комментарий преподавателя: ")}{ct(s, "feedback")}</p>}<ReviewHistory reviews={s.reviews} /></details>)}{a.submissions.length > 0 && <a href={`#course=${courseId}&run=${runId}&tab=assignments`}>{tr("Перейти к проверке работ →")}</a>}</article>)}</>}
      {tab === 'quizzes' && <>{!data.quizzes.length && <p className="empty-state">{tr("Тестов пока нет.")}</p>}{data.quizzes.map(q => <article className="study-card" key={q.id}><h3>{ct(q, "title")}</h3>{!q.attempts.length && <p className="muted">{tr("Ученик ещё не начинал тест.")}</p>}{q.attempts.map(a => <details className="attempt-card" key={a.id}><summary>{tr("Попытка ")}{a.attempt_no} · {statuses[a.status] ?? a.status} · {a.status === 'finished' ? `${a.score}/${a.max_score}` : tr("Результат не зафиксирован")} · {formatDate(a.started_at)}</summary>{a.answers.map((answer, index) => <div className="answer-review" key={answer.id}><h4>{index + 1}. {ct(answer, "body")}</h4><p className={answer.selected_index === null ? 'muted' : answer.correct ? 'answer-correct' : 'error'}>{answer.selected_index === null ? tr("Ответ не выбран") : answer.correct ? tr("✓ Выбран правильный ответ") : tr("✕ Выбран неправильный ответ")}</p>{answer.options.map((_option, i) => <div className={`answer-option ${i === answer.correct_index ? 'correct' : ''} ${i === answer.selected_index ? 'chosen' : ''}`} key={i}><span>{i === answer.selected_index ? '●' : '○'}</span><span>{ct(answer, 'options', i)}</span>{i === answer.selected_index && <small>{tr("Ответ ученика")}</small>}{i === answer.correct_index && <small>{tr("Правильный")}</small>}</div>)}</div>)}</details>)}</article>)}</>}
      {tab === 'code' && <>{!data.code_problems.length && <p className="empty-state">{tr("Задач Python пока нет.")}</p>}{data.code_problems.map(p => <article className="study-card" key={p.id}><h3>{ct(p, "title")}</h3>{!p.submissions.length && <p className="muted">{tr("Решений пока нет.")}</p>}{p.submissions.map(s => <details className="attempt-card" key={s.id}><summary>{tr("Отправка #")}{s.id} · {statuses[s.status] ?? s.status} · {s.passed}/{s.total} {tr(" тестов · ")}{formatDate(s.created_at)}</summary><pre className="code-editor">{s.code}</pre></details>)}</article>)}</>}
    </>}
  </section>
}
