import { ct } from '../../i18n/content'
import { auditCaption } from '../../i18n/captions'
import { t as tr } from '../../i18n/language'
import WorkspaceHome from '../workspace/WorkspaceHome'
import { useEffect, useState } from 'react'
import { apiRequest, type User } from '../../api'
import RoleBadge from '../../components/RoleBadge'
import { errorMessage, formatDate } from '../study/types'
import ReviewQueue from '../study/ReviewQueue'
import { CourseForm } from '../teacher/TeacherDashboard'
import { useOverview } from './useOverview'
import { Metrics, Pagination, RunFilters } from './ManagementParts'
import './Management.css'
import '../study/Deadlines.css'

type Teacher = { id: number; display_name: string; role_label: string; is_active: boolean; courses: number; groups: number; students: number; pending: number; overdue: number; unassigned: number; reviewed_week: number; last_review_at: string | null }
type Course = { id: number; title: string; description: string; teacher: string; is_published: boolean; groups: number; students: number; pending: number; overdue: number }
type Event = { id: number; actor: { display_name: string; role_label: string } | null; course: string; course_id: number; action: string; created_at: string }
type Result = { teachers?: Teacher[]; courses?: Course[]; events?: Event[]; page: number; total: number; next_page: number | null }

export default function AdminControl({ user, section = 'overview' }: { user: User; section?: 'overview' | 'teachers' | 'courses' | 'reviews' | 'activity' }) {
  const [revision, setRevision] = useState(0)
  const { data: overview, error: overviewError } = useOverview(revision)
  const [data, setData] = useState<Result | null>(null)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [course, setCourse] = useState('')
  const [run, setRun] = useState('')
  const [reviewer, setReviewer] = useState(() => new URLSearchParams(location.hash.slice(1)).get('reviewer') || '')
  const [reviewerName, setReviewerName] = useState('')
  const [editor, setEditor] = useState<Course | 'new' | null>(null)
  const [teacherSearch, setTeacherSearch] = useState('')
  const [teacherOptions, setTeacherOptions] = useState<Teacher[]>([])
  useEffect(() => {
    if (!['teachers', 'courses', 'activity'].includes(section)) return
    let alive = true
    const query = new URLSearchParams({ search, page: String(page) })
    const timer = window.setTimeout(() => { setLoading(true); apiRequest<Result>(`/api/study/management/${section}/?${query}`).then(value => { if (alive) { setData(value); setError('') } }).catch(err => { if (alive) setError(errorMessage(err)) }).finally(() => { if (alive) setLoading(false) }) }, 200)
    return () => { alive = false; window.clearTimeout(timer) }
  }, [section, search, page, revision])
  const titles = { overview: tr(user.admin_scope === 'learning' ? 'Обзор обучения' : 'Обзор платформы'), teachers: tr("Контроль работы преподавателей"), courses: tr("Все курсы платформы"), reviews: tr("Контроль проверок"), activity: tr("История действий") }
  function inspectTeacher(teacher: Teacher) { window.location.assign(`#page=reviews&reviewer=${teacher.id}`) }
  const selectedReviewer = reviewer
  useEffect(() => {
    if (section !== 'reviews') return
    let alive = true
    const timer = window.setTimeout(() => { apiRequest<{ teachers: Teacher[] }>(`/api/study/management/teachers/?search=${encodeURIComponent(teacherSearch)}`).then(value => { if (alive) setTeacherOptions(value.teachers) }).catch(err => { if (alive) setError(errorMessage(err)) }) }, 200)
    return () => { alive = false; window.clearTimeout(timer) }
  }, [section, teacherSearch])
  useEffect(() => {
    if (!selectedReviewer) return
    let alive = true
    apiRequest<{ display_name: string }>(`/api/auth/profiles/${selectedReviewer}/`).then(value => { if (alive) setReviewerName(value.display_name) }).catch(() => { if (alive) setReviewerName(tr("Недоступный профиль")) })
    return () => { alive = false }
  }, [selectedReviewer])
  return <section className="management-page admin-control"><div className="section-heading"><div><h2>{titles[section]}</h2></div><button className="secondary" onClick={() => setRevision(v => v + 1)}>{tr("Обновить данные")}</button></div>
    {(error || overviewError) && <p className="error" role="alert">{error || overviewError}</p>}
    {section === 'overview' && (overview ? <><WorkspaceHome /><Metrics values={overview.metrics} items={[["users", tr("Пользователей")], ["courses", tr("Курсов всего")], ["groups", tr("Учебных групп")], ["students", tr("Учащихся в курсах")]]} /><div className="management-actions"><a className="button-link" href="#page=reviews">{tr("Проверки и задержки →")}</a><a className="button-link" href="#page=admin-teachers">{tr("Работа преподавателей →")}</a><a className="button-link" href="#page=students">{tr("Прогресс и ответы учеников →")}</a></div><p className="muted">{tr("Активных записей на обучение: ")}{overview.metrics.active_enrollments} {tr(" · Завершённых: ")}{overview.metrics.completed_enrollments}</p></> : !overviewError && <p>{tr("Загрузка обзора…")}</p>)}
    {section === 'courses' && <div className="action-row"><button onClick={() => setEditor('new')}>{tr("+ Создать курс")}</button></div>}
    {editor && <CourseForm key={editor === 'new' ? 'new' : editor.id} initial={editor === 'new' ? undefined : editor} onSaved={() => { setEditor(null); setRevision(v => v + 1) }} onCancel={() => setEditor(null)} />}
    {section === 'reviews' && <><div className="management-filters"><RunFilters runs={overview?.runs || []} course={course} run={run} change={(c, r) => { setCourse(c); setRun(r) }} /><label>{tr("Поиск преподавателя")}<input value={teacherSearch} onChange={e => setTeacherSearch(e.target.value)} placeholder={tr("Введите фамилию или имя")} /></label><label>{tr("Ответственный преподаватель")}<select aria-label={tr("Ответственный преподаватель")} value={selectedReviewer} onChange={e => { setReviewer(e.target.value); window.history.replaceState(null, '', '#page=reviews') }}><option value="">{tr("Все преподаватели")}</option>{selectedReviewer && !teacherOptions.some(t => String(t.id) === selectedReviewer) && <option value={selectedReviewer}>{reviewerName || tr("Загрузка имени…")}</option>}{teacherOptions.map(teacher => <option key={teacher.id} value={teacher.id}>{teacher.display_name} · {tr(teacher.role_label)}</option>)}</select></label>{selectedReviewer && <button className="secondary" onClick={() => { setReviewer(''); setReviewerName(''); window.history.replaceState(null, '', '#page=reviews') }}>{tr("Сбросить преподавателя")}{reviewerName ? `: ${reviewerName}` : ''}</button>}</div><ReviewQueue key={`${course}-${run}-${selectedReviewer}-${revision}`} userId={user.id} monitor courseId={course} runId={run} reviewerId={selectedReviewer} /></>}
    {['teachers', 'courses'].includes(section) && <div className="management-filters"><label>{section === 'teachers' ? tr("Найти преподавателя") : tr("Найти курс")}<input value={search} onChange={e => { setLoading(true); setSearch(e.target.value); setPage(1) }} placeholder={section === 'teachers' ? tr("Фамилия, имя или логин") : tr("Название курса")} /></label></div>}
    {['teachers', 'courses', 'activity'].includes(section) && (loading || !data ? !error && <p role="status">{tr("Загрузка…")}</p> : <><Pagination page={page} total={data.total} next={data.next_page} change={p => { setLoading(true); setPage(p) }} />
      {section === 'teachers' && <div className="management-table-wrap" tabIndex={0} role="region" aria-label={tr("Таблица прокручивается по горизонтали")}><table className="management-table"><thead><tr><th>{tr("Преподаватель")}</th><th>{tr("Курсы и ученики")}</th><th>{tr("Назначенные проверки")}</th><th>{tr("Выполнено")}</th><th>{tr("Действия")}</th></tr></thead><tbody>{data.teachers?.map(teacher => <tr key={teacher.id}><td><strong>{teacher.display_name}</strong><RoleBadge label={tr(teacher.role_label)} /><small>{teacher.is_active ? tr("Активен") : tr("Неактивен")}</small></td><td>{teacher.courses} {tr(" курсов · ")}{teacher.groups} {tr(" групп")}<small>{teacher.students} {tr(" учеников")}</small></td><td>{teacher.pending} {tr(" работ")}<small className={teacher.overdue ? 'error' : ''}>{tr("Просрочено: ")}{teacher.overdue}</small><small>{tr("Без ответственного в его группах: ")}{teacher.unassigned}</small></td><td>{tr("Проверок / возвратов за 7 дней: ")}{teacher.reviewed_week}<small>{teacher.last_review_at ? tr("Последняя проверка: {0}", [formatDate(teacher.last_review_at)]) : tr("Проверок пока нет")}</small></td><td><button onClick={() => inspectTeacher(teacher)}>{tr("Посмотреть проверки")}</button><p><a href={`#profile=${teacher.id}`}>{tr("Профиль →")}</a></p></td></tr>)}</tbody></table>{!data.teachers?.length && <p className="empty-state">{tr("Преподаватели не найдены.")}</p>}</div>}
      {section === 'courses' && <div className="management-table-wrap" tabIndex={0} role="region" aria-label={tr("Таблица прокручивается по горизонтали")}><table className="management-table"><thead><tr><th>{tr("Курс")}</th><th>{tr("Преподаватель")}</th><th>{tr("Обучение")}</th><th>{tr("Проверки")}</th><th>{tr("Подробности")}</th></tr></thead><tbody>{data.courses?.map(item => <tr key={item.id}><td><strong>{ct(item, "title")}</strong><small>{item.is_published ? tr("Опубликован") : tr("Черновик")}</small></td><td>{item.teacher}</td><td>{item.groups} {tr(" групп · ")}{item.students} {tr(" учеников")}</td><td>{item.pending} {tr(" ожидают")}<small>{tr("Просрочено: ")}{item.overdue}</small></td><td><a href={`#course=${item.id}&tab=results`}>{tr("Журнал и ответы →")}</a><p><a href={`#course=${item.id}&tab=groups`}>{tr("Группы и команда →")}</a></p><button className="secondary" onClick={() => setEditor(item)}>{tr("Название и описание")}</button></td></tr>)}</tbody></table>{!data.courses?.length && <p className="empty-state">{tr("Курсы не найдены.")}</p>}</div>}
      {section === 'activity' && <div className="management-events">{!data.events?.length && <p className="empty-state">{tr("События пока не записаны.")}</p>}{data.events?.map(event => <article className="study-card" key={event.id}><time>{formatDate(event.created_at)}</time><p><strong>{event.actor?.display_name || tr("Удалённый пользователь")}</strong><RoleBadge label={tr(event.actor?.role_label)} /> · {auditCaption(event.action)}</p><a href={`#course=${event.course_id}`}>{ct(event, "course")}</a></article>)}</div>}
    </>)}
  </section>
}
