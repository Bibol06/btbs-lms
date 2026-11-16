import { useState, useRef, useEffect } from 'react'
import { chooseLanguage, languages, t, useLanguage } from '../i18n/language'
import './LanguageSwitcher.css'

export default function LanguageSwitcher({ full = false }: { full?: boolean }) {
  const { language, saving, error } = useLanguage()
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null), trigger = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (!open) return
    box.current?.querySelector<HTMLButtonElement>('button[aria-pressed="true"]')?.focus()
    function outside(event: PointerEvent) { if (!box.current?.contains(event.target as Node)) setOpen(false) }
    function escape(event: KeyboardEvent) { if (event.key === 'Escape') { setOpen(false); trigger.current?.focus() } }
    document.addEventListener('pointerdown', outside); document.addEventListener('keydown', escape)
    return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', escape) }
  }, [open])
  const current = languages.find(item => item.code === language)!
  return <div className={`language-switcher ${full ? 'language-full' : ''}`} ref={box}>
    <button type="button" ref={trigger} className="language-trigger" title={`${t('Язык платформы')}: ${current.name}`} aria-label={`${t('Язык платформы')}: ${current.name}`} aria-busy={saving} aria-expanded={open} aria-haspopup="dialog" onClick={() => setOpen(value => !value)}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><circle cx="12" cy="12" r="9" /><ellipse cx="12" cy="12" rx="4" ry="9" /><path d="M3 12h18M5 7h14M5 17h14" /></svg>
      <span>{full ? current.name : current.short}</span><span className="language-chevron" aria-hidden="true">⌄</span>
    </button>
    {open && <div className="language-popover" role="dialog" aria-label={t('Выбор языка')}><strong>{t('Язык платформы')}</strong><div role="group" aria-label={t('Доступные языки')}>{languages.map(item => <button type="button" key={item.code} lang={item.code} aria-pressed={item.code === language} onClick={() => { void chooseLanguage(item.code); setOpen(false); trigger.current?.focus() }}><span>{item.name}</span><small>{item.short}</small>{item.code === language && <span aria-hidden="true">✓</span>}</button>)}</div></div>}
    {error && <span className="language-save-error" role="status">{t('Язык сохранён на устройстве.')} <button type="button" onClick={() => void chooseLanguage(language)}>{t('Повторить сохранение в профиль')}</button></span>}
    
  </div>
}
