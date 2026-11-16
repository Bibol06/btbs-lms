import { useState } from 'react'
import { apiRequest } from '../../api'
import { t } from '../../i18n/language'
import { errorMessage, formatDate } from '../study/types'

export type BackupStatus = { running?: boolean; queued: boolean; last_success?: string; next_due?: string; error?: string | null;
  location?: string; remote?: { verified_at: string; bytes: number };
  media_files?: number; key_available: boolean; keep: number; schedule_hour: number; timezone: string;
  archives: { name: string; bytes: number }[]; restore_check: { ok?: boolean; checked_at?: string; media_files?: number } }
export default function BackupPanel({ data, mail, changed }: { data: BackupStatus; mail: { mode: string; pending: number; failed: number }; changed: () => void }) {
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [message, setMessage] = useState('')
  async function create() {
    setBusy(true); setError(''); setMessage('')
    try { const result = await apiRequest<{ message: string }>('/api/auth/system/backups/', 'POST', {}); setMessage(result.message); changed() }
    catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }
  return <article className="study-card backup-panel"><div className="section-heading"><h3>{t('Резервные копии')}</h3>
    <button disabled={busy || data.running || data.queued} onClick={create}>{t(data.running ? 'Создаём копию…' : data.queued ? 'В очереди' : 'Создать копию сейчас')}</button></div>
    {(error || data.error) && <p className="error" role="alert">{t(error || data.error || '')}</p>}{message && <p role="status">{t(message)}</p>}
    <div className="backup-summary"><div><span>{t('Последняя успешная копия')}</span><strong>{data.last_success ? formatDate(data.last_success) : t('Пока нет')}</strong></div>
      <div><span>{t('Следующая копия')}</span><strong>{data.next_due ? formatDate(data.next_due) : t('При запуске службы')}</strong></div>
      <div><span>{t('Проверка восстановления')}</span><strong>{data.restore_check.ok ? formatDate(data.restore_check.checked_at) : t('Ещё не выполнена')}</strong></div></div>
    <p className="muted">{t('Зашифрованные архивы · На этом компьютере · Храним последних: {0}', [data.keep])}</p>
    {data.location === 'local+s3' && <p>{t('Внешняя копия S3')}: <strong>{data.remote?.verified_at ? formatDate(data.remote.verified_at) : t('Ещё не выполнена')}</strong></p>}
    {!data.key_available && <p className="muted">{t('Ключ шифрования будет создан вместе с первой копией.')}</p>}
    <details><summary>{t('Сохранённые копии')} ({data.archives.length})</summary>{data.archives.map(a => <p className="backup-file" key={a.name}><code>{a.name}</code><span>{(a.bytes / 1024 / 1024).toFixed(2)} MB</span></p>)}</details>
    <div className="backup-mail"><strong>{t('Письма восстановления пароля')}</strong><p>{t(mail.mode === 'smtp' ? 'Отправка через SMTP' : 'Локальный режим — письма сохраняются на компьютере')}</p>
      {(mail.pending > 0 || mail.failed > 0) && <p>{t('В очереди: {0} · Ошибок отправки: {1}', [mail.pending, mail.failed])}</p>}</div>
  </article>
}
