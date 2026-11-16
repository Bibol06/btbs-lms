import { apiRequest, ensureCsrf, getCookie } from './api'
import { readApiJson } from './i18n/contentStore'
import { t } from './i18n/language'
import { uploadMultipart } from './multipartUpload'

export async function uploadLessonFile(lessonId: number, file: File, title: string,
  signal: AbortSignal, progress: (percent: number) => void) {
  const config = await apiRequest<{ direct_upload: boolean; multipart_upload: boolean; video_limit_mb: number; document_limit_mb: number }>('/api/media/config/')
  const limit = /\.(mp4|webm)$/i.test(file.name) ? config.video_limit_mb : config.document_limit_mb
  if (file.size > limit*1024*1024 || file.size === 0) throw new Error(t('Размер файла превышает лимит: {0} МБ', [limit]))
  if (signal.aborted) throw new DOMException('Aborted', 'AbortError')
  if (config.multipart_upload && file.size > 20*1024*1024) return uploadMultipart(lessonId, file, title, signal, progress)
  let pending: string | null = null
  try {
    let url: string, headers: Record<string, string> = {}
    const form = new FormData()
    if (config.direct_upload) {
      const start = await apiRequest<{ id: string; upload: { url: string; fields: Record<string, string> } }>(`/api/media/lessons/${lessonId}/uploads/`, 'POST', { filename: file.name, size: file.size, title })
      pending = start.id; url = start.upload.url
      Object.entries(start.upload.fields).forEach(([key, value]) => form.append(key, value))
    } else {
      await ensureCsrf(); url = `/api/learning/teacher/lessons/${lessonId}/materials/`
      headers = { 'X-CSRFToken': getCookie('csrftoken') }; form.append('title', title)
    }
    form.append('file', file)
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError')
    const response = await new Promise<XMLHttpRequest>((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      const abort = () => xhr.abort()
      xhr.open('POST', url); xhr.withCredentials = !config.direct_upload
      Object.entries(headers).forEach(([key, value]) => xhr.setRequestHeader(key, value))
      xhr.upload.onprogress = event => { if (event.lengthComputable) progress(Math.min(95, Math.round(95*event.loaded/event.total))) }
      xhr.onload = () => { signal.removeEventListener('abort', abort); if (xhr.status >= 200 && xhr.status < 300) resolve(xhr); else reject(new Error(config.direct_upload ? t('Загрузка в S3 не завершена. Проверьте CORS и соединение.') : (() => { try { return JSON.parse(xhr.responseText).error } catch { return t('Ошибка загрузки') } })())) }
      xhr.onerror = () => { signal.removeEventListener('abort', abort); reject(new Error(t('Не удалось загрузить файл. Проверьте соединение.'))) }
      xhr.onabort = () => { signal.removeEventListener('abort', abort); reject(new DOMException('Aborted', 'AbortError')) }
      signal.addEventListener('abort', abort, { once: true }); xhr.send(form)
    })
    if (pending) {
      const result = await apiRequest<{ material: { id: number; title: string; url: string; kind: string } }>(`/api/media/uploads/${pending}/complete/`, 'POST', {})
      pending = null; progress(100); return result.material
    }
    progress(100)
    return (await readApiJson(new Response(response.responseText, { headers: { 'Content-Type': 'application/json' } }))).material
  } finally {
    if (pending) await apiRequest(`/api/media/uploads/${pending}/abort/`, 'POST', {}).catch(() => {})
  }
}
