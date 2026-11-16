import { discussionText } from '../../i18n/discussion'
import DiscussionBody from '../../components/DiscussionBody'
import { t as tr } from '../../i18n/language'
import RoleBadge from '../../components/RoleBadge'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { apiRequest } from '../../api'
import { errorMessage, formatDate } from '../study/types'
import './Discussion.css'

type Comment = { id: number; author: string; author_role_label: string; is_teacher: boolean; staff_at_creation: boolean; body: string; is_redacted?: boolean; parent_id: number | null; is_hidden: boolean; is_pinned: boolean; can_edit: boolean; created_at: string; is_resolved: boolean; question_state?: string }
type Thread = { root: Comment; replies: Comment[] }
type DiscussionData = { threads: Thread[]; is_closed: boolean; can_moderate: boolean; total_threads: number; next_page: number | null }
type Composer = { kind: 'reply' | 'edit'; comment: Comment; rootId: number }
const draftKey = (composer: Composer | null) => composer ? `${composer.kind}:${composer.comment.id}` : 'new'

export default function Discussion({ lessonId, runId }: { lessonId: number; runId: number }) {
  const [data, setData] = useState<DiscussionData | null>(null)
  const [revision, setRevision] = useState(0)
  const [pages, setPages] = useState(1)
  const [composer, setComposer] = useState<Composer | null>(null)
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set())
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [linkedComment] = useState(() => Number(new URLSearchParams(location.hash.slice(1)).get('comment')) || null)
  const [focusId, setFocusId] = useState<number | null>(linkedComment)
  const composerInput = useRef<HTMLTextAreaElement>(null)
  const endpoint = `/api/communication/lessons/${lessonId}/discussion/?run_id=${runId}`
  const commentDomId = (id: number) => `discussion-${lessonId}-${runId}-comment-${id}`

  useEffect(() => {
    let alive = true
    Promise.all(Array.from({ length: pages }, (_, i) => apiRequest<DiscussionData>(`${endpoint}&page=${i + 1}${i === 0 && linkedComment ? `&focus=${linkedComment}` : ''}`)))
      .then(results => {
        if (!alive) return
        const threads = [...new Map(results.flatMap(value => value.threads).map(thread => [thread.root.id, thread])).values()]
        setData({ ...results[0], threads, next_page: results[results.length - 1].next_page }); setError('')
      }).catch(err => { if (alive) setError(errorMessage(err)) }).finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [endpoint, pages, revision, linkedComment])
  useEffect(() => { composerInput.current?.focus() }, [composer])
  useEffect(() => {
    if (focusId === null) return
    const element = document.getElementById(`discussion-${lessonId}-${runId}-comment-${focusId}`)
    if (element) { element.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); element.focus({ preventScroll: true }) }
  }, [data, focusId, lessonId, runId])

  function openComposer(kind: Composer['kind'], comment: Comment, rootId: number) {
    setComposer({ kind, comment, rootId }); setError(''); setMessage(''); setFocusId(null)
    setCollapsed(current => { const next = new Set(current); next.delete(rootId); return next })
  }
  async function change(url: string, payload: unknown) {
    setBusy(true); setError(''); setMessage(''); setFocusId(null)
    try { await apiRequest(url, 'PATCH', payload); setRevision(v => v + 1) }
    catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }
  async function send(event: FormEvent, target: Composer | null) {
    event.preventDefault(); setBusy(true); setError(''); setMessage('')
    const key = draftKey(target)
    const body = drafts[key] ?? (target?.kind === 'edit' ? target.comment.body : '')
    try {
      let id = target?.comment.id ?? null
      if (target?.kind === 'edit') await apiRequest(`/api/communication/comments/${target.comment.id}/`, 'PATCH', { body })
      else {
        const result = await apiRequest<{ id: number }>(endpoint, 'POST', { body, parent_id: target?.comment.id })
        id = result.id
      }
      setDrafts(current => { const next = { ...current }; delete next[key]; return next })
      if (target) setComposer(null)
      else { setPages(1); setComposer(null) }
      setFocusId(id); setMessage(target?.kind === 'edit' ? 'Сообщение сохранено.' : target ? 'Ответ добавлен в эту ветку.' : 'Новый вопрос опубликован.')
      setRevision(v => v + 1)
    } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }
  function form(target: Composer | null) {
    const key = draftKey(target)
    const value = drafts[key] ?? (target?.kind === 'edit' ? target.comment.body : '')
    return <form className={`study-form discussion-composer ${target ? 'inline-composer' : 'new-question'}`} onSubmit={event => send(event, target)}>
      {target ? <>
        <div className="section-heading"><strong>{target.kind === 'edit' ? tr("Редактирование сообщения") : tr("Ответ для {0}", [target.comment.author])}</strong><button className="secondary" type="button" disabled={busy} onClick={() => setComposer(null)}>{tr("Отмена")}</button></div>
        {target.kind === 'reply' && <blockquote className="reply-preview">{discussionText(target.comment).length > 180 ? `${discussionText(target.comment).slice(0, 180)}…` : discussionText(target.comment)}</blockquote>}
      </> : <div><strong>{tr("Задать новый вопрос")}</strong></div>}
      <label>{target?.kind === 'edit' ? tr("Текст сообщения") : target ? tr("Ваш ответ") : tr("Вопрос или комментарий")}<textarea ref={target ? composerInput : undefined} required disabled={busy} value={value} onChange={event => setDrafts(current => ({ ...current, [key]: event.target.value }))} maxLength={10000} rows={3} placeholder={target ? tr("Напишите ответ…") : tr("Задайте отдельный вопрос по уроку…")} /></label>
      <div className="action-row"><button disabled={busy || loading || !value.trim()}>{busy ? tr("Сохранение…") : target?.kind === 'edit' ? tr("Сохранить изменения") : target ? tr("Отправить ответ") : tr("Опубликовать вопрос")}</button></div>
    </form>
  }
  function renderComment(comment: Comment, thread: Thread, isReply = false) {
    const parent = isReply && comment.parent_id !== thread.root.id ? [thread.root, ...thread.replies].find(c => c.id === comment.parent_id) : null
    const editing = composer?.kind === 'edit' && composer.comment.id === comment.id
    return <article className={`discussion-comment ${isReply ? 'thread-reply' : 'thread-question'} ${comment.is_hidden ? 'hidden-comment' : ''}`} key={comment.id} id={commentDomId(comment.id)} tabIndex={-1}>
      <div className="comment-heading"><span className={`avatar comment-avatar ${comment.is_teacher ? 'teacher-avatar' : ''}`} aria-hidden="true">{comment.author[0]?.toUpperCase()}</span><div><div className="comment-author"><strong>{comment.author}</strong><RoleBadge label={tr(comment.author_role_label)} />{comment.is_pinned && <span className="comment-label">{tr("Закреплено")}</span>}{comment.is_hidden && <span className="comment-label">{tr("Скрыто")}</span>}</div><time dateTime={comment.created_at}>{formatDate(comment.created_at)}</time></div></div>
      {parent && <div className="reply-context">{tr("В ответ ")}<strong>{parent.author}</strong><RoleBadge label={tr(parent.author_role_label)} />: <span>{discussionText(parent).length > 110 ? `${discussionText(parent).slice(0, 110)}…` : discussionText(parent)}</span></div>}
      {editing ? form(composer) : <DiscussionBody comment={comment} className="comment-body" />}
      <div className="comment-actions">{!comment.is_hidden && !data?.is_closed && <button className="secondary" disabled={busy} aria-label={tr("Ответить {0}", [comment.author])} onClick={() => openComposer('reply', comment, thread.root.id)}>{tr("Ответить")}</button>}
        {!isReply && !comment.is_hidden && <><span className={`hub-status ${comment.question_state === 'waiting' ? 'warning' : ''}`}>{comment.staff_at_creation ? tr("Комментарий преподавателя") : comment.is_resolved ? tr("Вопрос решён") : comment.question_state === 'answered' ? tr("Преподаватель ответил") : tr("Ожидает ответа")}</span>{!comment.staff_at_creation && (comment.can_edit || data?.can_moderate) && <button className="secondary" disabled={busy} onClick={() => change(`/api/communication/comments/${comment.id}/`, { is_resolved: !comment.is_resolved })}>{comment.is_resolved ? tr("Открыть вопрос снова") : tr("Вопрос решён")}</button>}</>}
        {comment.can_edit && !comment.is_hidden && !editing && <button className="secondary" disabled={busy} onClick={() => openComposer('edit', comment, thread.root.id)}>{tr("Изменить")}</button>}
        {data?.can_moderate && <details className="comment-moderation"><summary>{tr("Модерация")}</summary><div className="action-row"><button className="secondary" disabled={busy} onClick={() => change(`/api/communication/comments/${comment.id}/`, { is_pinned: !comment.is_pinned })}>{comment.is_pinned ? tr("Открепить") : tr("Закрепить")}</button><button className="danger" disabled={busy} onClick={() => change(`/api/communication/comments/${comment.id}/`, { is_hidden: !comment.is_hidden })}>{comment.is_hidden ? tr("Показать") : tr("Скрыть")}</button></div></details>}
      </div>
    </article>
  }
  return <section className="study-card lesson-discussion" aria-label={tr("Обсуждение урока")}>
    <div className="section-heading"><div><h3>{tr("Обсуждение урока")}</h3></div><div className="action-row"><button className="secondary" disabled={busy || loading} onClick={() => { setLoading(true); setFocusId(null); setRevision(v => v + 1) }}>{tr("Обновить")}</button>{data?.can_moderate && <button className="secondary" disabled={busy} onClick={() => change(endpoint, { is_closed: !data.is_closed })}>{data.is_closed ? tr("Открыть обсуждение") : tr("Закрыть обсуждение")}</button>}</div></div>
    {error && <p className="error" role="alert">{tr(error)}</p>}{message && <p className="success" role="status">{tr(message)}</p>}
    {!data && loading && <p role="status">{tr("Загрузка обсуждения…")}</p>}
    {data && <>
      {data.is_closed ? <p className="discussion-closed">{tr("Обсуждение закрыто преподавателем.")}</p> : form(null)}
      <p className="discussion-count">{tr("Вопросов: ")}{data.total_threads}</p>
      {!data.threads.length && <p className="empty-state">{tr("Вопросов пока нет.")}</p>}
      <div className="discussion-threads">{data.threads.map(thread => <section className="discussion-thread" key={thread.root.id} aria-label={tr("Вопрос {0}", [thread.root.author])}>
        {renderComment(thread.root, thread)}
        {thread.replies.length > 0 && <button className="secondary replies-toggle" aria-expanded={!collapsed.has(thread.root.id)} disabled={busy} onClick={() => { setFocusId(null); setCollapsed(current => { const next = new Set(current); if (next.has(thread.root.id)) next.delete(thread.root.id); else next.add(thread.root.id); return next }) }}>{collapsed.has(thread.root.id) ? tr("Показать ответы") : tr("Свернуть ответы")} ({thread.replies.length})</button>}
        {!collapsed.has(thread.root.id) && <div className="thread-replies">{thread.replies.map(comment => renderComment(comment, thread, true))}</div>}
        {composer?.kind === 'reply' && composer.rootId === thread.root.id && !data.is_closed && <div className="thread-reply-form">{form(composer)}</div>}
      </section>)}</div>
      {data.next_page && <button className="secondary discussion-more" disabled={busy || loading} onClick={() => { setLoading(true); setFocusId(null); setPages(data.next_page as number) }}>{loading ? tr("Загрузка…") : tr("Показать ещё вопросы")}</button>}
    </>}
  </section>
}
