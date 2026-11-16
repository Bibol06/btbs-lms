import { t } from '../i18n/language'
import './DiscussionBody.css'

/** Translations are for reading; callers keep the original for editing and saving. */
export default function PreparedText({ original, text, redacted = false, compact = false, className = '' }: {
  original: string; text: string; redacted?: boolean; compact?: boolean; className?: string
}) {
  const translated = !redacted && text !== original
  return <div className={`discussion-text ${className}`} translate="no">
    <p className="preserve-text">{text}</p>
    {translated && (compact ? <small className="discussion-translation-label">{t('Перевод')}</small> :
      <details className="discussion-original">
        <summary>{t('Перевод · Показать оригинал')}</summary>
        <p className="preserve-text">{original}</p>
      </details>)}
    {!redacted && !translated && <small className="discussion-translation-label">{t('Оригинал сообщения')}</small>}
  </div>
}
