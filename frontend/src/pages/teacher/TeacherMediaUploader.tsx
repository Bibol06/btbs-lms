import { ct } from '../../i18n/content'
import { readApiJson } from '../../i18n/contentStore'
import { t as tr } from '../../i18n/language'

import { useEffect, useRef, useState, type FormEvent } from 'react'
import { uploadLessonFile } from '../../mediaUpload'
import './TeacherMediaUploader.css'

type Lesson = {
  id: number
  title: string
  position: number
}

type Props = {
  courseId: number
  onUploaded?: () => void
}

type Material = {
  id: number
  title: string
  url: string
  kind: string
}

function TeacherMediaUploader({ courseId, onUploaded }: Props) {
  const [open, setOpen] = useState(false)
  const [lessons, setLessons] = useState<Lesson[]>([])
  const [lessonId, setLessonId] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [uploaded, setUploaded] = useState<Material | null>(null)

  const fileInput = useRef<HTMLInputElement>(null)
  const uploadAbort = useRef<AbortController | null>(null)
  const [progress, setProgress] = useState(0)
  useEffect(() => () => uploadAbort.current?.abort(), [])

  async function toggleUploader() {
    if (open) {
      setOpen(false)
      return
    }

    setOpen(true)
    setLoading(true)
    setError('')
    setUploaded(null)

    try {
      const response = await fetch(
        `/api/learning/courses/${courseId}/lessons/`,
        { credentials: 'include' }
      )

      if (!response.ok) {
        throw new Error(tr("Не удалось загрузить уроки"))
      }

      const data = await readApiJson(response)
      setLessons(data.lessons)
      setLessonId(String(data.lessons[0]?.id ?? ''))
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Ошибка'
      )
    } finally {
      setLoading(false)
    }
  }

  async function uploadFile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (!file || !lessonId) {
      setError('Выберите урок и файл')
      return
    }

    setUploading(true)
    setError('')
    setMessage('')

    try {
      const controller = new AbortController()
      uploadAbort.current = controller
      setProgress(0)
      const material = await uploadLessonFile(Number(lessonId), file, title, controller.signal, setProgress)
      setUploaded(material)
      setMessage('Файл успешно загружен!')
      setFile(null)
      setTitle('')

      if (fileInput.current) {
        fileInput.current.value = ''
      }
      onUploaded?.()
    } catch (err) {
      setError(
        err instanceof DOMException && err.name === 'AbortError' ? tr('Загрузка отменена') : err instanceof Error ? err.message : 'Ошибка загрузки'
      )
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="media-uploader">
      <button
        type="button"
        className="media-toggle"
        onClick={toggleUploader}
        disabled={uploading}
      >
        {open ? tr("Закрыть загрузку") : tr("+ Загрузить файл / видео")}
      </button>

      {uploading && <div role="status"><progress max={100} value={progress} /><span>{progress >= 95 ? tr('Проверяем загруженный файл…') : tr('Загрузка: {0}%', [progress])}</span><button type="button" className="secondary" disabled={progress >= 95} onClick={() => uploadAbort.current?.abort()}>{tr('Отменить загрузку')}</button></div>}
      {open && (
        <div className="media-panel">
          <h3>{tr("Загрузка материалов")}</h3>

          {loading ? (
            <p>{tr("Загрузка уроков...")}</p>
          ) : (
            <form onSubmit={uploadFile}>
              <label htmlFor={`lesson-${courseId}`}>
                {tr("Выберите урок")}</label>

              <select
                id={`lesson-${courseId}`}
                disabled={uploading}
                value={lessonId}
                onChange={e => {
                  setLessonId(e.target.value)
                  setUploaded(null)
                }}
                required
              >
                <option value="">{tr("Выберите урок")}</option>

                {lessons.map(lesson => (
                  <option key={lesson.id} value={lesson.id}>
                    {lesson.position}. {ct(lesson, "title")}
                  </option>
                ))}
              </select>

              <label htmlFor={`material-title-${courseId}`}>
                {tr("Название материала")}</label>

              <input
                id={`material-title-${courseId}`}
                disabled={uploading}
                type="text"
                placeholder={tr("Необязательно")}
                value={title}
                maxLength={200}
                onChange={e => setTitle(e.target.value)}
              />

              <label htmlFor={`material-file-${courseId}`}>
                {tr("Файл с компьютера")}</label>

              <input
                ref={fileInput}
                id={`material-file-${courseId}`}
                disabled={uploading}
                type="file"
                accept=".pdf,.doc,.docx,.ppt,.pptx,.mp4,.webm,.jpg,.jpeg,.png"
                onChange={e => {
                  setFile(e.target.files?.[0] ?? null)
                  setUploaded(null)
                }}
              />

              {file && (
                <div className="selected-file">
                  {tr("Выбран: ")}{file.name}
                  <p>
                    {tr("Размер: ")}{(file.size / 1024 / 1024).toFixed(2)} {tr(" МБ")}</p>
                </div>
              )}
              {file && file.size > 20*1024*1024 && <p>{tr('Если загрузка прервалась, выберите тот же файл и нажмите «Загрузить материал». При включённой загрузке частями уже отправленные части сохраняются 24 часа.')}</p>}

              <button
                className="media-submit"
                type="submit"
                disabled={uploading || !file || !lessonId}
              >
                {uploading ? tr("Загрузка...") : tr("Загрузить материал")}
              </button>
            </form>
          )}

          {message && <p className="media-success">{tr(message)}</p>}
          {error && <p className="media-error">{tr(error)}</p>}

          {uploaded && (
            <a
              href={uploaded.url}
              target="_blank"
              rel="noopener noreferrer"
              className="media-preview"
            >
              {tr("Открыть загруженный файл: ")}{ct(uploaded, "title")}
            </a>
          )}
        </div>
      )}
    </div>
  )
}

export default TeacherMediaUploader
