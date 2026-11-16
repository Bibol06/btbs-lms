import { t } from './language'
import { ct } from './content'

const auditLabels: Record<string, string> = {
  'announcement.updated': 'Изменил объявление', 'conversation.participant_added': 'Добавил участника диалога',
  'comment.moderated': 'Изменил видимость комментария', 'submission.reviewer_assigned': 'Назначил ответственного или срок проверки',
  'assignment.deadline_extended': 'Продлил срок ученику', 'schedule.updated': 'Изменил расписание',
  'run.updated': 'Изменил настройки группы', 'team.changed': 'Изменил команду курса',
  'enrollment.status_changed': 'Изменил доступ ученика', 'question.status_changed': 'Изменил статус вопроса',
  'attention.policy_updated': 'Изменил правила внимания', 'assignment.rubric_updated': 'Изменил критерии оценки',
  'question_bank.saved': 'Сохранил вопрос в банк', 'course.cloned': 'Скопировал курс',
}
export function auditCaption(code: string) { return t(auditLabels[code] || code) }
export function runTitle(source: string) { return ct(source) }
export function stepKindCaption(kind: string) {
  const labels: Record<string, string> = { text: 'Текст', video: 'Видео', file: 'Файл', assignment: 'Задание', quiz: 'Тест', code: 'Python' }
  return t(labels[kind] || kind)
}
