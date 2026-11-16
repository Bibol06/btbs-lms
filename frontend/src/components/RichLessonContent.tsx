import { Fragment, type ReactNode } from 'react'
import './LessonContent.css'

type Props = { content: string; runId?: number; className?: string }

function imageSource(value: string, runId?: number) {
  if (/^\/api\/courses\/images\/[1-9]\d*\/$/.test(value)) return value
  const match = value.match(/^\/api\/learning\/images\/([1-9]\d*)\/(?:\?run_id=\d+)?$/)
  return match ? `/api/learning/images/${match[1]}/${runId ? `?run_id=${runId}` : ''}` : null
}

function safeLink(value: string) {
  return /^https?:\/\/[^\s<>]+$/i.test(value) ? value : null
}

function inline(source: string, runId?: number): ReactNode[] {
  const token = /(`[^`\n]+`|(?<!\w)\*\*[^*\s](?:[^*\n]*[^*\s])?\*\*(?!\w)|(?<!\w)\*[^*\s](?:[^*\n]*[^*\s])?\*(?!\w)|!\[[^\]\n]*\]\([^)\n]+\)|\[[^\]\n]+\]\([^)\n]+\))/g
  const parts: ReactNode[] = []
  let offset = 0
  for (const match of source.matchAll(token)) {
    if (match.index! > offset) parts.push(source.slice(offset, match.index))
    const value = match[0]
    if (value.startsWith('`')) parts.push(<code key={match.index}>{value.slice(1, -1)}</code>)
    else if (value.startsWith('**')) parts.push(<strong key={match.index}>{value.slice(2, -2)}</strong>)
    else if (value.startsWith('*')) parts.push(<em key={match.index}>{value.slice(1, -1)}</em>)
    else if (value.startsWith('!')) {
      const image = value.match(/^!\[([^\]]*)\]\((.+)\)$/)!
      const src = imageSource(image[2], runId)
      parts.push(src ? <img key={match.index} src={src} alt={image[1]} loading="lazy" decoding="async" className="lesson-illustration" /> : value)
    } else {
      const link = value.match(/^\[([^\]]*)\]\((.+)\)$/)!
      const href = safeLink(link[2])
      parts.push(href ? <a key={match.index} href={href} target="_blank" rel="noopener noreferrer">{link[1]}</a> : value)
    }
    offset = match.index! + value.length
  }
  if (offset < source.length) parts.push(source.slice(offset))
  return parts
}

/** A small, safe authoring format. Raw HTML is always escaped as ordinary text. */
export default function RichLessonContent({ content, runId, className = '' }: Props) {
  const lines = content.replace(/\r\n/g, '\n').split('\n')
  const blocks: ReactNode[] = []
  for (let index = 0; index < lines.length;) {
    const line = lines[index]
    if (!line.trim()) { index++; continue }
    if (/^\s*```/.test(line)) {
      const language = line.trim().slice(3).trim()
      const start = index++
      const code: string[] = []
      while (index < lines.length && !/^\s*```\s*$/.test(lines[index])) code.push(lines[index++])
      if (index < lines.length) index++
      blocks.push(<pre key={start} className="lesson-code" data-language={language || undefined}><code>{code.join('\n')}</code></pre>)
      continue
    }
    const heading = line.match(/^(#{1,3})\s+(.+)$/)
    if (heading) {
      const text = inline(heading[2], runId)
      blocks.push(heading[1].length === 1 ? <h2 key={index}>{text}</h2> : heading[1].length === 2 ? <h3 key={index}>{text}</h3> : <h4 key={index}>{text}</h4>)
      index++; continue
    }
    if (/^\s*[-*]\s+/.test(line) || /^\s*\d+[.)]\s+/.test(line)) {
      const ordered = /^\s*\d+[.)]\s+/.test(line)
      const rule = ordered ? /^\s*\d+[.)]\s+/ : /^\s*[-*]\s+/
      const start = index
      const items: ReactNode[] = []
      while (index < lines.length && rule.test(lines[index])) {
        items.push(<li key={index}>{inline(lines[index].replace(rule, ''), runId)}</li>); index++
      }
      blocks.push(ordered ? <ol key={start}>{items}</ol> : <ul key={start}>{items}</ul>)
      continue
    }
    const image = line.match(/^!\[([^\]]*)\]\(([^)]+)\)\s*$/)
    if (image && imageSource(image[2], runId)) {
      blocks.push(<figure key={index}><img src={imageSource(image[2], runId)!} alt={image[1]} loading="lazy" decoding="async" className="lesson-illustration" />{image[1] && <figcaption>{image[1]}</figcaption>}</figure>)
      index++; continue
    }
    const paragraph: string[] = [line]
    const start = index++
    while (index < lines.length && lines[index].trim() && !/^(#{1,3}\s|\s*```|\s*[-*]\s|\s*\d+[.)]\s|!\[)/.test(lines[index])) paragraph.push(lines[index++])
    blocks.push(<p key={start}>{paragraph.map((text, offset) => <Fragment key={offset}>{offset > 0 && <br />}{inline(text, runId)}</Fragment>)}</p>)
  }
  return <div className={`rich-lesson-content ${className}`} translate="no">{blocks}</div>
}
