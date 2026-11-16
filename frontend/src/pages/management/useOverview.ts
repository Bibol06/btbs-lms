import { useEffect, useState } from 'react'
import { apiRequest } from '../../api'
import { errorMessage } from '../study/types'

export type RunOption = { id: number; course_id: number; title: string; course: string }
export type Overview = { scope: string; metrics: Record<string, number>; runs: RunOption[]; server_now: string }
export function useOverview(revision = 0) {
  const [data, setData] = useState<Overview | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let alive = true
    const load = () => apiRequest<Overview>('/api/study/management/overview/').then(value => { if (alive) { setData(value); setError('') } }).catch(err => { if (alive) setError(errorMessage(err)) })
    void load(); const timer = window.setInterval(load, 30000)
    return () => { alive = false; window.clearInterval(timer) }
  }, [revision])
  return { data, error }
}
