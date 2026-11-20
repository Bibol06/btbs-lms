import { readApiJson } from '../../i18n/contentStore'
import { t as tr } from '../../i18n/language'
import RoleBadge from '../../components/RoleBadge'
import type { User as SessionUser } from '../../api'
import AdminResponsibilities from './AdminResponsibilities'

import { useEffect, useState, type FormEvent } from 'react'
import './UsersPage.css'
import MoreMenu from '../../components/MoreMenu'

type User = {
  id: number
  username: string
  display_name: string
  role_label: string
  email: string
  role: 'student' | 'teacher' | 'admin'
  is_active: boolean
  admin_scope?: string | null
}


function getCookie(name: string) {
  const cookie = document.cookie
    .split('; ')
    .find(item => item.startsWith(name + '='))

  return cookie
    ? decodeURIComponent(cookie.substring(name.length + 1))
    : ''
}

function UsersPage({ current }: { current?: SessionUser }) {
  const [users, setUsers] = useState<User[]>([])
  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState('')
  const [confirming, setConfirming] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [showForm, setShowForm] = useState(false)
  const [username, setUsername] = useState('')
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState('')
  const [message, setMessage] = useState('')
  const [deletingId, setDeletingId] = useState<number | null>(null)
    const [deleteError, setDeleteError] = useState('')

  useEffect(() => {
    let cancelled = false

    async function loadUsers() {
      try {
        const response = await fetch('/api/auth/users/', {
          credentials: 'include',
        })

        if (!response.ok) {
          throw new Error(tr("Не удалось загрузить пользователей"))
        }

        const data = await readApiJson(response)

        if (!cancelled) {
          setUsers(data.users)
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : 'Ошибка'
          )
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    loadUsers()

    return () => {
      cancelled = true
    }
  }, [])

  async function createStudent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    setSaving(true)
    setFormError('')
    setMessage('')

    try {
      const csrfResponse = await fetch('/api/auth/csrf/', {
        credentials: 'include',
      })

      if (!csrfResponse.ok) {
        throw new Error(tr("Ошибка получения CSRF-токена"))
      }

      const token = getCookie('csrftoken')

      if (!token) {
        throw new Error(tr("CSRF-токен не найден"))
      }

      const response = await fetch('/api/auth/students/create/', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': token,
        },
        body: JSON.stringify({
          first_name: firstName, last_name: lastName,
          username,
          email,
          password,
        }),
      })

      const data = await readApiJson(response)

      if (!response.ok) {
        throw new Error(data.error || tr("Ошибка создания студента"))
      }

      setUsers(prev => [...prev, data.user])

      setUsername(''); setFirstName(''); setLastName('')
      setEmail('')
      setPassword('')
      setShowForm(false)

      setMessage('Студент успешно добавлен!')
    } catch (err) {
      setFormError(
        err instanceof Error ? err.message : tr("Ошибка соединения")
      )
    } finally {
      setSaving(false)
    }
  }

async function deleteStudent(user: User) {
  if (user.role !== 'student') return

  setDeletingId(user.id)
  setDeleteError('')
  setMessage('')

  try {
    const csrfResponse = await fetch('/api/auth/csrf/', {
      credentials: 'include',
    })

    if (!csrfResponse.ok) {
      throw new Error(tr("Ошибка получения CSRF-токена"))
    }

    const token = getCookie('csrftoken')

    if (!token) {
      throw new Error(tr("CSRF-токен не найден"))
    }

    const response = await fetch(
      `/api/auth/users/${user.id}/`,
      {
        method: 'DELETE',
        credentials: 'include',
        headers: {
          'X-CSRFToken': token,
        },
      }
    )

    const data = await readApiJson(response)

    if (!response.ok) {
      throw new Error(data.error || tr("Ошибка удаления"))
    }

    setUsers(prev =>
      prev.filter(item => item.id !== user.id)
    )

    setMessage('Студент успешно удалён!')

  } catch (err) {
    setDeleteError(
      err instanceof Error ? err.message : tr("Ошибка соединения")
    )
  } finally {
    setDeletingId(null)
  }
}

  const filteredUsers = users.filter(user => (!roleFilter || user.role === roleFilter) && (
    (user.display_name || user.username).toLowerCase().includes(search.toLowerCase()) || user.username.toLowerCase().includes(search.toLowerCase()) ||
    user.email.toLowerCase().includes(search.toLowerCase())
  ))

  return (
    <div className="page users-page">
      <header className="page-header">
        <div>
          <h2 className="page-title">{tr("Управление пользователями")}</h2>
          {!loading && !error && <p className="page-sub">{tr('Всего: {0} · студентов: {1} · преподавателей: {2}', [String(users.length), String(users.filter(u => u.role === 'student').length), String(users.filter(u => u.role === 'teacher').length)])}</p>}
        </div>

        <button
          className="add-user-btn"
          onClick={() => {
            setShowForm(!showForm)
            setFormError('')
          }}
        >
          {showForm ? tr("Отмена") : tr("+ Добавить студента")}
        </button>
      </header>

      {!loading && !error && <AdminResponsibilities current={current} people={users} changed={() => { fetch('/api/auth/users/', { credentials: 'include' }).then(readApiJson).then(value => setUsers(value.users)).catch(() => setError('Не удалось загрузить пользователей')) }} />}

      {message && <p className="users-success">{tr(message)}</p>}
      {deleteError && <p className="users-error">{tr(deleteError)}</p>}

      {showForm && (
        <div className="student-form-card">
          <h3>{tr("Новый студент")}</h3>

          <form onSubmit={createStudent}>
            <label htmlFor="student-last-name">{tr("Фамилия")}</label><input id="student-last-name" value={lastName} onChange={e => setLastName(e.target.value)} maxLength={150} autoComplete="family-name" required />
            <label htmlFor="student-first-name">{tr("Имя")}</label><input id="student-first-name" value={firstName} onChange={e => setFirstName(e.target.value)} maxLength={150} autoComplete="given-name" required />
            <label htmlFor="student-username">{tr("Логин")}</label>
            <input
              id="student-username"
              value={username}
              onChange={e => setUsername(e.target.value)}
              placeholder="student01"
              required
            />

            <label htmlFor="student-email">{tr("Email")}</label>
            <input
              id="student-email"
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="student@example.com"
              required
            />

            <label htmlFor="student-password">{tr("Пароль")}</label>
            <input
              id="student-password"
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder={tr("Пароль студента")}
              autoComplete="new-password"
              required
            />

            <p>{tr("Роль: Студент")}</p>

            {formError && <p className="users-error">{tr(formError)}</p>}

            <button type="submit" disabled={saving}>
              {saving ? tr("Сохранение...") : tr("Создать студента")}
            </button>
          </form>
        </div>
      )}

      <div className="users-filters">
        <input
          className="users-search"
          type="search"
          aria-label={tr("Поиск по имени или email...")}
          placeholder={tr("Поиск по имени или email...")}
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        <select className="users-role-filter" aria-label={tr("Роль")} value={roleFilter} onChange={e => setRoleFilter(e.target.value)}>
          <option value="">{tr("Все роли")}</option>
          <option value="student">{tr("Студенты")}</option>
          <option value="teacher">{tr("Преподаватели")}</option>
          <option value="admin">{tr("Администраторы")}</option>
        </select>
      </div>

      {loading && <p>{tr("Загрузка пользователей...")}</p>}
      {error && <p className="users-error">{tr(error)}</p>}

      {!loading && !error && (
        <div className="users-table-wrap" tabIndex={0} role="region" aria-label={tr("Таблица прокручивается по горизонтали")}>
          <table className="users-table">
            <thead>
              <tr>
                <th>{tr("Имя и логин для входа")}</th>
                <th>{tr("Email")}</th>
                <th>{tr("Роль")}</th>
                <th>{tr("Статус")}</th>
                <th>{tr("Действия")}</th>
              </tr>
            </thead>

            <tbody>
              {filteredUsers.map(user => (
                <tr key={user.id}>
                  <td><strong>{user.display_name}</strong><br /><small className="muted">@{user.username}</small></td>
                  <td>{user.email}</td>
                  <td><RoleBadge label={tr(user.role_label)} /></td>
                  <td>
                    {user.is_active ? tr("Активен") : tr("Неактивен")}
                  </td>
                  
<td className="users-actions">
  {user.role === 'student' && (confirming === user.id
    ? <span className="confirm-action" role="group" aria-label={tr("Подтверждение действия")}>
        <span>{tr("Удалить студента «{0}» и его учебные результаты?", [user.display_name])}</span>
        <button type="button" className="danger small" disabled={deletingId !== null} onClick={() => { setConfirming(null); deleteStudent(user) }}>{deletingId === user.id ? tr("Удаление...") : tr("Подтвердить")}</button>
        <button type="button" className="secondary small" onClick={() => setConfirming(null)}>{tr("Отмена")}</button>
      </span>
    : <MoreMenu label={tr("Действия с пользователем {0}", [user.display_name])} items={[{ label: tr("Удалить"), danger: true, onSelect: () => setConfirming(user.id) }]} />)}
</td>

                </tr>
              ))}
            </tbody>
          </table>

          {filteredUsers.length === 0 && (
            <p>{tr("Пользователи не найдены")}</p>
          )}
        </div>
      )}
    </div>
  )
}

export default UsersPage
