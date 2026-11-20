import { useEffect, useId, useRef, useState } from 'react'
import { t } from '../i18n/language'
import './MoreMenu.css'

export type MoreMenuItem = { label: string; href?: string; onSelect?: () => void; danger?: boolean }

/** "⋯" button with a small menu of secondary actions (links or callbacks). */
export default function MoreMenu({ label, items, className = '' }: { label: string; items: MoreMenuItem[]; className?: string }) {
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const menuId = useId()
  useEffect(() => {
    if (!open) return
    box.current?.querySelector<HTMLElement>('[role=menuitem]')?.focus()
    const outside = (event: PointerEvent) => { if (!box.current?.contains(event.target as Node)) setOpen(false) }
    const keys = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { setOpen(false); trigger.current?.focus(); return }
      if (event.key === 'Tab') { setOpen(false); return }
      if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return
      const entries = Array.from(box.current?.querySelectorAll<HTMLElement>('[role=menuitem]') ?? [])
      const index = entries.indexOf(document.activeElement as HTMLElement)
      event.preventDefault()
      entries[(index + (event.key === 'ArrowDown' ? 1 : -1) + entries.length) % entries.length]?.focus()
    }
    document.addEventListener('pointerdown', outside)
    document.addEventListener('keydown', keys)
    return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', keys) }
  }, [open])
  if (!items.length) return null
  return <div className={`more-menu ${className}`} ref={box}>
    <button type="button" ref={trigger} className="more-menu-trigger" aria-haspopup="menu" aria-expanded={open} aria-controls={open ? menuId : undefined}
      aria-label={label} title={t('Ещё действия')} onClick={() => setOpen(value => !value)}>
      <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><circle cx="3" cy="8" r="1.5" /><circle cx="8" cy="8" r="1.5" /><circle cx="13" cy="8" r="1.5" /></svg>
    </button>
    {open && <div className="more-menu-popover" role="menu" id={menuId} aria-label={label}>
      {items.map(item => item.href
        ? <a key={item.label} role="menuitem" href={item.href} className={item.danger ? 'is-danger' : ''} onClick={() => setOpen(false)}>{item.label}</a>
        : <button key={item.label} type="button" role="menuitem" className={item.danger ? 'is-danger' : ''} onClick={() => { setOpen(false); item.onSelect?.() }}>{item.label}</button>)}
    </div>}
  </div>
}
