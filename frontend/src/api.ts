import { readApiJson } from './i18n/contentStore'
import { t as tr } from './i18n/language'
export type User = {
  id: number
  display_name?: string
  role_label?: string
  username: string
  role: 'student' | 'teacher' | 'admin'
  admin_scope?: 'full' | 'system' | 'learning' | null
  capabilities?: { system_admin: boolean; learning_admin: boolean; manage_accounts: boolean; manage_admin_roles: boolean }
  can_teach?: boolean
  preferred_language?: string
}

export async function apiRequest<T>(url: string, method = 'GET', data?: unknown): Promise<T> {
  const headers: Record<string, string> = {}
  let body: BodyInit | undefined
  if (method !== 'GET') {
    await ensureCsrf()
    headers['X-CSRFToken'] = getCookie('csrftoken')
  }
  if (data instanceof FormData) body = data
  else if (data !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(data)
  }
  const response = await fetch(url, { method, credentials: 'include', headers, body })
  const result = await readApiJson(response).catch(() => ({}))
  if (!response.ok) throw new Error(result.error || tr("Ошибка запроса ({0})", [response.status]))
  return result as T
}

export function getCookie(name: string) {
  const cookie = document.cookie
    .split('; ')
    .find(item => item.startsWith(name + '='))

  return cookie
    ? decodeURIComponent(cookie.substring(name.length + 1))
    : ''
}

export async function ensureCsrf() {
  const response = await fetch('/api/auth/csrf/', {
    credentials: 'include',
  })

  if (!response.ok) {
    throw new Error(tr("Ошибка CSRF"))
  }
}

export async function loginRequest(username: string, password: string): Promise<User> {
  await ensureCsrf()
  const token = getCookie('csrftoken')

  if (!token) {
    throw new Error(tr("CSRF-токен не найден"))
  }

  const response = await fetch('/api/auth/login/', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': token,
    },
    body: JSON.stringify({ username, password }),
  })

  const data = await readApiJson(response)

  if (!response.ok) {
    throw new Error(data.error || tr("Ошибка входа"))
  }

  return {
    admin_scope: data.admin_scope, capabilities: data.capabilities,
    id: data.id,
    preferred_language: data.preferred_language,
    display_name: data.display_name, role_label: data.role_label,
    username: data.username,
    role: data.role,
    can_teach: data.can_teach,
  }
}

export async function registerRequest(
  username: string,
  email: string,
  password: string,
  firstName = '',
  lastName = '',
): Promise<User> {
  await ensureCsrf()
  const token = getCookie('csrftoken')
  if (!token) throw new Error(tr("CSRF-токен не найден"))

  const response = await fetch('/api/auth/register/', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': token,
    },
    body: JSON.stringify({ username, email, password, first_name: firstName, last_name: lastName }),
  })

  const data = await readApiJson(response).catch(() => ({}))
  if (!response.ok) {
    throw new Error(data.error || tr("Не удалось зарегистрироваться"))
  }
  return { id: data.id, display_name: data.display_name, role_label: data.role_label, username: data.username, role: data.role }
}

export async function enrollRequest(courseId: number) {
  await ensureCsrf()
  const token = getCookie('csrftoken')

  const response = await fetch(`/api/courses/${courseId}/enroll/`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': token,
    },
  })

  const data = await readApiJson(response).catch(() => ({}))

  if (response.status === 401) {
    const error = new Error(data.error || tr("Чтобы записаться, войдите в аккаунт"))
    ;(error as Error & { authRequired?: boolean }).authRequired = true
    throw error
  }

  if (!response.ok) {
    throw new Error(data.error || tr("Не удалось записаться на курс"))
  }

  return data
}
