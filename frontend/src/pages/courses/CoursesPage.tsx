import CourseLanguageBadge from '../../components/CourseLanguageBadge'
import CourseCover from '../../components/CourseCover'
import CourseSummary from '../../components/CourseSummary'
import { ct } from '../../i18n/content'
import { readApiJson } from '../../i18n/contentStore'
import { t as tr, countLabel } from '../../i18n/language'
import RoleBadge from '../../components/RoleBadge'
import LessonPage from './LessonPage'
import { useEffect, useState } from 'react'
import { enrollRequest, type User } from '../../api'
import './CoursesPage.css'

type Course = {
  id: number
  title: string
  description: string
  teacher: string | null
  teacher_id: number | null
  teacher_role_label: string
  is_published: boolean
  is_enrolled: boolean
  can_manage: boolean
  lessons_count: number
}

type Props = {
  user: User | null
  openCourseId: number | null
  onOpenCourse: (id: number | null) => void
  onNeedAuth: (courseId: number) => void
}

function CoursesPage({ user, openCourseId, onOpenCourse, onNeedAuth }: Props) {
  const [courses, setCourses] = useState<Course[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [enrollingId, setEnrollingId] = useState<number | null>(null)

  useEffect(() => {
    let active = true

    async function loadCourses() {
      setLoading(true)
      try {
        const response = await fetch('/api/courses/', {
          credentials: 'include',
        })

        if (!response.ok) {
          throw new Error(tr("Ошибка загрузки курсов"))
        }

        const data = await readApiJson(response)

        if (active) {
          setCourses(data.courses)
        }
      } catch (err) {
        if (active) {
          setError(
            err instanceof Error ? err.message : 'Ошибка'
          )
        }
      } finally {
        if (active) setLoading(false)
      }
    }

    loadCourses()

    return () => {
      active = false
    }
  }, [user, openCourseId])

  async function handleEnroll(course: Course) {
    if (!user) {
      onNeedAuth(course.id)
      return
    }

    setEnrollingId(course.id)
    setError('')

    try {
      await enrollRequest(course.id)
      setCourses(current =>
        current.map(item =>
          item.id === course.id ? { ...item, is_enrolled: true } : item
        )
      )
      onOpenCourse(course.id)
    } catch (err) {
      const authRequired = Boolean(
        err && typeof err === 'object' && 'authRequired' in err
      )
      if (authRequired) {
        onNeedAuth(course.id)
        return
      }
      setError(err instanceof Error ? err.message : 'Не удалось записаться')
    } finally {
      setEnrollingId(null)
    }
  }

  if (openCourseId !== null) {
    return (
      <LessonPage
        key={`${openCourseId}-${user?.username ?? 'guest'}`}
        courseId={openCourseId}
        user={user}
        onBack={() => onOpenCourse(null)}
        onNeedAuth={onNeedAuth}
        onEnrolled={() => {
          setCourses(current =>
            current.map(item =>
              item.id === openCourseId ? { ...item, is_enrolled: true } : item
            )
          )
        }}
      />
    )
  }

  return (
    <div className="courses-page">
      <div className="courses-header">
        <h2>{tr("Каталог курсов")}</h2>
        
      </div>

      <div className="courses-summary">
        <div className="card">
          <h3>{courses.length}</h3>
          <p>{tr("Курсы в каталоге")}</p>
        </div>

        <div className="card">
          <h3>{courses.filter(c => c.is_enrolled || c.can_manage).length}</h3>
          <p>{tr("Доступны полностью")}</p>
        </div>
      </div>

      {loading && <p>{tr("Загрузка курсов...")}</p>}

      {error && <p className="courses-error">{tr(error)}</p>}

      {!loading && !error && courses.length === 0 && (
        <div className="card">
          <h3>{tr("Курсов пока нет")}</h3>
          <p>{tr("Опубликованные курсы появятся здесь.")}</p>
        </div>
      )}

      {!loading && courses.length > 0 && (
        <div className="courses-grid">
          {courses.map(course => (
            <article className="course-card" key={course.id}>
              <CourseCover courseId={course.id} title={ct(course, 'title')} />

              <div className="course-info">
                <span className="course-category">
                  {countLabel(course.lessons_count, "lesson")}</span>

                <h3>{ct(course, "title")}</h3><CourseLanguageBadge course={course} />

                <CourseSummary course={course} courseId={course.id} showLink={false} />

                <div className="course-teacher">
                  {user && course.teacher_id ? <a href={`#profile=${course.teacher_id}`}>{course.teacher}</a> : course.teacher || tr("Не назначен")}{course.teacher && <RoleBadge label={tr(course.teacher_role_label)} />}
                </div>

                <div className="course-footer">
                  <span
                    className={
                      course.is_published
                        ? 'course-published'
                        : 'course-draft'
                    }
                  >
                    {course.is_published ? tr("Открыт") : tr("Черновик")}
                  </span>
                  {course.is_enrolled && (
                    <span className="course-enrolled">{tr("Вы записаны")}</span>
                  )}
                </div>

                <div className="course-actions">
                  <a
                    className="course-open-btn"
                    href={`#course=${course.id}&tab=overview`}
                  >
                    {tr('О курсе')}</a>

                  {course.can_manage || course.is_enrolled ? (
                    <button
                      className="course-open-btn course-open-btn-primary"
                      onClick={() => onOpenCourse(course.id)}
                    >
                      {tr("Открыть курс")}</button>
                  ) : (
                    <button
                      className="course-open-btn course-open-btn-primary"
                      disabled={enrollingId === course.id}
                      onClick={() => handleEnroll(course)}
                    >
                      {enrollingId === course.id
                        ? tr("Запись...")
                        : tr("Записаться на курс")}
                    </button>
                  )}
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  )
}

export default CoursesPage
