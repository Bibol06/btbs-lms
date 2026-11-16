import { localizedLabels, t } from './i18n/language'
import type { User } from './api'

export type Workspace = 'student' | 'teacher' | 'admin'
export type NavItem = { id: string; label: string; icon: string }

export function workspaceFor(user: User | null): Workspace {
  return user?.role === 'admin' ? 'admin' : user?.role === 'teacher' || user?.can_teach ? 'teacher' : 'student'
}
export function homeFor(user: User | null) {
  if (user?.role === 'admin' && user.admin_scope === 'system') return 'system'
  const role = workspaceFor(user)
  return role === 'admin' ? 'admin' : role === 'teacher' ? 'teaching' : 'learning'
}
export const workspaceNames = localizedLabels({ student: 'Кабинет студента', teacher: 'Кабинет преподавателя', admin: 'Кабинет администратора' })
export function workspaceTitle(user: User | null) {
  if (user?.role !== 'admin') return workspaceNames[workspaceFor(user)]
  return t(user.admin_scope === 'system' ? 'Кабинет системного администратора' : user.admin_scope === 'learning' ? 'Кабинет администратора обучения' : 'Кабинет владельца')
}
export const navigation: Record<Workspace, NavItem[]> = localizedLabels({
  student: [{ id: 'learning', label: 'Моё обучение', icon: '⌂' }, { id: 'deadlines', label: 'Мои задания и сроки', icon: '◷' }, { id: 'analytics', label: 'Мой прогресс', icon: '▥' }, { id: 'catalog', label: 'Каталог курсов', icon: '▦' }],
  teacher: [{ id: 'teaching', label: 'Мои курсы и группы', icon: '▤' }, { id: 'reviews', label: 'Проверка работ', icon: '◷' }, { id: 'questions', label: 'Вопросы учеников', icon: '?' }, { id: 'attention', label: 'Требует внимания', icon: '!' }, { id: 'students', label: 'Мои ученики', icon: '♙' }, { id: 'analytics', label: 'Аналитика обучения', icon: '▥' }, { id: 'bank', label: 'Банк вопросов', icon: '▤' }, { id: 'catalog', label: 'Каталог курсов', icon: '▦' }],
  admin: [{ id: 'admin', label: 'Обзор платформы', icon: '⌂' }, { id: 'attention', label: 'Требует внимания', icon: '!' }, { id: 'analytics', label: 'Аналитика платформы', icon: '▥' }, { id: 'admin-teachers', label: 'Преподаватели', icon: '▤' }, { id: 'students', label: 'Контроль обучения', icon: '♙' }, { id: 'reviews', label: 'Контроль проверок', icon: '◷' }, { id: 'questions', label: 'Вопросы учеников', icon: '?' }, { id: 'admin-courses', label: 'Все курсы', icon: '▦' }, { id: 'bank', label: 'Банк вопросов', icon: '▤' }, { id: 'users', label: 'Пользователи', icon: '♧' }, { id: 'admin-activity', label: 'История действий', icon: '≡' }],
})
export function navigationFor(user: User) {
  const items = navigation[workspaceFor(user)]
  if (user.role !== 'admin') return items
  const systemItem = { id: 'system', label: 'Система и хранилище', icon: '▤' }
  if (user.admin_scope === 'system') return [systemItem, ...items.filter(item => ['users', 'catalog'].includes(item.id))]
  if (user.admin_scope === 'learning') return items.filter(item => item.id !== 'users').map(item => ({ ...item, label: item.id === 'admin' ? t('Обзор обучения') : item.id === 'analytics' ? t('Аналитика обучения') : item.label }))
  return [...items, systemItem]
}
export function routePage() {
  const route = new URLSearchParams(location.hash.slice(1))
  return route.has('course') ? 'catalog' : route.has('profile') ? 'profile' : route.get('page') || 'catalog'
}
export function canonicalPage(page: string, user: User | null) {
  if (user?.admin_scope === 'system' && ['admin', 'teaching'].includes(page)) return 'system'
  if (new URLSearchParams(location.hash.slice(1)).get('mode') === 'personal' && ['learning', 'deadlines', 'analytics'].includes(page)) return page
  if (page === 'deadlines' && user && workspaceFor(user) !== 'student') return 'reviews'
  if (page === 'teaching' && user?.role === 'admin') return 'admin-courses'
  return page
}
