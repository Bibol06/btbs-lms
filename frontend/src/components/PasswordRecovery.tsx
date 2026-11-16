import { useEffect, useState, type FormEvent } from 'react'
import { apiRequest } from '../api'
import { getLanguage, t } from '../i18n/language'
import { errorMessage } from '../pages/study/types'
import './PasswordRecovery.css'
type Delivery = { delivery_mode: 'local' | 'smtp'; configured: boolean }

export default function PasswordRecovery({ reset, login }: { reset: boolean; login: () => void }) {
  const [link] = useState(() => {
    const params = new URLSearchParams(location.hash.slice(1))
    return { uid: params.get('uid') || '', token: params.get('token') || '' }
  })
  const [email, setEmail] = useState(''), [password, setPassword] = useState(''), [confirmation, setConfirmation] = useState('')
  const [checking, setChecking] = useState(reset), [valid, setValid] = useState(!reset)
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [message, setMessage] = useState('')
  const [delivery, setDelivery] = useState<Delivery | null>(null)
  useEffect(() => {
    if (reset) return
    let alive = true
    apiRequest<Delivery>('/api/auth/password-reset/status/').then(value => { if (alive) setDelivery(value) }).catch(() => {})
    return () => { alive = false }
  }, [reset])
  useEffect(() => {
    if (!reset) return
    let alive = true
    apiRequest('/api/auth/password-reset/validate/', 'POST', link).then(() => { if (alive) setValid(true) })
      .catch(e => { if (alive) setError(errorMessage(e)) }).finally(() => { if (alive) setChecking(false) })
    return () => { alive = false }
  }, [reset, link])
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError('')
    const values = new FormData(event.currentTarget)
    try {
      if (reset && values.get('password') !== values.get('confirm_password')) throw new Error('Пароли не совпадают')
      const result = await apiRequest<{ message: string } & Partial<Delivery>>(reset ? '/api/auth/password-reset/confirm/' : '/api/auth/password-reset/', 'POST', reset
        ? { ...link, password: values.get('password'), confirm_password: values.get('confirm_password') }
        : { email: values.get('email'), language: getLanguage() })
      setMessage(result.message); setPassword(''); setConfirmation('')
      if (result.delivery_mode) setDelivery({ delivery_mode: result.delivery_mode, configured: Boolean(result.configured) })
      if (reset) history.replaceState(null, '', '#page=reset-password')
    } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }
  return <section className="password-recovery"><article className="study-card">
    <p className="eyebrow">BTBS</p><h1>{t(reset ? 'Новый пароль' : 'Восстановление пароля')}</h1>
    {!reset && !message && delivery?.delivery_mode === 'local' && <p className="recovery-notice" role="status">{t('Отправка на email ещё не подключена. Письмо не придёт в почтовый ящик. Обратитесь к администратору.')}</p>}
    {checking ? <p role="status">{t('Проверяем ссылку…')}</p> : <>
      {error && <p className="error" role="alert">{t(error)}</p>}
      {message ? <div role="status"><p>{t(message)}</p>{!reset && delivery?.delivery_mode === 'smtp' && <p className="muted">{t('Проверьте входящие письма и папку «Спам».')}</p>}</div> : valid && <form className="study-form" onSubmit={submit}>
        {reset ? <><label>{t('Новый пароль')}<input name="password" type="password" autoComplete="new-password" value={password} onChange={e => setPassword(e.target.value)} minLength={8} maxLength={256} required /></label>
          <label>{t('Повторите пароль')}<input name="confirm_password" type="password" autoComplete="new-password" value={confirmation} onChange={e => setConfirmation(e.target.value)} minLength={8} maxLength={256} required /></label></>
          : <label>{t('Email аккаунта')}<input name="email" type="email" autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} maxLength={254} required /></label>}
        <button type="submit" disabled={busy}>{t(busy ? 'Отправляем…' : reset ? 'Сохранить новый пароль' : delivery?.delivery_mode === 'local' ? 'Запросить ссылку' : 'Отправить ссылку')}</button>
      </form>}
      {reset && !valid && <a className="button-link" href="#page=forgot-password">{t('Запросить новую ссылку')}</a>}
    </>}
    <button className="secondary recovery-login" onClick={login}>{t('Вернуться ко входу')}</button>
  </article></section>
}
