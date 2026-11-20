import { ct } from '../i18n/content'
import { t as tr, getLocale } from '../i18n/language'
import RoleBadge from '../components/RoleBadge'
import LanguageSwitcher from '../components/LanguageSwitcher'
import { useEffect, useState, type FormEvent } from 'react'
import { apiRequest } from '../api'
import { errorMessage } from './study/types'
import './Profile.css'

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
  if (!data) return <p role={error ? 'alert' : 'status'} className={error ? 'error' : 'muted'}>{error ? tr(error) : tr("Загрузка профиля…")}</p>
  const details = [ct(data, 'organization'), ct(data, 'city')].filter(Boolean)
  return <section className="page profile-page" aria-labelledby="profile-title">
    <header className="profile-head">
      <span className="avatar profile-avatar" aria-hidden="true">{data.display_name[0]?.toUpperCase()}</span>
      <div className="profile-identity">
        <h2 className="page-title" id="profile-title">{data.display_name}</h2>
        <p className="page-sub"><RoleBadge label={tr(data.role_label)} /><span>@{data.username}</span>{details.map(item => <span key={item}>{item}</span>)}</p>
      </div>
      {data.is_own && !editing && <button className="secondary" onClick={() => { setEditing(true); setMessage('') }}>{tr("Редактировать профиль")}</button>}
    </header>
    {error && <p className="error" role="alert">{tr(error)}</p>}{message && <p className="success" role="status">{tr(message)}</p>}
    {editing ? <form className="form card" onSubmit={save} aria-labelledby="profile-edit-title">
      <h3 className="card-title" id="profile-edit-title">{tr("Редактировать профиль")}</h3>
      <div className="form-row"><label>{tr("Имя")}<input name="first_name" maxLength={150} defaultValue={data.first_name} autoComplete="given-name" /></label><label>{tr("Фамилия")}<input name="last_name" maxLength={150} defaultValue={data.last_name} autoComplete="family-name" /></label></div>
      <label>{tr("О себе")}<textarea name="bio" rows={4} maxLength={3000} defaultValue={data.bio} placeholder={tr("Расскажите о себе, своих интересах или опыте преподавания")} /></label>
      <div className="form-row"><label>{tr("Учебное заведение / организация")}<input name="organization" maxLength={200} defaultValue={data.organization} /></label><label>{tr("Город")}<input name="city" maxLength={100} defaultValue={data.city} /></label></div>
      <div className="form-actions"><button type="button" className="secondary" disabled={busy} onClick={() => setEditing(false)}>{tr("Отмена")}</button><button disabled={busy}>{busy ? tr("Сохранение…") : tr("Сохранить изменения")}</button></div>
    </form> : <div className="profile-grid">
      <article className="card"><h3 className="card-title">{tr("О себе")}</h3><p className="preserve-text profile-bio">{ct(data, "bio") || tr("Пока нет описания.")}</p>
        <dl className="profile-facts"><div><dt>{tr("На платформе с ")}</dt><dd>{new Date(data.joined_at).toLocaleDateString(getLocale())}</dd></div>{data.email && <div><dt>{tr("Email:")}</dt><dd>{data.email} <span className="muted">{tr(" · виден только вам")}</span></dd></div>}</dl></article>
      {data.learning && !data.can_teach && data.role === 'student' && <article className="card"><h3 className="card-title">{tr("Моё обучение")}</h3><div className="profile-metrics"><div><strong>{data.learning.active}</strong><span>{tr("В процессе")}</span></div><div><strong>{data.learning.completed}</strong><span>{tr("Завершено")}</span></div></div><a href="#page=learning">{tr("Перейти к моим курсам →")}</a></article>}
      {data.is_own && (data.can_teach || data.role === 'admin') && <article className="card"><h3 className="card-title">{data.role === 'admin' ? tr("Управление платформой") : tr("Моя работа преподавателем")}</h3><p><a href={data.role === 'admin' ? '#page=admin' : '#page=teaching'}>{tr("Перейти в рабочий кабинет →")}</a></p>{data.learning && data.learning.active + data.learning.completed > 0 && <details><summary>{tr("Я также учусь на курсах")}</summary><a href="#page=learning&mode=personal">{tr("Открыть моё личное обучение →")}</a><p><a href="#page=deadlines&mode=personal">{tr("Мои личные задания и сроки →")}</a></p></details>}</article>}
      {data.is_own && <article className="card profile-language"><h3 className="card-title">{tr("Язык платформы")}</h3><LanguageSwitcher full /></article>}
    </div>}
    {(data.can_teach || data.teaching_courses.length > 0) && <section className="profile-teaching" aria-labelledby="profile-teaching-title"><h3 className="section-title" id="profile-teaching-title">{tr("Преподавание")}</h3>{data.teaching_courses.length ? <ul className="list">{data.teaching_courses.map(c => <li className="list-row" key={c.id}><div className="list-row-main"><p className="list-row-title"><a href={`#course=${c.id}`}>{ct(c, "title")}</a></p></div><span className={`badge ${c.is_published ? 'is-success' : 'is-warning'}`}>{c.is_published ? tr("Опубликованный курс") : tr("Черновик")}</span></li>)}</ul> : <div className="empty"><p>{tr("Опубликованных курсов пока нет.")}</p></div>}</section>}
  </section>
}
