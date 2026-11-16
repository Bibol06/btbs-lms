import { useState } from 'react'
import { t } from '../i18n/language'
import './MaterialViewer.css'

type Material = { title: string; url: string; kind?: string; filename?: string }
export default function MaterialViewer({ material }: { material: Material }) {
  const [expanded, setExpanded] = useState(false)
  const extension = (material.filename || material.title).split('.').pop()?.toLowerCase()
  // Only application-owned endpoints are embedded; never execute uploaded HTML/SVG.
  const safe = /^\/api\/(learning\/materials\/\d+\/open\/|study\/)/.test(material.url)
  if (!safe) return <p>{t('Материал недоступен')}</p>
  const video = material.kind === 'video' || ['mp4', 'webm'].includes(extension || '')
  const image = ['png', 'jpg', 'jpeg', 'gif', 'webp'].includes(extension || '')
  return <section className={`material-viewer ${expanded ? 'material-viewer-expanded' : ''}`} aria-label={material.title}>
    <header><div><small>{t('Материалы курса')}</small><strong>{material.title}</strong></div>
      <button type="button" className="secondary" aria-pressed={expanded} onClick={() => setExpanded(!expanded)}>{expanded ? t('Свернуть') : t('Развернуть')}</button></header>
    <div className="material-viewer-body">
      {video ? <video key={material.url} src={material.url} controls preload="metadata" />
        : image ? <img src={material.url} alt={material.title} loading="lazy" />
        : extension === 'pdf' ? <iframe key={material.url} src={material.url} title={material.title} referrerPolicy="no-referrer" />
        : <div className="material-viewer-placeholder"><strong>{t('Предпросмотр недоступен для этого формата')}</strong><p>{t('Сохраните файл, чтобы открыть его на устройстве.')}</p><a className="button-link" href={material.url} download>{t('Скачать файл')}</a></div>}
    </div>
  </section>
}
