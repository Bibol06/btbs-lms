import { ct } from '../../i18n/content'
import { getLocale, t as tr } from '../../i18n/language'
import { useId, useState } from 'react'
import type { SeriesPoint } from './types'

const shortDate = (value: string) => new Date(`${value}T12:00:00`).toLocaleDateString(getLocale(), { day: 'numeric', month: 'short' })
export function TrendChart({ data, metric, label, percent = false }: { data: SeriesPoint[]; metric: 'progress' | 'submissions' | 'reviews' | 'quizzes' | 'learning_actions'; label: string; percent?: boolean }) {
  const [selected, setSelected] = useState<number | null>(null)
  const uid = useId().replaceAll(':', '')
  const width = 760, height = 228, left = 45, right = 18, top = 15, bottom = 35
  const maximum = percent ? 100 : Math.max(1, ...data.map(d => Number(d[metric] || 0)))
  const ticks = percent ? [0, 25, 50, 75, 100] : maximum <= 4 ? Array.from({ length: maximum+1 }, (_, i) => i) : [...new Set([0, .25, .5, .75, 1].map(r => Math.round(maximum*r)))]
  const x = (i: number) => left + (data.length <= 1 ? 0 : i / (data.length - 1)) * (width - left - right)
  const y = (v: number) => height - bottom - v / maximum * (height - top - bottom)
  const segments: string[] = []; let segment = ''
  data.forEach((d, i) => { const value = d[metric]; if (value === null) { if (segment) segments.push(segment); segment = '' } else segment += `${segment ? ' L' : 'M'} ${x(i)} ${y(value)}` })
  if (segment) segments.push(segment)
  const current = selected === null ? null : data[selected]
  const known = data.some(d => d[metric] !== null)
  return <div className="analytics-chart"><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-labelledby={`${uid}-title ${uid}-desc`}><title id={`${uid}-title`}>{ct(label)}</title><desc id={`${uid}-desc`}>{tr("График по дням. Для точных значений откройте таблицу под графиком. Нет данных — разрыв линии.")}</desc>{ticks.map(value => <g key={value}><line x1={left} x2={width-right} y1={y(value)} y2={y(value)} stroke="#e7ece9" /><text x={left-10} y={y(value)+4} textAnchor="end">{value}{percent ? '%' : ''}</text></g>)}{segments.map((d, i) => <path key={i} d={d} fill="none" stroke="#31824d" strokeWidth={3} strokeLinejoin="round" />)}{data.map((d, i) => <g key={d.date}>{d[metric] !== null && <circle cx={x(i)} cy={y(d[metric] as number)} r={data.length < 35 ? 3 : 1.8} fill="#31824d" />}{(i === 0 || i === data.length-1 || i === Math.floor(data.length/2)) && <text x={x(i)} y={height-10} textAnchor={i === 0 ? 'start' : i === data.length-1 ? 'end' : 'middle'}>{shortDate(d.date)}</text>}<rect x={x(i)-Math.max(3, (width-left-right)/data.length/2)} y={top} width={Math.max(6, (width-left-right)/data.length)} height={height-top-bottom} fill="transparent" onPointerEnter={() => setSelected(i)} onPointerLeave={() => setSelected(null)} onClick={() => setSelected(i)} /></g>)}</svg><p className="chart-caption" aria-live="polite">{current ? `${shortDate(current.date)}: ${current[metric] === null ? tr("нет наблюдения") : `${current[metric]}${percent ? '%' : ''}`}${percent ? tr(" · Прохождений с известным прогрессом: {0}", [current.known_enrollments]) : ''}` : known ? '' : tr("Нет данных")}</p><details><summary>{tr("Значения по дням")}</summary><div className="analytics-table-wrap"><table className="analytics-table"><thead><tr><th>{tr("Дата")}</th><th>{ct(label)}</th>{percent && <th>{tr("Известных прохождений")}</th>}</tr></thead><tbody>{data.map(d => <tr key={d.date}><td>{shortDate(d.date)}</td><td>{d[metric] === null ? tr("Нет данных") : `${d[metric]}${percent ? '%' : ''}`}</td>{percent && <td>{d.known_enrollments}</td>}</tr>)}</tbody></table></div></details></div>
}

export function BeforeAfter({ before, after, pairs }: { before: number | null; after: number | null; pairs: number }) {
  if (!pairs || before === null || after === null) return <p className="analytics-empty-inline">{tr("Пока нет сопоставимых результатов до и после изучения материала.")}</p>
  return <div className="before-after"><div><span>{tr("До урока")}</span><div className="comparison-track"><i style={{ width: `${before}%` }} /></div><strong>{before}%</strong></div><div><span>{tr("После урока")}</span><div className="comparison-track after"><i style={{ width: `${after}%` }} /></div><strong>{after}%</strong></div><small>{tr("Те же прохождения: ")}{pairs}</small></div>
}
