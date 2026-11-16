import { ct } from './content'
import { t } from './language'

export type DiscussionText = { body: string; is_redacted?: boolean }

/** All discussion surfaces and reply quotes use the same display-only text. */
export function discussionText(comment: DiscussionText): string {
  return comment.is_redacted ? t('Комментарий скрыт модератором') : ct(comment, 'body')
}
