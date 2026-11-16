import { discussionText, type DiscussionText } from '../i18n/discussion'
import PreparedText from './PreparedText'

export default function DiscussionBody({ comment, compact = false, className = '' }: {
  comment: DiscussionText; compact?: boolean; className?: string
}) {
  return <PreparedText original={comment.body} text={discussionText(comment)} redacted={comment.is_redacted} compact={compact} className={className} />
}
