import { useEffect, useState } from 'react'
import { apiRequest } from '../../api'
import { errorMessage } from '../study/types'

export type Task = { id: string; title: string; course: string; run: string; state: string; due_at: string | null; target: string }
export type HomeData = {
  role: string; resume?: { enrollment_id: number; title: string; lesson: string; target: string } | null; tasks?: Task[]
  feedback?: { id: number; title: string; teacher: string; body: string; score: number | null; max_score: number; target: string; state: string; created_at: string }[]
  works?: { id: number; assignment: string; student: string; run: string; review_state: string; target: string; review_due_at: string | null }[]
  questions?: { id: number; student: string; body: string; target: string }[]; question_count?: number
  attention?: { id: number; student: string; course: string; run: string; reasons: string[]; target: string }[]
  counts?: { pending: number; overdue: number; unassigned: number; attention: number }
  runs?: { id: number; title: string; course: string; kind: string }[]
}

export function useWorkspaceHome() {
  const [data, setData] = useState<HomeData | null>(null), [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  const personal = new URLSearchParams(location.hash.slice(1)).get('mode') === 'personal'
  useEffect(() => {
    let alive = true
    apiRequest<HomeData>(`/api/workspace/home/?personal=${personal ? '1' : '0'}`).then(v => { if (alive) { setData(v); setError('') } }).catch(e => { if (alive) setError(errorMessage(e)) })
    return () => { alive = false }
  }, [personal, revision])
  return { data, error, refresh: () => setRevision(v => v+1) }
}
