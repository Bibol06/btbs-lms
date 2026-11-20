import { ct } from '../../i18n/content'
import { t as tr } from '../../i18n/language'
import RoleBadge from '../../components/RoleBadge'
import { useEffect, useState, type FormEvent } from 'react'
import { apiRequest } from '../../api'
import { errorMessage, formatDate } from '../study/types'

type Announcement = { id: number; title: string; body: string; author: string; author_role_label: string; created_at: string; is_published: boolean; can_edit: boolean; all_course: boolean }
type Conversation = { id: number; student: string; student_role_label: string; unread: number }
type Message = { id: number; author: string; author_role_label: string; mine: boolean; body: string; created_at: string }

export function Announcements({ courseId, runId, manage, canEdit }: { courseId: number; runId: number; manage: boolean; canEdit: boolean }) {
  const [items, setItems] = useState<Announcement[]>([])
  const [revision, setRevision] = useState(0)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [editing, setEditing] = useState<Announcement | 'new' | null>(null)
  useEffect(() => {
    let alive = true
    apiRequest<{ announcements: Announcement[] }>(`/api/communication/courses/${courseId}/announcements/?run_id=${runId}`)
      .then(data => { if (alive) { setItems(data.announcements); setError('') } }).catch(err => { if (alive) setError(errorMessage(err)) })
    return () => { alive = false }
  }, [courseId, runId, revision])
  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const form = new FormData(e.currentTarget)
    setBusy(true); setError('')
    try {
      await apiRequest(editing && editing !== 'new' ? `/api/communication/announcements/${editing.id}/` : `/api/communication/courses/${courseId}/announcements/?run_id=${runId}`,
        editing && editing !== 'new' ? 'PATCH' : 'POST', { title: form.get('title'), body: form.get('body'), is_published: form.has('published'), all_course: form.has('all_course') })
      setEditing(null); setRevision(v => v + 1)
    } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }
  const initial = editing === 'new' ? undefined : editing
  return <section className="study-section">
    <div className="section-heading"><h2 className="section-title">{tr("Новости курса")}</h2>{manage && <button onClick={() => setEditing('new')}>{tr("+ Объявление")}</button>}</div>
    {error && <p className="error" role="alert">{tr(error)}</p>}
    {editing && <form className="study-form" key={initial?.id ?? 'new'} onSubmit={save}>
      <label>{tr("Заголовок")}<input name="title" required maxLength={200} defaultValue={initial?.title} /></label>
      <label>{tr("Текст объявления")}<textarea name="body" rows={6} required maxLength={20000} defaultValue={initial?.body} /></label>
      {canEdit && editing === 'new' && <label className="check"><input type="checkbox" name="all_course" /> {tr(" Всем запускам курса (иначе только выбранной группе)")}</label>}
      <label className="check"><input type="checkbox" name="published" defaultChecked={initial?.is_published ?? true} /> {tr(" Опубликовать и уведомить студентов")}</label>
      <div className="action-row"><button disabled={busy}>{tr("Сохранить объявление")}</button><button type="button" className="secondary" onClick={() => setEditing(null)}>{tr("Отмена")}</button></div>
    </form>}
    {!items.length && <p className="empty-state">{tr("Объявлений пока нет.")}</p>}
    {items.map(a => <article className="study-card" key={a.id}><h3>{ct(a, "title")}</h3><p className="muted">{a.author}<RoleBadge label={tr(a.author_role_label)} /> · {formatDate(a.created_at)} · {a.all_course ? tr("Весь курс") : tr("Текущий запуск")}{!a.is_published ? tr(" · Черновик") : ''}</p><p className="preserve-text">{ct(a, "body")}</p>{a.can_edit && <button className="secondary" onClick={() => setEditing(a)}>{tr("Изменить объявление")}</button>}</article>)}
  </section>
}

export function Conversations({ courseId, runId, manage }: { courseId: number; runId: number; manage: boolean }) {
  const [data, setData] = useState<{ conversations: Conversation[]; students: { id: number; student__username: string; student: string; role_label: string }[] } | null>(null)
  const [selected, setSelected] = useState<number | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [older, setOlder] = useState<number | null>(null)
  const [revision, setRevision] = useState(0)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [draft, setDraft] = useState('')
  useEffect(() => {
    let alive = true
    async function load() {
      try {
        const value = await apiRequest<typeof data>(`/api/communication/courses/${courseId}/conversations/?run_id=${runId}`)
        if (alive) setData(value)
      } catch (err) { if (alive) setError(errorMessage(err)) }
    }
    void load(); const timer = window.setInterval(load, 15000)
    return () => { alive = false; window.clearInterval(timer) }
  }, [courseId, runId, revision])
  useEffect(() => {
    let alive = true
    if (!selected) return
    let first = true
    async function load() {
      try {
        const result = await apiRequest<{ messages: Message[]; next_before: number | null }>(`/api/communication/conversations/${selected}/messages/`)
        if (!alive) return
        if (first) { setMessages(result.messages); setOlder(result.next_before); first = false }
        else setMessages(current => [...new Map([...current, ...result.messages].map(m => [m.id, m])).values()].sort((a, b) => a.id - b.id))
        setError('')
        await apiRequest(`/api/communication/conversations/${selected}/messages/`, 'PATCH', {})
        if (alive) setData(current => current ? { ...current, conversations: current.conversations.map(c => c.id === selected ? { ...c, unread: 0 } : c) } : current)
      } catch (err) { if (alive) setError(errorMessage(err)) }
    }
    void load(); const timer = window.setInterval(load, 5000)
    return () => { alive = false; window.clearInterval(timer) }
  }, [selected, revision])
  async function open(enrollmentId?: number) {
    setBusy(true); setError('')
    try {
      const result = await apiRequest<{ id: number }>(`/api/communication/courses/${courseId}/conversations/?run_id=${runId}`, 'POST', { enrollment_id: enrollmentId })
      if (selected !== result.id) { setMessages([]); setDraft(''); setSelected(result.id) }
      setRevision(v => v + 1)
    } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }
  async function send(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError('')
    try { await apiRequest(`/api/communication/conversations/${selected}/messages/`, 'POST', { body: draft }); setDraft(''); setRevision(v => v + 1) }
    catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }
  async function loadOlder() {
    try {
      const result = await apiRequest<{ messages: Message[]; next_before: number | null }>(`/api/communication/conversations/${selected}/messages/?before=${older}`)
      setMessages(current => [...result.messages, ...current]); setOlder(result.next_before)
    } catch (err) { setError(errorMessage(err)) }
  }
  return <section className="study-section"><h2 className="section-title">{tr("Личные сообщения по курсу")}</h2>
    {error && <p className="error" role="alert">{tr(error)}</p>}
    <div className="action-row">{manage ? data?.students.map(s => <button className="secondary" key={s.id} onClick={() => open(s.id)} disabled={busy}>{tr("Написать: ")}{s.student}<RoleBadge label={tr(s.role_label)} /></button>) : <button disabled={busy} onClick={() => open()}>{tr("Написать преподавателю")}</button>}</div>
    {data && !data.conversations.length && !selected && <div className="empty"><p>{manage ? tr("Переписок пока нет. Выберите ученика, чтобы написать ему.") : tr("Здесь появится переписка с преподавателями курса.")}</p></div>}
    {Boolean(data?.conversations.length) && <div className="segment" role="group" aria-label={tr("Личные сообщения по курсу")}>{data?.conversations.map(c => <button type="button" aria-pressed={selected === c.id} key={c.id} onClick={() => { if (selected !== c.id) { setSelected(c.id); setDraft(''); setMessages([]) } }}>{manage ? <>{c.student}<RoleBadge label={tr(c.student_role_label)} /></> : tr("Преподаватели курса")}{c.unread ? tr(" · {0} новых", [c.unread]) : ''}</button>)}</div>}
    {selected && <div className="study-card">
      {older && <button className="secondary" onClick={loadOlder}>{tr("Предыдущие сообщения")}</button>}
      {!messages.length && <p className="muted">{tr("Начните диалог.")}</p>}
      {messages.map(m => <article className={`message ${m.mine ? 'mine' : ''}`} key={m.id}><strong>{m.author}</strong><RoleBadge label={tr(m.author_role_label)} /><p className="preserve-text">{ct(m, "body")}</p><small>{formatDate(m.created_at)}</small></article>)}
      <form className="study-form compact" onSubmit={send}><label>{tr("Ваше сообщение")}<textarea required rows={3} maxLength={10000} value={draft} onChange={e => setDraft(e.target.value)} /></label><button disabled={busy || !draft.trim()}>{tr("Отправить сообщение")}</button></form>
    </div>}
  </section>
}

export { default as Discussion } from './Discussion'
