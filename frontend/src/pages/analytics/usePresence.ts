import { useEffect } from 'react'
import { apiRequest } from '../../api'

export default function usePresence(userId?: number) {
  useEffect(() => {
    if (!userId) return
    let lastAction = Date.now(), lastSent = 0, stopped = false
    const activity = () => { lastAction = Date.now() }
    async function send() {
      const now = Date.now()
      if (stopped || document.visibilityState !== 'visible' || !document.hasFocus() || now - lastAction > 120000 || now - lastSent < 55000) return
      lastSent = now
      try { await apiRequest('/api/analytics/presence/', 'POST', {}) } catch { /* Learning remains available when activity recording is unavailable. */ }
    }
    for (const event of ['pointerdown', 'keydown', 'wheel', 'focus']) window.addEventListener(event, activity, { passive: true })
    const first = window.setTimeout(send, 1200)
    const timer = window.setInterval(send, 60000)
    return () => {
      stopped = true; window.clearTimeout(first); window.clearInterval(timer)
      for (const event of ['pointerdown', 'keydown', 'wheel', 'focus']) window.removeEventListener(event, activity)
    }
  }, [userId])
}
