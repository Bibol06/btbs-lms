import { apiRequest } from '../../api'
import { errorMessage } from '../study/types'

type Choice = { id: number; title: string }
export type StepChoices = { assignments: Choice[]; quizzes: Choice[]; problems: Choice[]; materials: Choice[] }

/** A failed file or Python endpoint must not discard successfully loaded quizzes. */
export async function loadStepChoices(courseId: number, runId: number, lessonId: number) {
  const [study, code, lessons] = await Promise.allSettled([
    apiRequest<{ assignments: Choice[]; quizzes: Choice[] }>(`/api/study/courses/${courseId}/?run_id=${runId}`),
    apiRequest<{ problems: Choice[] }>(`/api/code/courses/${courseId}/problems/?run_id=${runId}`),
    apiRequest<{ lessons: { id: number; materials: Choice[] }[] }>(`/api/learning/courses/${courseId}/lessons/?run_id=${runId}`),
  ])
  const choices: Partial<StepChoices> = {}
  if (study.status === 'fulfilled') { choices.assignments = study.value.assignments; choices.quizzes = study.value.quizzes }
  if (code.status === 'fulfilled') choices.problems = code.value.problems
  if (lessons.status === 'fulfilled') choices.materials = lessons.value.lessons.find(lesson => lesson.id === lessonId)?.materials ?? []
  return { choices, errors: {
    study: study.status === 'rejected' ? errorMessage(study.reason) : '',
    code: code.status === 'rejected' ? errorMessage(code.reason) : '',
    file: lessons.status === 'rejected' ? errorMessage(lessons.reason) : '',
  } }
}
