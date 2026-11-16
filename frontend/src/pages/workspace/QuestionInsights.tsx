import { ct } from '../../i18n/content'
import { t as tr } from '../../i18n/language'
import { useEffect, useState } from 'react'
import { apiRequest } from '../../api'
import { errorMessage } from '../study/types'

type Insights = { questions: { id: number; body: string; quiz: string; course: string; samples: number; correct_percent: number | null; unanswered: number; options: { label: string; count: number; correct: boolean }[] }[]; total: number; next_page: number | null }
export default function QuestionInsights({ query }: { query: string }) {
  const [data, setData] = useState<Insights | null>(null), [error, setError] = useState(''), [page, setPage] = useState(1)
  useEffect(() => { let alive = true; apiRequest<Insights>(`/api/workspace/question-insights/?${query}&page=${page}`).then(v => { if (alive) { setData(v); setError('') } }).catch(e => { if (alive) setError(errorMessage(e)) }); return () => { alive = false } }, [query, page])
  return <section className="analytics-panel"><h3>{tr("Разбор вопросов теста")}</h3>{error && <p role="alert" className="error">{tr(error)}</p>}
    {data?.questions.map(q => <details className="question-insight" key={q.id}><summary>{ct(q, "body")} {tr(" · Верно: ")}{q.correct_percent ?? '—'}% · {q.samples} {tr(" попыток")}</summary><p className="analytics-muted">{ct(q, "course")} · {q.quiz}</p>{q.options.map((o, i) => <div className="insight-option" key={i}><span>{ct(o, "label")}{o.correct && tr(" · правильный")}</span><progress max={q.samples} value={o.count} /><strong>{o.count}</strong></div>)}<p className="analytics-muted">{tr("Без ответа: ")}{q.unanswered}</p></details>)}{data && !data.questions.length && <p className="analytics-muted">{tr("Первых завершённых попыток в выбранном периоде нет.")}</p>}<div className="action-row"><button className="secondary" disabled={page === 1} onClick={() => setPage(v => v-1)}>{tr("← Назад")}</button><span>{tr("Страница ")}{page}</span><button className="secondary" disabled={!data?.next_page} onClick={() => setPage(v => v+1)}>{tr("Далее →")}</button></div></section>
}
