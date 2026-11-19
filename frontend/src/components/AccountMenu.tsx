import { useEffect, useRef, useState } from 'react'
import { chooseLanguage, languages, t, useLanguage } from '../i18n/language'

type Props = { name: string; roleLabel: string; onProfile: () => void; onLogout: () => void }

/** Avatar button with the personal menu: profile, interface language and sign-out. */
export default function AccountMenu({ name, roleLabel, onProfile, onLogout }: Props) {
  const [open, setOpen] = useState(false)
  const { language, saving } = useLanguage()
  const box = useRef<HTMLDivElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (!open) return
    box.current?.querySelector<HTMLElement>('[role=menuitem], [role=menuitemradio]')?.focus()
    const outside = (event: PointerEvent) => { if (!box.current?.contains(event.target as Node)) setOpen(false) }
    const keys = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { setOpen(false); trigger.current?.focus(); return }
      if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return
      const items = Array.from(box.current?.querySelectorAll<HTMLElement>('[role=menuitem], [role=menuitemradio]') ?? [])
      const index = items.indexOf(document.activeElement as HTMLElement)
      event.preventDefault()
      items[(index + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length]?.focus()
    }
    document.addEventListener('pointerdown', outside)
    document.addEventListener('keydown', keys)
    return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', keys) }
  }, [open])
  const initial = name.trim()[0]?.toUpperCase() ?? '?'
  const run = (action: () => void) => () => { setOpen(false); action() }
  return <div className="account-menu" ref={box}>
    <button type="button" ref={trigger} className="account-trigger" aria-haspopup="menu" aria-expanded={open} aria-label={t('Меню аккаунта: {0}', [name])} onClick={() => setOpen(v => !v)}>
      <span className="avatar" aria-hidden="true">{initial}</span><span className="account-chevron" aria-hidden="true">⌄</span>
    </button>
    {open && <div className="account-popover" role="menu" aria-label={t('Аккаунт')}>
      <div className="account-identity"><span className="avatar avatar-md" aria-hidden="true">{initial}</span><span><strong>{name}</strong><small>{roleLabel}</small></span></div>
      <button type="button" role="menuitem" onClick={run(onProfile)}>{t('Мой профиль')}</button>
      <div className="account-section" role="group" aria-label={t('Язык платформы')} aria-busy={saving}>
        <span className="account-section-title">{t('Язык платформы')}</span>
        {languages.map(item => <button type="button" role="menuitemradio" aria-checked={item.code === language} key={item.code} lang={item.code} onClick={run(() => { void chooseLanguage(item.code) })}>
          <span>{item.name}</span>{item.code === language && <span aria-hidden="true">✓</span>}
        </button>)}
      </div>
      <button type="button" role="menuitem" className="account-logout" onClick={run(onLogout)}>{t('Выйти')}</button>
    </div>}
  </div>
}
