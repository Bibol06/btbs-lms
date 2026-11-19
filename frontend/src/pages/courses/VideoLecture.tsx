import { useEffect, useMemo, useRef, useState } from 'react'
import { t as tr } from '../../i18n/language'
import { parseTranscript } from './transcript'

function clock(seconds: number) {
  const m = Math.floor(seconds / 60), s = Math.floor(seconds % 60)
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

function youtubeId(url: string) {
  try {
    const u = new URL(url)
    if (u.hostname === 'youtu.be') return u.pathname.slice(1).split('/')[0] || null
    if (!/(^|\.)youtube(-nocookie)?\.com$/.test(u.hostname)) return null
    if (u.searchParams.get('v')) return u.searchParams.get('v')
    const parts = u.pathname.split('/').filter(Boolean)
    return ['embed', 'shorts', 'live'].includes(parts[0]) ? parts[1] ?? null : null
  } catch { return null }
}

type Player = { seek: (seconds: number) => void }

export default function VideoLecture({ url, transcript, title, panelOpen }: { url: string; transcript: string; title: string; panelOpen: boolean }) {
  const chapters = useMemo(() => parseTranscript(transcript), [transcript])
  const [time, setTime] = useState(0)
  const player = useRef<Player | null>(null)
  const frame = useRef<HTMLIFrameElement>(null)
  const video = useRef<HTMLVideoElement>(null)
  const list = useRef<HTMLOListElement>(null)
  const id = youtubeId(url)
  const direct = !id && /\.(mp4|webm)(\?|#|$)/i.test(url)
  useEffect(() => {
    if (!id) return
    // YouTube iframe postMessage protocol: subscribe to currentTime, send seek commands.
    const send = (message: object) => frame.current?.contentWindow?.postMessage(JSON.stringify({ ...message, id: 1, channel: 'widget' }), '*')
    player.current = { seek: seconds => { send({ event: 'command', func: 'seekTo', args: [seconds, true] }); send({ event: 'command', func: 'playVideo', args: [] }) } }
    const receive = (event: MessageEvent) => {
      if (!/^https:\/\/www\.youtube(-nocookie)?\.com$/.test(event.origin) || typeof event.data !== 'string') return
      try {
        const data = JSON.parse(event.data)
        if (data.event === 'infoDelivery' && typeof data.info?.currentTime === 'number') setTime(data.info.currentTime)
      } catch { /* not a player message */ }
    }
    window.addEventListener('message', receive)
    const listen = window.setInterval(() => send({ event: 'listening' }), 1000)
    return () => { window.removeEventListener('message', receive); window.clearInterval(listen); player.current = null }
  }, [id])
  useEffect(() => {
    if (!direct) return
    player.current = { seek: seconds => { if (video.current) { video.current.currentTime = seconds; void video.current.play().catch(() => undefined) } } }
    return () => { player.current = null }
  }, [direct])
  const current = chapters.reduce((found, chapter, index) => chapter.start <= time + 0.5 ? index : found, 0)
  useEffect(() => {
    const item = list.current?.children[current] as HTMLElement | undefined
    if (item && list.current && !list.current.matches(':hover')) item.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [current])
  const seekable = Boolean(id || direct)
  return <div className={`video-lecture ${panelOpen && chapters.length ? '' : 'video-lecture-wide'}`}>
    {panelOpen && chapters.length > 0 && <aside className="video-transcript" aria-label={tr("Транскрипт")}>
      <h3>{tr("Транскрипт")}</h3>
      <ol ref={list}>{chapters.map((chapter, index) => {
        const end = chapters[index + 1]?.start
        return <li key={index} className={index === current ? 'is-current' : ''}>
          <button type="button" disabled={!seekable} onClick={() => player.current?.seek(chapter.start)} aria-current={index === current ? 'time' : undefined}>
            <span className="video-chapter-head"><strong>{index + 1}. {chapter.title || tr("Начало")}</strong><span className="video-chapter-time">{clock(chapter.start)}{end !== undefined ? ` – ${clock(end)}` : ''}</span></span>
            {chapter.text && <span className="video-chapter-text">{chapter.text}</span>}
          </button>
        </li>
      })}</ol>
    </aside>}
    <div className="video-stage">
      {id ? <iframe ref={frame} title={title} src={`https://www.youtube-nocookie.com/embed/${encodeURIComponent(id)}?enablejsapi=1&rel=0&modestbranding=1&origin=${encodeURIComponent(location.origin)}`} allow="autoplay; encrypted-media; picture-in-picture; fullscreen" referrerPolicy="strict-origin-when-cross-origin" />
        : direct ? <video ref={video} src={url} controls preload="metadata" onTimeUpdate={e => setTime(e.currentTarget.currentTime)} />
        : <div className="video-external"><p>{tr("Это видео открывается на сайте источника.")}</p><a className="button-link" href={url} target="_blank" rel="noreferrer">{tr("Смотреть видео →")}</a></div>}
    </div>
  </div>
}
