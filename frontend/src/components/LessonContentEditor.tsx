import { useEffect, useId, useRef, useState } from 'react'
import { apiRequest } from '../api'
import { t as tr } from '../i18n/language'
import { errorMessage } from '../pages/study/types'
import RichLessonContent from './RichLessonContent'
import './LessonContent.css'

type Props = {
  lessonId?: number; courseId?: number; scope?: 'lesson' | 'course'; runId?: number; name?: string; label?: string; defaultValue?: string
  value?: string; onChange?: (value: string) => void; rows?: number; maxLength?: number
  onUploadingChange?: (uploading: boolean) => void
}

export default function LessonContentEditor({ lessonId, courseId, scope = 'lesson', runId, name = 'content', label, defaultValue = '', value, onChange, rows = 10, maxLength = 100000, onUploadingChange }: Props) {
  const [draft, setDraft] = useState(defaultValue)
  const [preview, setPreview] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  const text = value ?? draft
  const imageTargetId = scope === 'course' ? courseId : lessonId
  const textarea = useRef<HTMLTextAreaElement>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const alive = useRef(true)
  const currentText = useRef(text)
  const uploadingListener = useRef(onUploadingChange)
  const id = useId()
  useEffect(() => { currentText.current = text }, [text])
  useEffect(() => { uploadingListener.current = onUploadingChange }, [onUploadingChange])
  useEffect(() => { alive.current = true; return () => { alive.current = false; uploadingListener.current?.(false) } }, [])

  function update(next: string) {
    setDraft(next); currentText.current = next; onChange?.(next)
  }
  function insert(before: string, after = '', fallback = '', block = false) {
    const input = textarea.current
    const start = preview ? text.length : input?.selectionStart ?? text.length
    const end = preview ? start : input?.selectionEnd ?? start
    const selection = text.slice(start, end) || fallback
    const prefix = block && start > 0 && text[start - 1] !== '\n' ? '\n\n' : ''
    const suffix = block && end < text.length && text[end] !== '\n' ? '\n\n' : ''
    const next = text.slice(0, start) + prefix + before + selection + after + suffix + text.slice(end)
    if (next.length > maxLength) { setError('Текст превышает допустимый размер'); return }
    update(next); setPreview(false)
    window.requestAnimationFrame(() => { input?.focus(); input?.setSelectionRange(start + prefix.length + before.length, start + prefix.length + before.length + selection.length) })
  }
  async function upload(file?: File) {
    if (!file || !imageTargetId) return
    if (!/\.(png|jpe?g)$/i.test(file.name) || file.size > 8 * 1024 * 1024 || file.size === 0) {
      setError('Выберите PNG или JPEG размером до 8 МБ'); if (fileInput.current) fileInput.current.value = ''; return
    }
    setUploading(true); uploadingListener.current?.(true); setError('')
    const insertionPoint = preview ? currentText.current.length : textarea.current?.selectionStart ?? currentText.current.length
    const data = new FormData(); data.append('file', file)
    try {
      const endpoint = scope === 'course' ? `/api/courses/teacher/${courseId}/images/` : `/api/learning/teacher/lessons/${lessonId}/images/`
      const { image } = await apiRequest<{ image: { title: string; url: string } }>(endpoint, 'POST', data)
      if (!alive.current) return
      const caption = image.title.replaceAll('[', ' ').replaceAll(']', ' ').replace(/[\r\n]/g, ' ').trim()
      const before = currentText.current.slice(0, insertionPoint), after = currentText.current.slice(insertionPoint)
      const next = `${before}${before && !before.endsWith('\n\n') ? '\n\n' : ''}![${caption}](${image.url})\n\n${after}`
      if (next.length > maxLength) { setError('Текст превышает допустимый размер'); return }
      update(next); setPreview(true)
    } catch (err) { if (alive.current) setError(errorMessage(err)) }
    finally {
      uploadingListener.current?.(false)
      if (alive.current) { setUploading(false); if (fileInput.current) fileInput.current.value = '' }
    }
  }

  return <div className="lesson-content-editor">
    <label htmlFor={id}>{label || tr('Содержание урока')}</label>
    <div className="lesson-editor-toolbar" role="toolbar" aria-label={scope === 'course' ? tr('Оформление описания курса') : tr('Оформление урока')}>
      <button type="button" className="secondary" onClick={() => insert('## ', '', tr('Заголовок'), true)} disabled={uploading}>{tr('Заголовок')}</button>
      <button type="button" className="secondary" onClick={() => insert('**', '**', tr('Важная мысль'))} disabled={uploading}><strong>{tr('Жирный')}</strong></button>
      <button type="button" className="secondary" onClick={() => insert('- ', '', tr('Пункт списка'), true)} disabled={uploading}>{tr('Список')}</button>
      <button type="button" className="secondary" onClick={() => insert('`', '`', 'print()')} disabled={uploading}>{tr('Код')}</button>
      <button type="button" className="secondary" onClick={() => fileInput.current?.click()} disabled={uploading || !imageTargetId}>{uploading ? tr('Загрузка изображения…') : tr('+ Изображение')}</button>
      <button type="button" className="secondary lesson-preview-toggle" aria-pressed={preview} disabled={uploading} onClick={() => setPreview(current => !current)}>{preview ? tr('Редактировать текст') : tr('Предпросмотр')}</button>
    </div>
    <input ref={fileInput} type="file" accept="image/png,image/jpeg" hidden aria-label={scope === 'course' ? tr('Изображение для описания курса') : tr('Изображение для урока')} onChange={event => { void upload(event.target.files?.[0]) }} />
    {!imageTargetId && <small className="muted">{scope === 'course' ? tr('Сначала сохраните курс, затем откройте его редактирование и добавьте изображения.') : tr('Сначала сохраните урок, чтобы добавить иллюстрацию.')}</small>}
    <textarea ref={textarea} id={id} name={name} value={text} hidden={preview} readOnly={uploading} rows={rows} maxLength={maxLength} spellCheck onChange={event => update(event.target.value)} />
    {preview && <div className="lesson-editor-preview">{text.trim() ? <RichLessonContent content={text} runId={runId} /> : <p className="muted">{scope === 'course' ? tr('Здесь появится описание курса.') : tr('Здесь появится материал урока.')}</p>}</div>}
    
    {error && <p className="error" role="alert">{tr(error)}</p>}
    {uploading && <p className="muted" role="status">{tr('Дождитесь завершения загрузки изображения.')}</p>}
  </div>
}
