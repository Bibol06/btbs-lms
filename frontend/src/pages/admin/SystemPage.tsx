import { useEffect, useState } from 'react'
import { apiRequest } from '../../api'
import { t } from '../../i18n/language'
import { errorMessage, formatDate } from '../study/types'
import RoleBadge from '../../components/RoleBadge'
import BackupPanel, { type BackupStatus } from './BackupPanel'
import './SystemPage.css'

type Status = { database_ok: boolean; database_engine: string; disk_free_gb: number;
  backups: BackupStatus; recovery_mail: { mode: string; pending: number; failed: number };
  storage: { mode: string; configured: boolean; region: string; local_files: number; s3_files: number; pending_uploads: number;
    courses: { id: number; title: string; prefix: string; materials: number; images: number; answers: number; s3_files: number; local_files: number }[] };
  audit: { id: number; actor: string; target: string | null; action: string; created_at: string }[] }
type Session = { id: number; person?: { display_name: string; role_label: string }; device?: string; browser?: string; os?: string; last_seen_at?: string }
const auditLabels: Record<string, string> = {
  'account.responsibility_changed': 'Изменены административные полномочия',
  'storage.connection_verified': 'Подключение S3 проверено', 'storage.connection_failed': 'Ошибка проверки S3',
  'account.password_reset': 'Пароль восстановлен', 'backup.requested': 'Запрошена резервная копия',
}

export default function SystemPage() {
  const [data, setData] = useState<Status | null>(null), [error, setError] = useState(''), [message, setMessage] = useState('')
  const [revision, setRevision] = useState(0), [checking, setChecking] = useState(false)
  const [sessions, setSessions] = useState<Session[]>([])
  useEffect(() => {
    if (!data?.backups?.running && !data?.backups?.queued) return
    const timer = window.setInterval(() => setRevision(n => n+1), 3000)
    return () => window.clearInterval(timer)
  }, [data?.backups?.running, data?.backups?.queued])
  useEffect(() => {
    let alive = true
    apiRequest<Status>('/api/auth/system/status/').then(v => { if (alive) { setData(v); setError('') } }).catch(e => { if (alive) setError(errorMessage(e)) })
    apiRequest<{ sessions: Session[] }>('/api/analytics/sessions/?period=week').then(v => { if (alive) setSessions(v.sessions || []) }).catch(() => {})
    return () => { alive = false }
  }, [revision])
  async function check() {
    setChecking(true); setError(''); setMessage('')
    try { const v = await apiRequest<{ message: string }>('/api/auth/system/storage-check/', 'POST', {}); setMessage(v.message); setRevision(n => n+1) }
    catch (e) { setError(errorMessage(e)) } finally { setChecking(false) }
  }
  return <section className="study-section"><div className="section-heading"><div><p className="eyebrow">{t('Системное администрирование')}</p><h2>{t('Система и хранилище')}</h2></div><button className="secondary" onClick={() => setRevision(n => n+1)}>{t('Обновить данные')}</button></div>
    {error && <p role="alert" className="error">{t(error)}</p>}{message && <p role="status" className="success">{t(message)}</p>}
    {!data ? !error && <p>{t('Загрузка…')}</p> : <><BackupPanel data={data.backups} mail={data.recovery_mail} changed={() => setRevision(n => n+1)} /><div className="course-readiness-metrics"><div><strong>{data.database_ok ? '✓' : '!'}</strong><span>{t('База данных')} · {data.database_engine}</span></div><div><strong>{data.disk_free_gb} GB</strong><span>{t('Свободное место на сервере')}</span></div><div><strong>{data.storage.local_files + data.storage.s3_files}</strong><span>{t('Сохранённых файлов')}</span></div></div>
      <article className="study-card"><h3>{t('Хранилище файлов и видео')}</h3><p>{data.storage.mode === 's3' ? t('Новые файлы сохраняются в S3') : t('Новые файлы сохраняются локально')}</p><p className="muted">{t('Локальных файлов: {0}. В S3: {1}. Незавершённых загрузок: {2}.', [data.storage.local_files, data.storage.s3_files, data.storage.pending_uploads])}</p><button className="secondary" disabled={checking || !data.storage.configured} onClick={check}>{checking ? t('Проверяем…') : t('Проверить подключение S3')}</button></article>
      <article className="study-card"><h3>{t('Файлы по курсам')}</h3>
        {data.storage.courses?.map(c => <div className="storage-course-row" key={c.id}>
          <div><strong>{c.title}</strong><p className="muted">{t('Материалы: {0} · Изображения: {1} · Ответы: {2}', [c.materials, c.images, c.answers])}</p>
            <p className="muted">{t('В S3: {0}. Локально: {1}.', [c.s3_files, c.local_files])}</p>
            <p className="storage-course-path"><span>{t('Папка в S3')}</span><code>{c.prefix}</code></p></div>
          <a href={`#course=${c.id}`}>{t('Открыть курс →')}</a>
        </div>)}{!data.storage.courses?.length && <p className="muted">{t('Загруженных файлов пока нет')}</p>}
      </article>
      <article className="study-card"><h3>{t('Последние входы и устройства')}</h3>{sessions.map(s => <p key={s.id}><strong>{s.person?.display_name}</strong><RoleBadge label={t(s.person?.role_label || '')} /> · {t(s.device || '')} · {t(s.browser || '')} · {t(s.os || '')} · {formatDate(s.last_seen_at)}</p>)}{!sessions.length && <p className="muted">{t('Записей пока нет')}</p>}</article>
      <article className="study-card"><h3>{t('Системный журнал')}</h3>{data.audit.map(e => <p key={e.id}><strong>{e.actor}</strong>{e.target ? ` → ${e.target}` : ''} · {t(auditLabels[e.action] || 'Системное событие')} · {formatDate(e.created_at)}</p>)}{!data.audit.length && <p className="muted">{t('Записей пока нет')}</p>}</article></>}
  </section>
}
