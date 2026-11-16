import './RoleBadge.css'
import { t } from '../i18n/language'

export default function RoleBadge({ label }: { label?: string | null }) {
  if (!label) return null
  return <span className="person-role">{t(label)}</span>
}
