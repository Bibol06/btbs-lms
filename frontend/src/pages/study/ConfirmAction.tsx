import { ct } from '../../i18n/content'
import { t as tr } from '../../i18n/language'
import { useState } from 'react'

export default function ConfirmAction({ label, question, onConfirm, disabled = false }: {
  label: string; question: string; onConfirm: () => void; disabled?: boolean
}) {
  const [open, setOpen] = useState(false)
  if (!open) return <button type="button" className="danger" disabled={disabled} onClick={() => setOpen(true)}>{ct(label)}</button>
  return <span className="confirm-action" role="group" aria-label={tr("Подтверждение действия")}>
    <span>{question}</span>
    <button type="button" className="danger" disabled={disabled} onClick={() => { setOpen(false); onConfirm() }}>{tr("Подтвердить")}</button>
    <button type="button" className="secondary" disabled={disabled} onClick={() => setOpen(false)}>{tr("Отмена")}</button>
  </span>
}
