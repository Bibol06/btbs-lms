import { ct } from '../../i18n/content'
import { t as tr } from '../../i18n/language'
import type { RunOption } from './useOverview'

export function Metrics({ values, items }: { values: Record<string, number>; items: [string, string][] }) {
  return <div className="management-metrics">{items.map(([key, label]) => <div className={`management-metric ${['overdue', 'unassigned'].includes(key) && values[key] > 0 ? 'attention' : ''}`} key={key}><strong>{values[key] ?? 0}</strong><span>{ct(label)}</span></div>)}</div>
}
export function RunFilters({ runs, course, run, change }: { runs: RunOption[]; course: string; run: string; change: (course: string, run: string) => void }) {
  const courses = [...new Map(runs.map(r => [r.course_id, ct(r, "course")])).entries()]
  return <><label>{tr("Курс")}<select aria-label={tr("Курс")} value={course} onChange={e => change(e.target.value, '')}><option value="">{tr("Все доступные курсы")}</option>{courses.map(([id, title]) => <option key={id} value={id}>{ct(title)}</option>)}</select></label><label>{tr("Группа / формат")}<select aria-label={tr("Группа / формат")} value={run} onChange={e => change(course, e.target.value)}><option value="">{tr("Все группы")}</option>{runs.filter(r => !course || r.course_id === Number(course)).map(r => <option key={r.id} value={r.id}>{ct(r, "title")}{!course ? ` · ${ct(r, "course")}` : ''}</option>)}</select></label></>
}
export function Pagination({ page, total, next, change }: { page: number; total: number; next: number | null; change: (page: number) => void }) {
  return <div className="management-pagination"><span>{tr("Всего записей: ")}{total}</span>{(page > 1 || next) && <><button className="secondary" disabled={page === 1} onClick={() => change(page - 1)}>{tr("← Назад")}</button><span>{tr("Страница ")}{page}</span><button className="secondary" disabled={!next} onClick={() => next && change(next)}>{tr("Далее →")}</button></>}</div>
}
