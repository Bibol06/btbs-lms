import CourseCover from '../../components/CourseCover'
import { ct } from '../../i18n/content'
import { readApiJson } from '../../i18n/contentStore'
import { t as tr, countLabel, getLocale } from '../../i18n/language'
import LessonPage from './LessonPage'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { User } from '../../api'
import './CoursesPage.css'

type Course = {
  id: number
  title: string
  description: string
  content_language?: string
  teacher: string | null
  is_published: boolean
  is_enrolled: boolean
  can_manage: boolean
  lessons_count: number
  progress?: number
  progress_run_id?: number
}

type Props = {
  user: User | null
  openCourseId: number | null
  onOpenCourse: (id: number | null) => void
  onNeedAuth: (courseId: number) => void
}

type Show = 'all' | 'mine' | 'open'
type Sort = 'new' | 'title'
type Filters = { q: string; show: Show; lang: string; sort: Sort }

const LANGUAGE_NAMES: Record<string, string> = { ru: 'Русский', kk: 'Қазақша', en: 'English' }
const DEFAULTS: Filters = { q: '', show: 'all', lang: '', sort: 'new' }

/** Catalog filters live in the hash, so a filtered catalog can be shared as a link. */
const STORAGE_KEY = 'lms-catalog-filters'

function readFilters(): Filters {
  let route = new URLSearchParams(location.hash.slice(1))
  if (!['q', 'show', 'lang', 'sort'].some(key => route.has(key))) {
    // Coming back from a course resets the hash; restore this tab's last filters.
    try { route = new URLSearchParams(sessionStorage.getItem(STORAGE_KEY) ?? '') } catch { /* storage blocked */ }
  }
  const show = route.get('show')
  return {
    q: route.get('q') ?? '',
    show: show === 'mine' || show === 'open' ? show : 'all',
    lang: route.get('lang') ?? '',
    sort: route.get('sort') === 'title' ? 'title' : 'new',
  }
}

function writeFilters(filters: Filters) {
  const route = new URLSearchParams(location.hash.slice(1))
  for (const key of ['q', 'show', 'lang', 'sort'] as const) {
    const value = filters[key].trim()
    if (value && value !== DEFAULTS[key]) route.set(key, value)
    else route.delete(key)
  }
  const saved = new URLSearchParams()
  for (const key of ['q', 'show', 'lang', 'sort'] as const) if (route.has(key)) saved.set(key, route.get(key) ?? '')
  try { sessionStorage.setItem(STORAGE_KEY, saved.toString()) } catch { /* storage blocked */ }
  if (!route.toString()) route.set('page', 'catalog')
  // replaceState does not fire hashchange, so the page keeps focus and is not remounted.
  window.history.replaceState(null, '', `#${route.toString()}`)
}

function teacherOnly(user: User | null) {
  return user?.role === 'teacher' || user?.role === 'admin'
}

function CourseCard({ course, showLanguage }: { course: Course; showLanguage: boolean }) {
  const title = ct(course, 'title')
  const learning = course.is_enrolled && !course.can_manage
  const href = learning && course.progress_run_id ? `#course=${course.id}&run=${course.progress_run_id}` : learning || course.can_manage ? `#course=${course.id}` : `#course=${course.id}&tab=overview`
  const meta = [countLabel(course.lessons_count, 'lesson')]
  if (showLanguage && course.content_language) meta.push(LANGUAGE_NAMES[course.content_language] ?? tr('Другой язык'))
  // Unknown progress (e.g. right after enrolling) shows no bar rather than a wrong "not started".
  const known = typeof course.progress === 'number'
  const progress = Math.max(0, Math.min(100, course.progress ?? 0))
  const progressText = progress === 0 ? tr('Не начат') : progress === 100 ? tr('Пройден') : `${progress}%`
  return <li className="catalog-card">
    <div className="catalog-card-body">
      <h3 className="catalog-card-title"><a href={href} title={title}>{title}</a></h3>
      {course.teacher && <p className="catalog-card-teacher" title={course.teacher}>{course.teacher}</p>}
      <p className="catalog-card-meta">{meta.join(' · ')}</p>
      {learning && known && <div className="catalog-card-progress">
        <span className="catalog-card-bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress} aria-valuetext={progressText} aria-label={tr('Прогресс по курсу')}><span style={{ width: `${progress}%` }} /></span>
        <span className="catalog-card-percent" aria-hidden="true">{progressText}</span>
      </div>}
      {learning && <span className="catalog-card-cta" aria-hidden="true">{known && progress === 0 ? tr('Начать') : tr('Продолжить')} →</span>}
    </div>
    <div className="catalog-card-cover">
      <CourseCover courseId={course.id} title={title} />
      {!course.is_published && <span className="catalog-card-badge">{tr('Черновик')}</span>}
    </div>
  </li>
}

function CoursesPage({ user, openCourseId, onOpenCourse, onNeedAuth }: Props) {
  const [courses, setCourses] = useState<Course[]>([])
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const [filters, setFilters] = useState<Filters>(readFilters)
  const search = useRef<HTMLInputElement>(null)

  useEffect(() => {
    let active = true
    async function loadCourses() {
      setLoading(true)
      setFailed(false)
      try {
        const response = await fetch('/api/courses/', { credentials: 'include' })
        if (!response.ok) throw new Error(String(response.status))
        const data = await readApiJson(response)
        if (active) setCourses(data.courses)
      } catch {
        if (active) setFailed(true)
      } finally {
        if (active) setLoading(false)
      }
    }
    loadCourses()
    return () => { active = false }
  }, [user, openCourseId, attempt])

  function update(change: Partial<Filters>) {
    const next = { ...filters, ...change }
    setFilters(next)
    writeFilters(next)
  }

  function reset() {
    update({ q: '', show: 'all', lang: '' })
    // The reset button disappears with the filters; keep keyboard focus in the toolbar.
    search.current?.focus()
  }

  const languages = useMemo(() => [...new Set(courses.map(c => c.content_language).filter((code): code is string => Boolean(code)))], [courses])
  // Links can carry values that do not apply here (a guest with show=mine, a language no course uses).
  const show = user ? filters.show : 'all'
  const lang = languages.includes(filters.lang) ? filters.lang : ''
  const visible = useMemo(() => {
    const query = filters.q.trim().toLocaleLowerCase()
    const rows = courses.filter(course => {
      const mine = course.is_enrolled || course.can_manage
      if (show === 'mine' && !mine) return false
      if (show === 'open' && mine) return false
      if (lang && course.content_language !== lang) return false
      if (!query) return true
      return [ct(course, 'title'), ct(course, 'description'), course.teacher ?? ''].some(text => text.toLocaleLowerCase().includes(query))
    })
    if (filters.sort === 'title') {
      const locale = getLocale()
      rows.sort((a, b) => ct(a, 'title').localeCompare(ct(b, 'title'), locale))
    }
    return rows
  }, [courses, filters.q, filters.sort, show, lang])

  if (openCourseId !== null) {
    return (
      <LessonPage
        key={`${openCourseId}-${user?.username ?? 'guest'}`}
        courseId={openCourseId}
        user={user}
        onBack={() => onOpenCourse(null)}
        onNeedAuth={onNeedAuth}
        onEnrolled={() => setCourses(current => current.map(item => item.id === openCourseId ? { ...item, is_enrolled: true } : item))}
      />
    )
  }

  const filtered = filters.q.trim() !== '' || show !== 'all' || lang !== ''
  const showLanguage = languages.length > 1
  // A failed refetch keeps the list already on screen.
  const error = failed && !courses.length
  const ready = !loading && !error

  return (
    <section className="catalog-page" aria-labelledby="catalog-title">
      <header className="catalog-header">
        <h2 id="catalog-title">{tr('Каталог курсов')}</h2>
      </header>

      <div className="catalog-toolbar">
        <input
          type="search"
          className="catalog-search"
          ref={search}
          value={filters.q}
          placeholder={tr('Поиск по названию или преподавателю')}
          aria-label={tr('Поиск курсов')}
          onChange={event => update({ q: event.target.value })}
        />
        <div className="catalog-filters">
          {user && <div className="catalog-segment" role="group" aria-label={tr('Какие курсы показать')}>
            {([['all', 'Все'], ['mine', 'Мои курсы'], ['open', 'Можно записаться']] as const).map(([value, label]) =>
              <button type="button" key={value} aria-pressed={show === value} onClick={() => update({ show: value })}>{tr(label)}</button>)}
          </div>}
          {showLanguage && <select className="catalog-select" aria-label={tr('Язык курса')} value={lang} onChange={event => update({ lang: event.target.value })}>
            <option value="">{tr('Все языки')}</option>
            {languages.map(code => <option key={code} value={code}>{LANGUAGE_NAMES[code] ?? tr('Другой язык')}</option>)}
          </select>}
          <select className="catalog-select" aria-label={tr('Сортировка')} value={filters.sort} onChange={event => update({ sort: event.target.value === 'title' ? 'title' : 'new' })}>
            <option value="new">{tr('Сначала новые')}</option>
            <option value="title">{tr('По названию')}</option>
          </select>
        </div>
      </div>

      <div className="catalog-status">
        <span aria-live="polite">{ready && courses.length > 0 ? tr('Найдено курсов: {0}', [visible.length]) : ''}</span>
        {ready && filtered && courses.length > 0 && <button type="button" className="catalog-reset" onClick={reset}>{tr('Сбросить фильтры')}</button>}
      </div>

      {loading && <>
        <p className="visually-hidden" role="status">{tr('Загрузка курсов...')}</p>
        <ul className="catalog-grid" aria-hidden="true">
          {Array.from({ length: 6 }, (_, index) => <li className="catalog-card catalog-skeleton" key={index}>
            <div className="catalog-card-body"><span /><span /><span /></div>
            <div className="catalog-card-cover" />
          </li>)}
        </ul>
      </>}

      {error && !loading && <div className="catalog-empty" role="alert">
        <h3>{tr('Ошибка загрузки курсов')}</h3>
        <p>{tr('Проверьте соединение и попробуйте ещё раз.')}</p>
        <button type="button" className="secondary" onClick={() => setAttempt(value => value + 1)}>{tr('Повторить')}</button>
      </div>}

      {ready && courses.length === 0 && <div className="catalog-empty">
        <h3>{tr('Курсов пока нет')}</h3>
        <p>{teacherOnly(user) ? tr('Создайте первый курс в кабинете преподавателя.') : tr('Опубликованные курсы появятся здесь.')}</p>
        {teacherOnly(user) && <a className="button-link" href={user?.role === 'admin' ? '#page=admin-courses' : '#page=teaching'}>{tr('Перейти к моим курсам')}</a>}
      </div>}

      {ready && courses.length > 0 && visible.length === 0 && <div className="catalog-empty">
        <h3>{tr('Ничего не найдено')}</h3>
        <p>{tr('Попробуйте изменить запрос или сбросить фильтры.')}</p>
        <button type="button" className="secondary" onClick={reset}>{tr('Сбросить фильтры')}</button>
      </div>}

      {ready && visible.length > 0 && <ul className="catalog-grid">
        {visible.map(course => <CourseCard key={course.id} course={course} showLanguage={showLanguage} />)}
      </ul>}
    </section>
  )
}

export default CoursesPage
