import { ct } from '../../i18n/content'
import { t as tr, getLanguage } from '../../i18n/language'
import RoleBadge from '../../components/RoleBadge'
import { useEffect, useState } from 'react'
import { apiRequest } from '../../api'
import { type StudyData, errorMessage } from './types'
import StudentDetail from './StudentDetail'

type Column = { id: number; title: string; max_score: number }
type Report = {
  assignments: Column[]; quizzes: Column[]; code_problems: Column[]
  students: { student_id: number; student: string; display_name: string; role_label: string; progress: StudyData['progress']; assignments: Record<string, number | null>; quizzes: Record<string, number | null>; code: Record<string, number | null> }[]
}

export default function Results({ courseId, runId, data, manage }: { courseId: number; runId: number; data: StudyData; manage: boolean }) {
  const [report, setReport] = useState<Report | null>(null)
  const [error, setError] = useState('')
  const [studentId, setStudentId] = useState<number | null>(() => Number(new URLSearchParams(location.hash.slice(1)).get('student')) || null)
  const [search, setSearch] = useState('')
  function selectStudent(id: number | null) {
    setStudentId(id)
    window.history.replaceState(null, '', `#course=${courseId}&run=${runId}&tab=results${id ? `&student=${id}` : ''}`)
  }
  useEffect(() => {
    let alive = true
    if (manage) apiRequest<Report>(`/api/study/courses/${courseId}/report/?run_id=${runId}`)
      .then(value => { if (alive) setReport(value) }).catch(err => { if (alive) setError(errorMessage(err)) })
    return () => { alive = false }
  }, [courseId, runId, manage])
  if (manage && studentId) return <StudentDetail key={studentId} courseId={courseId} runId={runId} studentId={studentId} onBack={() => selectStudent(null)} />
  if (manage) return <section className="study-section">
    <h2>{tr("Журнал успеваемости")}</h2><p><a href={`/api/study/courses/${courseId}/report.csv?run_id=${runId}&language=${getLanguage()}`}>{tr("Скачать журнал CSV")}</a></p>
    <label className="search-field">{tr("Найти ученика")}<input value={search} onChange={e => setSearch(e.target.value)} placeholder={tr("Имя или логин")} /></label>
    {error && <p role="alert" className="error">{tr(error)}</p>}
    {!report && !error && <p>{tr("Загрузка журнала…")}</p>}
    {report && <div className="table-scroll" tabIndex={0} role="region" aria-label={tr("Таблица прокручивается по горизонтали")}><table className="results-table"><thead><tr><th>{tr("Студент")}</th><th>{tr("Обязательные шаги")}</th>{report.assignments.map(a => <th key={`a${a.id}`}>{ct(a, "title")}<small> / {a.max_score}</small></th>)}{report.quizzes.map(q => <th key={`q${q.id}`}>{ct(q, "title")}<small> / {q.max_score}</small></th>)}{report.code_problems.map(p => <th key={`c${p.id}`}>{ct(p, "title")}<small> / {p.max_score} {tr(" тестов")}</small></th>)}</tr></thead>
      <tbody>{report.students.filter(s => `${s.display_name} ${s.student}`.toLowerCase().includes(search.toLowerCase())).map(s => <tr key={s.student_id}><td><button className="student-name" onClick={() => selectStudent(s.student_id)}>{s.display_name || s.student}</button><RoleBadge label={tr(s.role_label)} /><button className="secondary" onClick={() => selectStudent(s.student_id)}>{tr("Открыть ответы →")}</button></td><td><strong>{s.progress.percent}%</strong><progress max={100} value={s.progress.percent} />{s.progress.completed}/{s.progress.total} {tr(" шагов")}</td>{report.assignments.map(a => <td key={`a${a.id}`}>{s.assignments[a.id] ?? '—'}</td>)}{report.quizzes.map(q => <td key={`q${q.id}`}>{s.quizzes[q.id] ?? '—'}</td>)}{report.code_problems.map(p => <td key={`c${p.id}`}>{s.code[p.id] ?? '—'}</td>)}</tr>)}</tbody>
    </table>{!report.students.length && <p className="empty-state">{tr("На курс пока никто не записан.")}</p>}</div>}
  </section>
  const rows: { key: string; kind: string; title: string; value: string | null; status: string; tone: string }[] = [
    ...data.assignments.map(a => {
      const grades = a.submissions.filter(s => s.score !== null).map(s => s.score as number)
      return { key: `a${a.id}`, kind: tr('Задание'), title: ct(a, 'title'), value: grades.length ? `${Math.max(...grades)}/${a.max_score}` : null, status: a.submissions.length ? tr('На проверке') : tr('Не сдано'), tone: a.submissions.length ? 'is-info' : '' }
    }),
    ...data.quizzes.map(q => {
      const grades = q.attempts.filter(a => a.status === 'finished')
      return { key: `q${q.id}`, kind: tr('Тест'), title: ct(q, 'title'), value: grades.length ? `${Math.max(...grades.map(a => a.score))}/${q.questions_count}` : null, status: tr('Не пройден'), tone: '' }
    }),
    ...data.code_results.map(p => ({ key: `c${p.id}`, kind: 'Python', title: ct(p, 'title'), value: p.passed === null ? null : tr('{0}/{1} тестов', [p.passed, p.total]), status: tr('Не решено'), tone: '' })),
  ]
  return <section className="page results-page" aria-labelledby="results-title">
    <h2 className="section-title" id="results-title">{tr('Мои результаты')}</h2>
    <div className="card results-summary">
      <p className="results-summary-label">{tr('Обязательные шаги')}</p>
      <div className="progress"><span className="progress-bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={data.progress.percent} aria-label={tr('Прогресс курса')}><span style={{ width: `${data.progress.percent}%` }} /></span>
        <span className="progress-text">{tr('{0} из {1} шагов · {2}%', [String(data.progress.completed), String(data.progress.total), String(data.progress.percent)])}</span></div>
    </div>
    {rows.length > 0 ? <ul className="list">{rows.map(row => <li className="list-row" key={row.key}>
      <div className="list-row-main"><p className="agenda-kind">{row.kind}</p><p className="list-row-title">{row.title}</p></div>
      <div className="list-row-side">{row.value ? <span className="list-row-value">{row.value}</span> : <span className={`badge ${row.tone}`}>{row.status}</span>}</div>
    </li>)}</ul> : <div className="empty"><p>{tr('В курсе пока нет заданий и тестов с оценкой.')}</p></div>}
  </section>
}
