import { ct } from '../../i18n/content'
import { t as tr } from '../../i18n/language'
import { useEffect, useState, type FormEvent } from 'react'
import { apiRequest } from '../../api'
import { errorMessage } from '../study/types'
import ConfirmAction from '../study/ConfirmAction'

type Config = { id: number; lesson_id: number; pre_quiz_id: number | null; post_quiz_id: number | null }
type Options = { lessons: { id: number; title: string }[]; quizzes: { id: number; title: string }[]; evaluations: Config[] }
export default function EvaluationForm({ runId, saved }: { runId: string; saved: () => void }) {
  const [data, setData] = useState<Options | null>(null)
  const [lesson, setLesson] = useState(''), [pre, setPre] = useState(''), [post, setPost] = useState('')
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [message, setMessage] = useState('')
  const [revision, setRevision] = useState(0)
  useEffect(() => { let alive = true; apiRequest<Options>(`/api/analytics/evaluations/?run_id=${runId}`).then(value => { if (alive) setData(value) }).catch(err => { if (alive) setError(errorMessage(err)) }); return () => { alive = false } }, [runId, revision])
  function selectLesson(id: string) { setLesson(id); const existing = data?.evaluations.find(c => String(c.lesson_id) === id); setPre(existing?.pre_quiz_id ? String(existing.pre_quiz_id) : ''); setPost(existing?.post_quiz_id ? String(existing.post_quiz_id) : '') }
  async function save(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setMessage('')
    try { await apiRequest('/api/analytics/evaluations/', 'POST', { run_id: Number(runId), lesson_id: Number(lesson), pre_quiz_id: Number(pre), post_quiz_id: Number(post) }); setRevision(v => v + 1); setMessage('Сравнение сохранено. Результаты появятся после прохождения обоих тестов и открытия материала между ними.'); saved() } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }
  async function remove(config: Config) { try { await apiRequest('/api/analytics/evaluations/', 'DELETE', { run_id: Number(runId), lesson_id: config.lesson_id }); setRevision(v => v + 1); selectLesson(''); saved() } catch (err) { setError(errorMessage(err)) } }
  return <details className="analytics-panel evaluation-settings"><summary>{tr("Настроить входной и итоговый тесты")}</summary>{error && <p className="error" role="alert">{tr(error)}</p>}{message && <p className="success" role="status">{tr(message)}</p>}{!data ? <p>{tr("Загрузка настроек…")}</p> : data.quizzes.length < 2 ? <p>{tr("Для сравнения нужны два опубликованных теста.")}</p> : <form className="analytics-filter-grid" onSubmit={save}><label>{tr("Урок")}<select aria-label={tr("Урок для сравнения")} required value={lesson} onChange={e => selectLesson(e.target.value)}><option value="">{tr("Выберите урок")}</option>{data.lessons.map(l => <option key={l.id} value={l.id}>{ct(l, "title")}</option>)}</select></label><label>{tr("Входной тест")}<select aria-label={tr("Входной тест")} required value={pre} onChange={e => setPre(e.target.value)}><option value="">{tr("До материала")}</option>{data.quizzes.map(q => <option key={q.id} value={q.id}>{ct(q, "title")}</option>)}</select></label><label>{tr("Итоговый тест")}<select aria-label={tr("Итоговый тест")} required value={post} onChange={e => setPost(e.target.value)}><option value="">{tr("После материала")}</option>{data.quizzes.map(q => <option key={q.id} value={q.id}>{ct(q, "title")}</option>)}</select></label><button disabled={busy || !lesson || !pre || !post || pre === post}>{tr("Сохранить сравнение")}</button></form>}{data?.evaluations.map(c => <div className="analytics-config-row" key={c.id}><span><strong>{ct(data.lessons.find(l => l.id === c.lesson_id), "title") || tr("Урок")}</strong><small>{ct(data.quizzes.find(q => q.id === c.pre_quiz_id), "title") || tr("Входной тест недоступен")} → {ct(data.quizzes.find(q => q.id === c.post_quiz_id), "title") || tr("Итоговый тест недоступен")}</small></span><button className="secondary" onClick={() => selectLesson(String(c.lesson_id))}>{tr("Изменить")}</button><ConfirmAction label={tr("Убрать связь")} question={tr("Убрать это сравнение? Тесты и ответы учеников сохранятся.")} onConfirm={() => remove(c)} /></div>)}</details>
}
