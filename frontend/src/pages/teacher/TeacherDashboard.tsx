import { ct } from '../../i18n/content'
import { t as tr, getLanguage, countLabel } from '../../i18n/language'
import CourseLanguageBadge from '../../components/CourseLanguageBadge'
import CourseCover from '../../components/CourseCover'
import CourseSummary from '../../components/CourseSummary'
import LessonContentEditor from '../../components/LessonContentEditor'
import WorkspaceHome from '../workspace/WorkspaceHome'
import { CourseTools } from '../workspace/AuthorTools'
import { useEffect, useState, type FormEvent } from 'react'
import { apiRequest } from '../../api'
import { errorMessage } from '../study/types'
import '../study/Study.css'
import './TeacherDashboard.css'
import '../management/Management.css'
import '../study/Deadlines.css'

type Course = { id: number; title: string; description: string; teacher: string | null; is_published: boolean; lessons_count: number; can_edit_content: boolean; content_language?: string; content_translation?: string }

export function CourseForm({ initial, onSaved, onCancel }: { initial?: Pick<Course, 'id' | 'title' | 'description'>; onSaved: () => void; onCancel: () => void }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [contentLanguage, setContentLanguage] = useState<string>(getLanguage)
  const [translationMode, setTranslationMode] = useState('original')
  const [settingsReady, setSettingsReady] = useState(!initial)
  const [description, setDescription] = useState(initial?.description ?? '')
  const [uploadingImage, setUploadingImage] = useState(false)
  useEffect(() => {
    if (!initial) return
    let active = true
    apiRequest<{ course: Course }>(`/api/courses/teacher/${initial.id}/`).then(data => {
      if (active) { setContentLanguage(data.course.content_language || 'ru'); setTranslationMode(data.course.content_translation || 'original'); setSettingsReady(true) }
    }).catch(err => { if (active) setError(errorMessage(err)) })
    return () => { active = false }
  }, [initial])
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (uploadingImage) return
    const data = new FormData(event.currentTarget)
    setBusy(true); setError('')
    try {
      await apiRequest(initial ? `/api/courses/teacher/${initial.id}/` : '/api/courses/teacher/', initial ? 'PATCH' : 'POST', {
        title: data.get('title'), description,
        content_language: contentLanguage, content_translation: translationMode,
      })
      onSaved()
    } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }
  return <form className="study-form" onSubmit={save}>
    <h3>{initial ? tr("Редактирование курса") : tr("Новый курс")}</h3>
    <label>{tr("Название курса")}<input name="title" maxLength={200} defaultValue={initial?.title} required /></label>
    <LessonContentEditor scope="course" courseId={initial?.id} name="description" label={tr('Описание курса')} value={description} onChange={setDescription} onUploadingChange={setUploadingImage} maxLength={10000} rows={10} />
    <fieldset className="course-language-settings"><legend>{tr('Язык обучения')}</legend><div className="form-grid">
      <label>{tr('Язык материалов курса')}<select aria-label={tr('Язык материалов курса')} value={contentLanguage} onChange={e => setContentLanguage(e.target.value)}><option value="ru" lang="ru" translate="no">Русский</option><option value="kk" lang="kk" translate="no">Қазақша</option><option value="en" lang="en" translate="no">English</option><option value="other">{tr('Другой язык')}</option></select></label>
      <label>{tr('Режим перевода курса')}<select aria-label={tr('Режим перевода курса')} value={translationMode} onChange={e => setTranslationMode(e.target.value)}><option value="original">{tr('Сохранять язык курса')}</option><option value="localized">{tr('Использовать подготовленные переводы')}</option></select></label>
    </div></fieldset>
    {error && <p role="alert" className="error">{tr(error)}</p>}
    <div className="action-row"><button disabled={busy || uploadingImage || !settingsReady}>{tr("Сохранить курс")}</button><button type="button" disabled={busy || uploadingImage} className="secondary" onClick={onCancel}>{tr("Отмена")}</button></div>
  </form>
}

export default function TeacherDashboard() {
  const [courses, setCourses] = useState<Course[]>([])
  const [revision, setRevision] = useState(0)
  const [loading, setLoading] = useState(true)
  const [editor, setEditor] = useState<Course | 'new' | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState<number | null>(null)
  useEffect(() => {
    let alive = true
    apiRequest<{ courses: Course[] }>('/api/courses/teacher/')
      .then(data => { if (alive) { setCourses(data.courses); setError('') } })
      .catch(err => { if (alive) setError(errorMessage(err)) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [revision])
  function refresh() { setRevision(v => v + 1) }
  async function publish(course: Course) {
    setBusy(course.id); setError('')
    try {
      if (course.is_published) await apiRequest(`/api/courses/teacher/${course.id}/`, 'PATCH', { is_published: false })
      else await apiRequest(`/api/courses/${course.id}/publish/`, 'POST', { scope: 'course', include_descendants: true })
      refresh()
    } catch (err) { setError(errorMessage(err)) } finally { setBusy(null) }
  }
  return <div className="teacher-dashboard">
    <div className="section-heading"><div><h2>{tr("Мои курсы и группы")}</h2></div><button onClick={() => setEditor('new')}>{tr("+ Создать курс")}</button></div>
    {error && <p role="alert" className="error">{tr(error)}</p>}
    <WorkspaceHome />
    {editor && <CourseForm key={editor === 'new' ? 'new' : editor.id} initial={editor === 'new' ? undefined : editor} onSaved={() => { setEditor(null); refresh() }} onCancel={() => setEditor(null)} />}
    <div className="teacher-stats teacher-stats-compact"><div className="card"><h3>{courses.length}</h3><p>{tr("Всего курсов")}</p></div><div className="card"><h3>{courses.filter(c => c.is_published).length}</h3><p>{tr("Опубликованы")}</p></div><div className="card"><h3>{courses.filter(c => !c.is_published).length}</h3><p>{tr("Черновики")}</p></div></div>
    {loading && <p>{tr("Загрузка курсов…")}</p>}
    {!loading && !courses.length && <p className="empty-state">{tr("Создайте первый курс и добавьте уроки.")}</p>}
    <div className="teacher-courses">{courses.map(course => <article className="study-card teacher-course-item" key={course.id}>
      <CourseCover courseId={course.id} title={ct(course, 'title')} compact />
      <div className="teacher-course-body"><h3>{ct(course, "title")}</h3><CourseLanguageBadge course={course} /><CourseSummary course={course} courseId={course.id} /><p>{countLabel(course.lessons_count, "lesson")} · <span className="badge">{course.is_published ? tr("Опубликован") : tr("Черновик")}</span></p>
      <div className="action-row"><button onClick={() => { window.location.hash = `course=${course.id}` }}>{tr("Открыть курс")}</button><CourseTools courseId={course.id} title={course.title} displayTitle={ct(course, "title")} canEdit={course.can_edit_content} onEdit={() => setEditor(course)} onPublish={() => publish(course)} published={course.is_published} busy={busy === course.id} /><a className="button-link" href={`#course=${course.id}&tab=results`}>{tr("Ученики и ответы →")}</a></div>
      </div>
    </article>)}</div>
  </div>
}
