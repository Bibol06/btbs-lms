import { apiRequest } from './api'
import { t } from './i18n/language'

const chunkSize = 8 * 1024 * 1024
const check = (signal: AbortSignal) => { if (signal.aborted) throw new DOMException('Aborted', 'AbortError') }
const hex = (buffer: ArrayBuffer) => Array.from(new Uint8Array(buffer), n => n.toString(16).padStart(2, '0')).join('')

async function fingerprint(file: File, signal: AbortSignal) {
  // Hash every byte with bounded memory; equal names/sizes alone are not sufficient.
  const hashes: string[] = []
  for (let offset = 0; offset < file.size; offset += chunkSize) {
    check(signal)
    hashes.push(hex(await crypto.subtle.digest('SHA-256', await file.slice(offset, offset + chunkSize).arrayBuffer())))
  }
  check(signal)
  return hex(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(`${file.size}:${hashes.join(':')}`)))
}

async function putPart(url: string, data: Blob, signal: AbortSignal, onProgress: (bytes: number) => void) {
  check(signal)
  await new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    const abort = () => xhr.abort()
    const finish = (error?: Error) => { signal.removeEventListener('abort', abort); if (error) reject(error); else resolve() }
    xhr.open('PUT', url)
    xhr.timeout = 120000
    xhr.upload.onprogress = event => onProgress(event.loaded)
    xhr.onload = () => finish(xhr.status >= 200 && xhr.status < 300 ? undefined : new Error(t('Не удалось загрузить часть видео. Повторите загрузку.')))
    xhr.onerror = xhr.ontimeout = () => finish(new Error(t('Не удалось загрузить часть видео. Повторите загрузку.')))
    xhr.onabort = () => finish(new DOMException('Aborted', 'AbortError'))
    signal.addEventListener('abort', abort, { once: true })
    if (signal.aborted) { finish(new DOMException('Aborted', 'AbortError')); return }
    xhr.send(data)
  })
}

export async function uploadMultipart(lessonId: number, file: File, title: string, signal: AbortSignal, progress: (percent: number) => void) {
  const hash = await fingerprint(file, signal)
  check(signal)
  const start = await apiRequest<{ id: string; part_size: number }>(`/api/media/lessons/${lessonId}/uploads/`, 'POST', { filename: file.name, size: file.size, title, multipart: true, fingerprint: hash })
  const base = `/api/media/uploads/${start.id}`
  const status = await apiRequest<{ parts: { number: number; size: number }[]; assembled: boolean }>(`${base}/parts/`)
  if (!status.assembled) {
    const saved = new Map(status.parts.map(part => [part.number, part.size]))
    let completed = 0
    for (let n = 1; n <= Math.ceil(file.size / start.part_size); n++) {
      const data = file.slice((n-1)*start.part_size, n*start.part_size)
      if (saved.get(n) === data.size) completed += data.size
    }
    progress(Math.min(94, Math.round(completed / file.size * 94)))
    for (let n = 1; n <= Math.ceil(file.size / start.part_size); n++) {
      check(signal)
      const data = file.slice((n-1)*start.part_size, n*start.part_size)
      if (saved.get(n) === data.size) continue
      for (let attempt = 0; ; attempt++) {
        try {
          check(signal)
          const signed = await apiRequest<{ url: string }>(`${base}/parts/`, 'POST', { number: n })
          await putPart(signed.url, data, signal, bytes => progress(Math.min(94, Math.round((completed + bytes) / file.size * 94))))
          break
        } catch (error) {
          check(signal)
          if (attempt >= 2) throw error
        }
      }
      completed += data.size
    }
  }
  check(signal)
  progress(95)
  const result = await apiRequest<{ material: { id: number; title: string; url: string; kind: string } }>(`${base}/complete/`, 'POST', {})
  progress(100)
  return result.material
}
