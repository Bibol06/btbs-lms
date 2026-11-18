import { ct } from '../../i18n/content'
import { auditCaption } from '../../i18n/captions'
import { t as tr, getLocale } from '../../i18n/language'
import RoleBadge from '../../components/RoleBadge'
import { useEffect, useState, type FormEvent } from 'react'
import { apiRequest } from '../../api'
import { errorMessage, inputDate, isoDate } from '../study/types'
import ConfirmAction from '../study/ConfirmAction'

export type Run = { id: number; title: string; kind: string; starts_at: string | null; ends_at: string | null; is_open: boolean; can_manage: boolean; join_code: string; enrollment_id: number | null; enrollment_status: string | null; teachers: { id: number; username: string; display_name: string; role_label: string }[] }

export function NotificationSettings({ courseId, runId }: { courseId: number; runId: number }) {
  const [muted, setMuted] = useState<string[]>([])
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  useEffect(() => {
    let alive = true
    apiRequest<{ muted_kinds: string[] }>(`/api/communication/courses/${courseId}/preferences/?run_id=${runId}`).then(data => { if (alive) setMuted(data.muted_kinds) }).catch(err => { if (alive) setError(errorMessage(err)) })
    return () => { alive = false }
  }, [courseId, runId])
  async function save(e: FormEvent) {
    e.preventDefault()
    try { await apiRequest(`/api/communication/courses/${courseId}/preferences/?run_id=${runId}`, 'PUT', { muted_kinds: muted }); setMessage('Настройки уведомлений сохранены') }
    catch (err) { setError(errorMessage(err)) }
  }
  return <form className="study-form" onSubmit={save}><h3>{tr("Уведомления этого курса")}</h3>
    {[['announcement', tr("Объявления")], ['message', tr("Личные сообщения")], ['discussion', tr("Ответы в обсуждениях")], ['submission', tr("Новые работы на проверку")], ['grade', tr("Оценки и доработка")], ['material', tr("Новые материалы")], ['deadline', tr("Приближение срока")]].map(([kind, label]) => <label className="check" key={kind}><input type="checkbox" checked={!muted.includes(kind)} onChange={e => setMuted(current => e.target.checked ? current.filter(v => v !== kind) : [...current, kind])} />{ct(label)}</label>)}
    {error && <p role="alert" className="error">{tr(error)}</p>}{message && <p role="status" className="success">{tr(message)}</p>}<button>{tr("Сохранить уведомления")}</button>
  </form>
}

export default function GroupSettings({ courseId, run, canEdit, refresh }: { courseId: number; run: Run; canEdit: boolean; refresh: () => void }) {
  const [students, setStudents] = useState<{ id: number; student__username: string; student: string; role_label: string; status: string }[]>([])
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [revision, setRevision] = useState(0)
  const [audit, setAudit] = useState<{ action: string; actor__username: string; actor: string; actor_role_label: string; created_at: string }[]>([])
  useEffect(() => {
    let alive = true
    apiRequest<{ students: typeof students }>(`/api/courses/runs/${run.id}/`).then(data => { if (alive) setStudents(data.students) }).catch(err => { if (alive) setError(errorMessage(err)) })
    if (canEdit) apiRequest<{ events: typeof audit }>(`/api/communication/courses/${courseId}/audit/`).then(data => { if (alive) setAudit(data.events) }).catch(() => {})
    return () => { alive = false }
  }, [run.id, courseId, canEdit, revision])
  async function perform(e: FormEvent<HTMLFormElement>, action: string) {
    e.preventDefault(); const element = e.currentTarget; const data = new FormData(element)
    setError(''); setMessage('')
    try {
      if (action === 'create') await apiRequest(`/api/courses/${courseId}/runs/`, 'POST', { title: data.get('title'), starts_at: isoDate(data.get('starts_at')), ends_at: isoDate(data.get('ends_at')) })
      if (action === 'edit') await apiRequest(`/api/courses/runs/${run.id}/`, 'PATCH', { title: data.get('title'), starts_at: isoDate(data.get('starts_at')), ends_at: isoDate(data.get('ends_at')), is_open: data.has('is_open') })
      if (action === 'invite') await apiRequest(`/api/courses/runs/${run.id}/students/`, 'POST', { username: data.get('username') })
      if (action === 'teacher') await apiRequest(`/api/courses/${courseId}/team/`, 'POST', { username: data.get('username'), run_id: data.get('scope') === 'run' ? run.id : undefined })
      setMessage('Изменения сохранены'); setRevision(v => v + 1); refresh()
    } catch (err) { setError(errorMessage(err)) }
  }
  async function setStudentStatus(id: number, status: string) {
    try { await apiRequest(`/api/courses/enrollments/${id}/`, 'PATCH', { status }); setRevision(v => v + 1) }
    catch (err) { setError(errorMessage(err)) }
  }
  return <section className="study-section"><h2>{tr("Управление группами")}</h2>
    {error && <p role="alert" className="error">{tr(error)}</p>}{message && <p role="status" className="success">{tr(message)}</p>}
    {/* The plan has its own tab; repeating its editor here made this page twice as long (QA-016). */}
    <p className="muted"><a href={`#course=${courseId}&run=${run.id}&tab=plan`}>{tr("Сроки модулей и контрольные тесты группы — во вкладке «Учебный план» →")}</a></p>
    <form className="study-form" key={`run-${run.id}-${run.starts_at || ''}`} onSubmit={e => perform(e, 'edit')}><h3>{tr("Текущий запуск: ")}{ct(run, "title")}</h3>
      <label>{tr("Название запуска")}<input name="title" defaultValue={run.title} maxLength={200} required /></label>
      <div className="form-grid"><label>{tr("Начало обучения")}<input type="datetime-local" name="starts_at" defaultValue={inputDate(run.starts_at)} /></label><label>{tr("Окончание обучения")}<input type="datetime-local" name="ends_at" defaultValue={inputDate(run.ends_at)} /></label></div>
      <label className="check"><input type="checkbox" name="is_open" defaultChecked={run.is_open} /> {tr(" Разрешить запись по приглашению / в самостоятельный курс")}</label><button>{tr("Сохранить запуск")}</button>
      {run.join_code && <p>{tr("Код приглашения для студентов: ")}<code className="invitation-code">{run.join_code}</code></p>}
    </form>
    <div className="study-card"><h3>{tr("Преподаватели группы")}</h3>{run.teachers.map(teacher => <p key={teacher.id}><a href={`#profile=${teacher.id}`}>{teacher.display_name}</a><RoleBadge label={tr(teacher.role_label)} /></p>)}{!run.teachers.length && <p className="muted">{tr("Группу ведёт основная команда курса.")}</p>}</div>
    <div className="study-card"><h3>{tr("Студенты этого запуска")}</h3>{students.map(s => <div className="action-row" key={s.id}><span>{s.student}<RoleBadge label={tr(s.role_label)} /> · {s.status === 'completed' ? tr("Завершено") : s.status === 'archived' ? tr("В архиве") : s.status === 'removed' ? tr("Доступ отозван") : tr("Учится")}</span>{s.status === 'removed' ? <button className="secondary" onClick={() => setStudentStatus(s.id, 'active')}>{tr("Восстановить доступ")}</button> : <ConfirmAction label={tr("Отозвать доступ")} question={tr("Закрыть студенту доступ к этому запуску? Его результаты сохранятся.")} onConfirm={() => setStudentStatus(s.id, 'removed')} />}</div>)}{!students.length && <p>{tr("Студентов пока нет.")}</p>}
      <form className="study-form compact" onSubmit={e => perform(e, 'invite')}><label>{tr("Логин студента")}<input name="username" required maxLength={150} /></label><button className="secondary">{tr("Добавить студента в запуск")}</button></form>
    </div>
    {canEdit && <>
      <form className="study-form" onSubmit={e => perform(e, 'create')}><h3>{tr("Новая учебная группа")}</h3><label>{tr("Название группы")}<input name="title" required maxLength={200} /></label><div className="form-grid"><label>{tr("Начало")}<input type="datetime-local" name="starts_at" /></label><label>{tr("Окончание")}<input type="datetime-local" name="ends_at" /></label></div><button className="secondary">{tr("Создать группу")}</button></form>
      <form className="study-form" onSubmit={e => perform(e, 'teacher')}><h3>{tr("Назначить преподавателя")}</h3><label>{tr("Логин преподавателя")}<input name="username" required maxLength={150} /></label><label>{tr("Полномочия")}<select name="scope"><option value="run">{tr("Проверка и ведение только текущей группы")}</option><option value="course">{tr("Редактирование содержания всего курса")}</option></select></label><button className="secondary">{tr("Назначить")}</button></form>
      <details className="study-card"><summary>{tr("История изменений курса")}</summary>{audit.map((a, i) => <p key={i}>{a.actor}<RoleBadge label={tr(a.actor_role_label)} /> · {auditCaption(a.action)} · {new Date(a.created_at).toLocaleString(getLocale())}</p>)}</details>
    </>}
  </section>
}
