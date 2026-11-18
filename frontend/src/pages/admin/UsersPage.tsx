import { readApiJson } from '../../i18n/contentStore'
import { t as tr } from '../../i18n/language'
import RoleBadge from '../../components/RoleBadge'
import type { User as SessionUser } from '../../api'
import AdminResponsibilities from './AdminResponsibilities'

import { useEffect, useState, type FormEvent } from 'react'
import './UsersPage.css'
import ConfirmAction from '../study/ConfirmAction'

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

  const filteredUsers = users.filter(user =>
    (user.display_name || user.username).toLowerCase().includes(search.toLowerCase()) || user.username.toLowerCase().includes(search.toLowerCase()) ||
    user.email.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className="users-page">
      <div className="users-header">
        <div>
          <h2>{tr("Управление пользователями")}</h2>
          
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
      </div>

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

      <div className="users-stats">
        <div className="card">
          <h3>{users.length}</h3>
          <p>{tr("Всего пользователей")}</p>
        </div>

        <div className="card">
          <h3>{users.filter(u => u.role === 'student').length}</h3>
          <p>{tr("Студенты")}</p>
        </div>

        <div className="card">
          <h3>{users.filter(u => u.role === 'teacher').length}</h3>
          <p>{tr("Преподаватели")}</p>
        </div>
      </div>

      <input
        className="users-search"
        placeholder={tr("Поиск по имени или email...")}
        value={search}
        onChange={e => setSearch(e.target.value)}
      />

      {loading && <p>{tr("Загрузка пользователей...")}</p>}
      {error && <p className="users-error">{tr(error)}</p>}

      {!loading && !error && (
        <div className="users-table-wrap" tabIndex={0} role="region" aria-label={tr("Таблица прокручивается по горизонтали")}>
          <table className="users-table">
            <thead>
              <tr>
                <th>ID</th>
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
                  <td>{user.id}</td>
                  <td><strong>{user.display_name}</strong><br /><small className="muted">@{user.username}</small></td>
                  <td>{user.email}</td>
                  <td><RoleBadge label={tr(user.role_label)} /></td>
                  <td>
                    {user.is_active ? tr("Активен") : tr("Неактивен")}
                  </td>
                  
<td>
  {user.role === 'student' && (
    <ConfirmAction
      label={deletingId === user.id ? tr("Удаление...") : tr("Удалить")}
      question={tr("Удалить студента «{0}» и его учебные результаты?", [user.display_name])}
      disabled={deletingId !== null}
      onConfirm={() => deleteStudent(user)}
    />
  )}
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
