import { t as tr } from '../../i18n/language'
import { useCallback, useEffect, useState } from 'react'
import { apiRequest } from '../../api'
import { type StudyData, errorMessage } from './types'
import Assignments from './Assignments'
import Quizzes from './Quizzes'
import Results from './Results'
import './Study.css'
import './Deadlines.css'

export default function StudyPanel({ courseId, runId, tab, activityId }: { courseId: number; runId: number; tab: 'assignments' | 'quizzes' | 'results'; activityId?: number }) {
  const [data, setData] = useState<StudyData | null>(null)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  const refresh = useCallback(() => setRevision(v => v + 1), [])
  useEffect(() => {
    let alive = true
    apiRequest<StudyData>(`/api/study/courses/${courseId}/?run_id=${runId}`)
      .then(value => { if (alive) { setData(value); setError('') } })
      .catch(err => { if (alive) setError(errorMessage(err)) })
    return () => { alive = false }
  }, [courseId, runId, revision])
  if (error) return <div><p role="alert" className="error">{tr(error)}</p><button onClick={refresh}>{tr("Повторить")}</button></div>
  if (!data) return <p>{tr("Загрузка…")}</p>
  const selectedActivity = activityId ?? (Number(new URLSearchParams(location.hash.slice(1)).get('activity')) || undefined)
  if (tab === 'assignments') return <Assignments courseId={courseId} runId={runId} reviewers={data.reviewers} assignments={selectedActivity ? data.assignments.filter(a => a.id === selectedActivity) : data.assignments} manage={data.can_manage} canEdit={data.can_edit} refresh={refresh} embedded={activityId !== undefined} />
  if (tab === 'quizzes') return <Quizzes courseId={courseId} runId={runId} quizzes={selectedActivity ? data.quizzes.filter(q => q.id === selectedActivity) : data.quizzes} manage={data.can_manage} canEdit={data.can_edit} refresh={refresh} />
  return <Results key={revision} courseId={courseId} runId={runId} data={data} manage={data.can_manage} />
}
