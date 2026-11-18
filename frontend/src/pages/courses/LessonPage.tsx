import CourseLanguageBadge from '../../components/CourseLanguageBadge'
import { ct } from '../../i18n/content'
import { localizedLabels, t as tr } from '../../i18n/language'
import { CourseTools } from '../workspace/AuthorTools'
import { useEffect, useState } from 'react'
import { apiRequest, enrollRequest, type User } from '../../api'
import Curriculum from './Curriculum'
import CourseReadiness, { type ReadinessIssue } from './CourseReadiness'
import RichLessonContent from '../../components/RichLessonContent'
import GroupSettings, { NotificationSettings, type Run } from './GroupSettings'
import StudyPanel from '../study/StudyPanel'
import { Announcements, Conversations } from '../communication/Communication'
import { errorMessage } from '../study/types'
import '../study/Study.css'
import './CourseWorkspace.css'
import LearningPlan from './LearningPlan'

type Props = { courseId: number; user: User | null; onBack: () => void; onNeedAuth: (id: number) => void; onEnrolled: () => void }
type Preview = { course: string; description: string; is_published: boolean; can_manage: boolean; is_enrolled: boolean; lessons: { id: number; title: string }[] }
type Tab = 'plan' | 'overview' | 'lessons' | 'assignments' | 'quizzes' | 'results' | 'announcements' | 'messages' | 'groups' | 'settings' | 'publication'
const tabs: [Tab, string][] = localizedLabels([['plan', 'Учебный план'], ['overview', 'О курсе'], ['lessons', 'Содержание курса'], ['publication', 'Готовность и публикация'], ['assignments', 'Задания'], ['quizzes', 'Тесты'], ['results', 'Ученики и ответы'], ['announcements', 'Объявления'], ['messages', 'Сообщения'], ['groups', 'Группы и команда'], ['settings', 'Настройки']])

export default function LessonPage({ courseId, user, onBack, onNeedAuth, onEnrolled }: Props) {
  const [runs, setRuns] = useState<Run[]>([])
  const [canEdit, setCanEdit] = useState(false)
  const [runId, setRunId] = useState<number | null>(() => Number(new URLSearchParams(location.hash.slice(1)).get('run')) || null)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [revision, setRevision] = useState(0)
  const [tab, setTab] = useState<Tab>(() => {
    const value = new URLSearchParams(location.hash.slice(1)).get('tab') as Tab
    return tabs.some(([id]) => id === value) ? value : 'lessons'
  })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [outlineHost, setOutlineHost] = useState<HTMLDivElement | null>(null)
  const [mobileRailOpen, setMobileRailOpen] = useState(false)
  useEffect(() => {
    function followCourseLink() {
      const route = new URLSearchParams(location.hash.slice(1))
      if (Number(route.get('course')) !== courseId) return
      const next = route.get('tab') as Tab | null
      if (next && tabs.some(([id]) => id === next)) setTab(next === 'publication' && !canEdit || next === 'groups' && !runs.find(item => item.id === runId)?.can_manage ? 'lessons' : next)
      else if (route.has('step') || route.has('lesson')) setTab('lessons')
    }
    window.addEventListener('hashchange', followCourseLink)
    return () => window.removeEventListener('hashchange', followCourseLink)
  }, [courseId, canEdit, runId, runs])
  useEffect(() => {
    let alive = true
    apiRequest<{ runs: Run[]; can_edit_content: boolean }>(`/api/courses/${courseId}/runs/`).then(data => {
      if (alive) {
        setRuns(data.runs); setCanEdit(data.can_edit_content)
        setTab(current => current === 'publication' && !data.can_edit_content || current === 'groups' && !data.runs.some(item => item.can_manage) ? 'lessons' : current)
        setRunId(current => data.runs.some(r => r.id === current) ? current : data.runs.find(r => r.enrollment_id && ['active', 'completed'].includes(r.enrollment_status ?? ''))?.id ?? data.runs.find(r => r.can_manage)?.id ?? data.runs[0]?.id ?? null)
      }
    }).catch(err => { if (alive) setError(errorMessage(err)) })
    return () => { alive = false }
  }, [courseId, user, revision])
  useEffect(() => {
    let alive = true
    if (!runId) return
    apiRequest<Preview>(`/api/learning/courses/${courseId}/lessons/?run_id=${runId}`).then(data => { if (alive) { setPreview(data); setError('') } }).catch(err => { if (alive) { setPreview(null); setError(errorMessage(err)) } })
    return () => { alive = false }
  }, [courseId, runId, revision])
  const run = runs.find(r => r.id === runId)
  const manage = Boolean(run?.can_manage)
  const full = manage || Boolean(run?.enrollment_id && ['active', 'completed'].includes(run.enrollment_status ?? ''))
  function changeTab(next: Tab) {
    setTab(next)
    setMobileRailOpen(false)
    window.history.replaceState(null, '', `#course=${courseId}&run=${runId}&tab=${next}`)
  }
  function changeRun(nextId: number) {
    const next = runs.find(item => item.id === nextId)
    const nextTab = tab === 'groups' && !next?.can_manage || tab === 'publication' && !canEdit ? 'lessons' : tab
    setPreview(null); setRunId(nextId); setTab(nextTab)
    window.history.replaceState(null, '', `#course=${courseId}&run=${nextId}&tab=${nextTab}`)
  }
  function editIssue(issue: ReadinessIssue) {
    if (issue.scope === 'quiz') { changeTab('quizzes'); return }
    setTab('lessons')
    const target = issue.scope === 'step' ? `&step=${issue.id}` : issue.scope === 'lesson' ? `&lesson=${issue.id}` : ''
    window.history.replaceState(null, '', `#course=${courseId}&run=${runId}${target}&edit=1`)
  }
  async function enroll() {
    if (!user) { onNeedAuth(courseId); return }
    setBusy(true); setError('')
    try { await enrollRequest(courseId); onEnrolled(); setRevision(v => v + 1) } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }
  async function publish() {
    setBusy(true)
    try {
      if (preview?.is_published) await apiRequest(`/api/courses/teacher/${courseId}/`, 'PATCH', { is_published: false })
      else await apiRequest(`/api/courses/${courseId}/publish/?run_id=${runId}`, 'POST', { scope: 'course', include_descendants: true })
      setRevision(v => v + 1)
    }
    catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }
  async function bookmark(kind: string) {
    if (!user) { onNeedAuth(courseId); return }
    try { await apiRequest(`/api/courses/${courseId}/bookmark/`, 'POST', { kind }); setMessage('Курс добавлен в ваш список') }
    catch (err) { setError(errorMessage(err)) }
  }
  return <div className="lesson-page notranslate" translate="no">
    <div className="course-heading">
      <div><button className="secondary back-btn" onClick={onBack}>{tr("← Все курсы")}</button><p className="eyebrow">{manage ? user?.role === 'admin' ? tr("Администрирование курса") : tr("Кабинет преподавателя курса") : tr("Учебный курс")}</p><h1>{ct(preview, "course") || tr("Загрузка курса…")}</h1><CourseLanguageBadge course={preview} /></div>
      {run && <label className="run-selector">{manage ? tr("Ученики и результаты группы") : tr("Моя группа / формат обучения")}<select value={runId ?? ''} onChange={e => changeRun(Number(e.target.value))}>{runs.map(r => <option key={r.id} value={r.id}>{ct(r, "title")}{r.enrollment_id ? tr(" · Вы записаны") : ''}</option>)}</select></label>}
    </div>
    {manage && run && <div className="course-author-tools"><a className="button-link" href={`#page=preview&course_id=${courseId}&run_id=${run.id}`}>{tr("Посмотреть глазами ученика")}</a><CourseTools courseId={courseId} title={preview?.course || tr("Курс")} displayTitle={ct(preview, 'course') || tr("Курс")} runId={run.id} canEdit={canEdit} /></div>}
    {error && <p role="alert" className="error">{tr(error)}</p>}{message && <p role="status" className="success">{tr(message)}</p>}
    {!preview && !error && <p>{tr("Загрузка курса…")}</p>}
    {preview && run && (full ? <>
      <div className="course-workspace"><aside className={`course-rail ${mobileRailOpen ? 'is-open' : ''}`} aria-label={tr('Навигация по курсу')}>
        <button className="course-rail-toggle secondary" type="button" aria-expanded={mobileRailOpen} onClick={() => setMobileRailOpen(value => !value)}>{tr('Программа и разделы курса')} <span aria-hidden="true">{mobileRailOpen ? '−' : '+'}</span></button><div className="course-rail-body">
        <p className="course-rail-caption">{manage ? tr('Работа с курсом') : tr('Моё обучение')}</p>
        <nav className="course-navigation" aria-label={tr('Разделы курса')}>
          {tabs.filter(([id]) => ['plan', 'overview', 'lessons'].includes(id)).map(([id, label]) => <button key={id} aria-current={tab === id ? 'page' : undefined} onClick={() => changeTab(id)}>{ct(label)}</button>)}
          <details className="course-section-menu" open={!['plan', 'overview', 'lessons'].includes(tab)}><summary>{manage ? tr('Управление курсом') : tr('Результаты и общение')}</summary>
            {tabs.filter(([id]) => !['plan', 'overview', 'lessons'].includes(id) && (id !== 'groups' || manage) && (id !== 'publication' || canEdit) && (manage || !['assignments', 'quizzes'].includes(id))).map(([id, label]) => <button key={id} aria-current={tab === id ? 'page' : undefined} onClick={() => changeTab(id)}>{id === 'results' ? manage ? tr('Ученики и ответы') : tr('Мои результаты') : ct(label)}</button>)}
          </details>
        </nav><div ref={setOutlineHost} className="course-outline-host" /></div>
      </aside><section className="course-main" aria-label={tr('Материалы курса')}>
      {canEdit && tab !== 'publication' && <CourseReadiness courseId={courseId} runId={run.id} revision={revision} compact onChanged={() => setRevision(v => v + 1)} onDetails={() => changeTab('publication')} onEditIssue={editIssue} />}
      {tab === 'plan' && <LearningPlan key={`${run.id}-${run.starts_at || ''}`} courseId={courseId} runId={run.id} canEditQuiz={canEdit} onSaved={() => setRevision(v => v + 1)} />}
      {tab === 'overview' && <section className="course-overview"><p className="eyebrow">{tr('О курсе')}</p><h2>{ct(preview, 'course')}</h2><RichLessonContent content={ct(preview, 'description') || tr('Описание курса пока не добавлено.')} runId={run.id} /><div className="action-row"><button onClick={() => changeTab('lessons')}>{manage ? tr('Открыть редактор курса') : tr('Перейти к обучению')}</button>{canEdit && <button className="secondary" onClick={() => changeTab('publication')}>{tr('Проверить доступ ученика')}</button>}</div></section>}
      {tab === 'publication' && canEdit && <CourseReadiness courseId={courseId} runId={run.id} revision={revision} onChanged={() => setRevision(v => v + 1)} onDetails={() => changeTab('publication')} onEditIssue={editIssue} />}
      {tab === 'lessons' && <Curriculum key={`${run.id}-${revision}`} courseId={courseId} runId={run.id} courseTitle={ct(preview, 'course')} navigationHost={outlineHost} onNavigate={() => setMobileRailOpen(false)} />}
      {['assignments', 'quizzes', 'results'].includes(tab) && <StudyPanel key={`${tab}-${run.id}`} courseId={courseId} runId={run.id} tab={tab as 'assignments' | 'quizzes' | 'results'} />}
      {tab === 'announcements' && <Announcements key={run.id} courseId={courseId} runId={run.id} manage={manage} canEdit={canEdit} />}
      {tab === 'messages' && <Conversations key={run.id} courseId={courseId} runId={run.id} manage={manage} />}
      {tab === 'groups' && manage && <GroupSettings key={run.id} courseId={courseId} run={run} canEdit={canEdit} refresh={() => setRevision(v => v + 1)} />}
      {tab === 'settings' && <section className="study-section">{canEdit && <article className="study-card"><h3>{tr("Публикация курса")}</h3><p className="muted">{preview.is_published ? tr("Курс опубликован и доступен для записи.") : tr("Курс находится в черновике.")} </p><button className="secondary" disabled={busy} onClick={publish}>{preview.is_published ? tr("Снять курс с публикации") : tr("Опубликовать курс")}</button></article>}{preview.is_published && user && <article className="study-card"><h3>{tr("Мои списки")}</h3><div className="action-row"><button className="secondary" onClick={() => bookmark('favorite')}>{tr("В избранное")}</button><button className="secondary" onClick={() => bookmark('wishlist')}>{tr("Хочу пройти")}</button></div></article>}<NotificationSettings key={run.id} courseId={courseId} runId={run.id} /></section>}
      </section></div>
    </> : <div className="study-card"><section className="course-overview"><p className="eyebrow">{tr('О курсе')}</p><h2>{ct(preview, 'course')}</h2><RichLessonContent content={ct(preview, 'description') || tr('Описание курса пока не добавлено.')} runId={run.id} /></section><h3>{tr("Программа курса")}</h3>{preview.lessons.map(l => <p key={l.id}>{ct(l, "title")}</p>)}<div className="action-row"><button disabled={busy} onClick={enroll}>{tr("Записаться на курс")}</button><button className="secondary" onClick={() => bookmark('favorite')}>{tr("В избранное")}</button><button className="secondary" onClick={() => bookmark('wishlist')}>{tr("Хочу пройти")}</button></div></div>)}
  </div>
}
