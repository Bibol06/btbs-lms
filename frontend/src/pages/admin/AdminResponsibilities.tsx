import { useState } from 'react'
import { apiRequest, type User } from '../../api'
import { t } from '../../i18n/language'
import { errorMessage } from '../study/types'

type Person = { id: number; display_name: string; username: string; role: string; admin_scope?: string | null; is_active: boolean }
export default function AdminResponsibilities({ current, people, changed }: { current?: User; people: Person[]; changed: () => void }) {
  const [target, setTarget] = useState(''), [responsibility, setResponsibility] = useState('learning')
  const [error, setError] = useState(''), [message, setMessage] = useState(''), [busy, setBusy] = useState(false)
  return <section className="admin-responsibilities"><h3>{t('Администраторы платформы')}</h3><div className="admin-responsibility-grid">{(['system', 'learning'] as const).map(scope => <article className="study-card" key={scope}>
    <h4>{t(scope === 'system' ? 'Системный администратор' : 'Администратор обучения')}</h4>
    <div className="admin-responsibility-tags">{(scope === 'system' ? ['Пользователи и доступ', 'Система и хранилище', 'Входы и устройства'] : ['Курсы и группы', 'Сроки и проверки', 'Результаты и аналитика']).map(label => <span key={label}>{t(label)}</span>)}</div>
    {people.filter(p => p.role === 'admin' && p.admin_scope === scope).map(p => <p key={p.id}><strong>{p.display_name || p.username}</strong><small>@{p.username} · {t(p.is_active ? 'Активен' : 'Неактивен')}</small></p>)}
    {!people.some(p => p.role === 'admin' && p.admin_scope === scope) && <p className="muted">{t('Пока не назначен')}</p>}
  </article>)}</div>{current?.capabilities?.manage_admin_roles && <details className="study-card"><summary>{t('Назначить область ответственности')}</summary><form className="study-form" onSubmit={async event => {
    event.preventDefault(); setBusy(true); setError(''); setMessage('')
    try { await apiRequest(`/api/auth/users/${target}/responsibility/`, 'POST', { responsibility }); changed(); setMessage('Полномочия обновлены. Пользователю нужно обновить страницу.'); setTarget('') }
    catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }}><label>{t('Пользователь')}<select required value={target} onChange={e => setTarget(e.target.value)}><option value="">{t('Выберите пользователя')}</option>{people.filter(p => p.id !== current.id && !(p.role === 'admin' && (!p.admin_scope || p.admin_scope === 'full'))).map(p => <option value={p.id} key={p.id}>{p.display_name || p.username}</option>)}</select></label><label>{t('Область ответственности')}<select value={responsibility} onChange={e => setResponsibility(e.target.value)}><option value="learning">{t('Администратор обучения')}</option><option value="system">{t('Системный администратор')}</option><option value="teacher">{t('Преподаватель')}</option><option value="student">{t('Студент')}</option></select></label>{error && <p className="error" role="alert">{t(error)}</p>}{message && <p className="success" role="status">{t(message)}</p>}<button disabled={busy || !target}>{t('Сохранить полномочия')}</button></form></details>}</section>
}
