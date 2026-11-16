import { ct } from '../i18n/content'
import { t as tr, getLocale } from '../i18n/language'
import RoleBadge from '../components/RoleBadge'
import LanguageSwitcher from '../components/LanguageSwitcher'
import { useEffect, useState, type FormEvent } from 'react'
import { apiRequest } from '../api'
import { errorMessage } from './study/types'

type ProfileData = {
  id: number; username: string; display_name: string; first_name: string; last_name: string
  role: 'student' | 'teacher' | 'admin'; role_label: string; can_teach: boolean; bio: string; organization: string
  city: string; joined_at: string; is_own: boolean; email?: string
  teaching_courses: { id: number; title: string; is_published: boolean }[]
  learning?: { active: number; completed: number }
}

export default function Profile({ profileId, onSaved }: { profileId: string; onSaved: (name: string) => void }) {
  const [data, setData] = useState<ProfileData | null>(null)
  const [editing, setEditing] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    let alive = true
    apiRequest<ProfileData>(profileId === 'me' ? '/api/auth/profile/' : `/api/auth/profiles/${profileId}/`)
      .then(value => { if (alive) setData(value) }).catch(err => { if (alive) setError(errorMessage(err)) })
    return () => { alive = false }
  }, [profileId])
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError('')
    const form = new FormData(event.currentTarget)
    const fields = Object.fromEntries(['first_name', 'last_name', 'bio', 'organization', 'city'].map(name => [name, form.get(name)]))
    try {
      const next = await apiRequest<ProfileData>('/api/auth/profile/', 'PATCH', fields)
      setData(next); setEditing(false); setMessage('Профиль сохранён'); onSaved(next.display_name)
    } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }
  if (!data) return <p role="status">{error || tr("Загрузка профиля…")}</p>
  return <section className="profile-page study-section">
    <div className="profile-cover" />
    {data.is_own && <section className="study-card profile-language"><h3>{tr("Язык платформы")}</h3><LanguageSwitcher full /></section>}
    <div className="profile-heading"><span className="avatar avatar-large" aria-hidden="true">{data.display_name[0]?.toUpperCase()}</span><div><h2>{data.display_name} <RoleBadge label={tr(data.role_label)} /></h2><p className="muted">{tr("Логин для входа: @")}{data.username}</p></div>{data.is_own && <button className="secondary" onClick={() => { setEditing(v => !v); setMessage('') }}>{editing ? tr("Закрыть редактор") : tr("Редактировать профиль")}</button>}</div>
    {error && <p className="error" role="alert">{tr(error)}</p>}{message && <p className="success" role="status">{tr(message)}</p>}
    {editing ? <form className="study-form" onSubmit={save}>
      <div className="form-grid"><label>{tr("Имя")}<input name="first_name" maxLength={150} defaultValue={data.first_name} autoComplete="given-name" /></label><label>{tr("Фамилия")}<input name="last_name" maxLength={150} defaultValue={data.last_name} autoComplete="family-name" /></label></div>
      <label>{tr("О себе")}<textarea name="bio" rows={4} maxLength={3000} defaultValue={data.bio} placeholder={tr("Расскажите о себе, своих интересах или опыте преподавания")} /></label>
      <div className="form-grid"><label>{tr("Учебное заведение / организация")}<input name="organization" maxLength={200} defaultValue={data.organization} /></label><label>{tr("Город")}<input name="city" maxLength={100} defaultValue={data.city} /></label></div>
      
      <button disabled={busy}>{busy ? tr("Сохранение…") : tr("Сохранить изменения")}</button>
    </form> : <div className="profile-grid"><article className="study-card"><h3>{tr("О себе")}</h3><p className="preserve-text">{ct(data, "bio") || tr("Пока нет описания.")}</p>{data.organization && <p>{ct(data, "organization")}</p>}{data.city && <p>{ct(data, "city")}</p>}<p className="muted">{tr("На платформе с ")}{new Date(data.joined_at).toLocaleDateString(getLocale())}</p>{data.email && <p className="muted">{tr("Email:")} {data.email} {tr(" · виден только вам")}</p>}</article>
      {data.learning && !data.can_teach && data.role === 'student' && <article className="study-card"><h3>{tr("Моё обучение")}</h3><div className="profile-metrics"><div><strong>{data.learning.active}</strong><span>{tr("В процессе")}</span></div><div><strong>{data.learning.completed}</strong><span>{tr("Завершено")}</span></div></div><a href="#page=learning">{tr("Перейти к моим курсам →")}</a></article>}
      {data.is_own && (data.can_teach || data.role === 'admin') && <article className="study-card"><h3>{data.role === 'admin' ? tr("Управление платформой") : tr("Моя работа преподавателем")}</h3><p><a href={data.role === 'admin' ? '#page=admin' : '#page=teaching'}>{tr("Перейти в рабочий кабинет →")}</a></p>{data.learning && data.learning.active + data.learning.completed > 0 && <details><summary>{tr("Я также учусь на курсах")}</summary><a href="#page=learning&mode=personal">{tr("Открыть моё личное обучение →")}</a><p><a href="#page=deadlines&mode=personal">{tr("Мои личные задания и сроки →")}</a></p></details>}</article>}</div>}
    {(data.can_teach || data.teaching_courses.length > 0) && <section><h3>{tr("Преподавание")}</h3>{data.teaching_courses.length ? <div className="profile-grid">{data.teaching_courses.map(c => <article className="study-card" key={c.id}><h3>{ct(c, "title")}</h3><p className="muted">{c.is_published ? tr("Опубликованный курс") : tr("Черновик")}</p><a href={`#course=${c.id}`}>{tr("Открыть курс →")}</a></article>)}</div> : <p className="empty-state">{tr("Опубликованных курсов пока нет.")}</p>}</section>}
  </section>
}
