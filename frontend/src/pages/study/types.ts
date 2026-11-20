import { t as tr } from '../../i18n/language'
import { localDate } from '../../i18n/dates'
export type Submission = {
  review_version: number; rubric_result?: { version: number; criteria: { id: string; label: string; max: number; score: number; comment: string }[] }
  id: number; student_id: number; student: string; student_role_label: string; attempt_no: number; text_answer: string
  file_url: string; file_name: string; submitted_at: string; score: number | null
  feedback: string; graded_at: string | null; status: string; reviews: { rubric_result?: Submission['rubric_result']; action: string; score: number | null; feedback: string; created_at: string; reviewer__username: string; reviewer: string; reviewer_role_label: string }[]
  is_late: boolean; due_at_snapshot: string | null; review_due_at: string | null; review_state: string
  reviewer_id: number | null; reviewer: string | null; reviewer_role_label: string; revision_due_at: string | null
}
export type SubmissionWindow = { due_at: string | null; closes_at: string | null; allow_late: boolean; source: string; note: string; phase: string; can_submit: boolean }
export type Reviewer = { id: number; username: string; display_name: string; role_label: string; first_name: string; last_name: string }
export type Assignment = {
  id: number; title: string; description: string; due_at: string | null
  max_score: number; max_attempts: number; is_published: boolean; submissions: Submission[]
  allow_late: boolean; cutoff_at: string | null; review_hours: number; window: SubmissionWindow | null
}
export type Question = { id?: number; body: string; options: string[]; correct_index: number }
export type Attempt = {
  id: number; attempt_no: number; status: 'active' | 'finished' | 'expired'
  score: number; max_score: number; deadline_at: string; finished_at: string | null
  auto_submitted: boolean; server_now: string
}
export type Quiz = {
  id: number; title: string; max_attempts: number; time_limit_sec: number
  opens_at: string | null; closes_at: string | null; is_published: boolean
  questions_count: number; questions?: Question[]; attempts: Attempt[]; has_attempts: boolean
}
export type StudyData = {
  reviewers: Reviewer[]
  assignments: Assignment[]; quizzes: Quiz[]; can_manage: boolean; can_edit: boolean
  code_results: { id: number; title: string; passed: number | null; total: number }[]
  progress: { completed: number; total: number; percent: number }
}
export function formatDate(value: string | null) {
  // Minutes are enough for deadlines and activity; seconds were noise (QA-026).
  return value ? localDate(new Date(value), 'datetime') : tr("Без ограничения")
}
export function inputDate(value: string | null | undefined) {
  if (!value) return ''
  const date = new Date(value)
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}
export function isoDate(value: FormDataEntryValue | null) {
  return value ? new Date(String(value)).toISOString() : null
}
export function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : tr("Ошибка соединения")
}
