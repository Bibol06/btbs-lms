import { ct } from '../i18n/content'
import { t as tr } from '../i18n/language'
import { useEffect, useState } from 'react'
import { apiRequest } from '../api'
import { errorMessage } from '../pages/study/types'

export default function WorkspaceSearch() {
  const [query, setQuery] = useState(''), [data, setData] = useState<{ kind: string; title: string; detail: string; target: string }[]>([])
  const [open, setOpen] = useState(false), [error, setError] = useState('')
  useEffect(() => {
    if (query.trim().length < 2) return
    let alive = true
    const timer = setTimeout(() => apiRequest<{ results: typeof data }>(`/api/workspace/search/?q=${encodeURIComponent(query)}`).then(v => { if (alive) { setData(v.results); setError('') } }).catch(e => { if (alive) setError(errorMessage(e)) }), 200)
    return () => { alive = false; clearTimeout(timer) }
  }, [query])
  useEffect(() => { const close = () => setOpen(false); window.addEventListener('hashchange', close); return () => window.removeEventListener('hashchange', close) }, [])
  return <div className="workspace-search" onBlur={e => { if (!e.currentTarget.contains(e.relatedTarget)) setOpen(false) }}><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></svg><input type="search" aria-label={tr("Поиск по платформе")} placeholder={tr("Найти курс или ученика…")} value={query} onChange={e => { setQuery(e.target.value); setOpen(true) }} onFocus={() => setOpen(true)} onKeyDown={e => { if (e.key === 'Escape') setOpen(false) }} />
    {open && query.trim().length >= 2 && <div className="workspace-search-results" aria-label={tr("Результаты поиска")}>{error && <p role="alert">{tr(error)}</p>}{!error && !data.length && <p>{tr("Совпадений пока нет.")}</p>}{data.map((r, i) => <a href={r.target} key={`${r.target}-${i}`} onClick={() => setOpen(false)}><span>{tr(r.kind)}</span><strong>{ct(r, "title")}</strong><small>{r.kind === 'Курс' ? tr(r.detail) : r.detail}</small></a>)}</div>}</div>
}
