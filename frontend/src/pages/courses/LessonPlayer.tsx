import { useEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { ct } from '../../i18n/content'
import { t as tr } from '../../i18n/language'
import MaterialViewer from '../../components/MaterialViewer'
import RichLessonContent from '../../components/RichLessonContent'
import InlineStepQuiz from '../study/InlineStepQuiz'
import StudyPanel from '../study/StudyPanel'
import CodeExercise from '../study/CodeExercise'
import Discussion from '../communication/Discussion'
import LessonPulse from '../workspace/LessonPulse'
import VideoLecture from './VideoLecture'
import './LessonPlayer.css'

export type PlayerStep = { id: number; title: string; kind: string; position: number; completed: boolean; locked: boolean; is_published: boolean }
export type PlayerLesson = { id: number; title: string; locked_reason: string; steps: PlayerStep[] }
export type PlayerModule = { id: number; title: string; position: number; lessons: PlayerLesson[] }
export type PlayerDetail = { id: number; lesson_id: number; title: string; kind: string; content: string; video_url: string; transcript?: string; completed: boolean
  material: { id: number; title: string; url: string; kind: string; filename?: string } | null; assignment_id: number | null; quiz_id: number | null; code_problem_id: number | null }

type Props = { courseTitle: string; runId: number; courseId: number; modules: PlayerModule[]; step: PlayerDetail | null; selectedId: number | null; canManage: boolean; error: string
  onSelect: (id: number) => void; onComplete: (id: number) => Promise<boolean>; onRefresh: () => void; onExit: () => void; openDiscussion?: boolean }

const ICONS: Record<string, string> = { video: '▶', code: '</>', quiz: '?', assignment: '✎', file: '📄', text: '≡' }

function stepIcon(kind: string) { return ICONS[kind] ?? '≡' }

function Modal({ title, onClose, children, wide = false }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  const dialog = useRef<HTMLDivElement>(null)
  const closeRef = useRef(onClose)
  useEffect(() => { closeRef.current = onClose }, [onClose])
  // Runs once per opening: re-running on every render would steal focus from fields inside the dialog.
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    dialog.current?.focus()
    const close = (event: KeyboardEvent) => { if (event.key === 'Escape') { event.stopPropagation(); closeRef.current() } }
    window.addEventListener('keydown', close, true)
    return () => { window.removeEventListener('keydown', close, true); previous?.focus() }
  }, [])
  return <div className="player-modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) onClose() }}>
    <div className={`player-modal ${wide ? 'player-modal-wide' : ''}`} role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} ref={dialog}>
      <header><h2>{title}</h2><button type="button" className="player-icon-button" aria-label={tr("Закрыть")} onClick={onClose}>✕</button></header>
      <div className="player-modal-body">{children}</div>
    </div>
  </div>
}

/** Course plan: modules with progress, lessons and their steps. Used in the player and as the course start page. */
export function CoursePlan({ modules, selectedId, onSelect }: { modules: PlayerModule[]; selectedId: number | null; onSelect: (id: number) => void }) {
  const [open, setOpen] = useState<Set<number>>(() => new Set(modules.filter(m => m.lessons.some(l => l.steps.some(s => s.id === selectedId))).map(m => m.id)))
  return <div className="course-plan">{modules.map(module => {
    const steps = module.lessons.flatMap(l => l.steps)
    const percent = steps.length ? Math.round(steps.filter(s => s.completed).length * 100 / steps.length) : 0
    const expanded = open.has(module.id) || modules.length === 1
    return <section key={module.id} className="course-plan-module">
      <button type="button" className="course-plan-head" aria-expanded={expanded} onClick={() => setOpen(current => { const next = new Set(current); if (next.has(module.id)) next.delete(module.id); else next.add(module.id); return next })}>
        <span className="course-plan-number">{module.position}</span><strong>{ct(module, 'title')}</strong>
        <span className="course-plan-progress"><span className="course-plan-bar"><span style={{ width: `${percent}%` }} /></span>{percent}%</span>
      </button>
      {expanded && module.lessons.map(lesson => <div key={lesson.id} className="course-plan-lesson">
        <p className="course-plan-lesson-title">{ct(lesson, 'title')}{lesson.locked_reason && <span className="muted"> · 🔒 {tr(lesson.locked_reason)}</span>}</p>
        {lesson.steps.map(step => <button type="button" key={step.id} className={`course-plan-step ${step.id === selectedId ? 'is-current' : ''}`} disabled={step.locked} onClick={() => onSelect(step.id)}>
          <span className="course-plan-icon" aria-hidden="true">{stepIcon(step.kind)}</span>
          <span className="course-plan-step-title">{ct(step, 'title')}{!step.is_published ? tr(" · черновик") : ''}</span>
          <span className="course-plan-state">{step.locked ? '🔒' : step.completed ? '✓' : ''}</span>
        </button>)}
      </div>)}
    </section>
  })}</div>
}

export default function LessonPlayer({ courseTitle, runId, courseId, modules, step, selectedId, canManage, error, onSelect, onComplete, onRefresh, onExit, openDiscussion = false }: Props) {
  const [plan, setPlan] = useState(false)
  const [discussion, setDiscussion] = useState(openDiscussion)
  // The transcript panel is hidden per step: a new step always starts with it open.
  const [panelHiddenFor, setPanelHiddenFor] = useState<number | null>(null)
  const panel = panelHiddenFor !== selectedId
  const [saving, setSaving] = useState(false)
  const lessons = modules.flatMap(m => m.lessons)
  const all = lessons.flatMap(l => l.steps)
  const index = all.findIndex(s => s.id === selectedId)
  const lesson = lessons.find(l => l.steps.some(s => s.id === selectedId))
  const previous = index > 0 ? all[index - 1] : null
  const next = index >= 0 && index < all.length - 1 ? all[index + 1] : null
  useEffect(() => {
    document.body.classList.add('lesson-player-open')
    return () => document.body.classList.remove('lesson-player-open')
  }, [])
  async function understood() {
    if (!step) return
    setSaving(true)
    const ok = canManage || step.completed || await onComplete(step.id)
    setSaving(false)
    if (!ok) return
    if (next && !next.locked) onSelect(next.id)
    else setPlan(true)
  }
  const reading = step && ['text', 'file', 'video'].includes(step.kind)
  const gotIt = reading && <button type="button" className="player-got-it" disabled={saving} onClick={understood}>{step.completed || canManage ? (next ? tr("Дальше →") : tr("План курса")) : tr("Понятно!")}</button>
  let content: ReactNode = <p className="muted player-loading" role="status">{error ? tr(error) : tr('Загрузка…')}</p>
  if (step && step.id === selectedId) {
    if (step.kind === 'video') content = <div className="player-video">
      <VideoLecture key={step.id} url={step.video_url} transcript={step.transcript ?? ''} title={ct(step, 'title')} panelOpen={panel} />
      <div className="player-step-actions">{step.transcript ? <button type="button" className="secondary" aria-pressed={!panel} onClick={() => setPanelHiddenFor(panel ? selectedId : null)}>{panel ? tr("Скрыть боковую панель") : tr("Показать транскрипт")}</button> : <span />}{gotIt}</div>
    </div>
    else if (step.kind === 'code' && step.code_problem_id) content = <div className="player-code"><CodeExercise key={step.id} problemId={step.code_problem_id} runId={runId} onCompleted={onRefresh} variant="player" /></div>
    else content = <div className="player-scroll"><article className={`player-article player-article-${step.kind}`}>
      <h1>{ct(step, 'title')}</h1>
      {step.kind === 'text' && <RichLessonContent content={ct(step, 'content') || tr("Содержание пока не добавлено.")} runId={runId} />}
      {step.kind === 'file' && step.material && <MaterialViewer key={step.material.id} material={{ ...step.material, title: ct(step.material, 'title') }} />}
      {step.kind === 'quiz' && step.quiz_id && <InlineStepQuiz courseId={courseId} runId={runId} quizId={step.quiz_id} onCompleted={onRefresh} />}
      {step.kind === 'assignment' && step.assignment_id && <StudyPanel courseId={courseId} runId={runId} tab="assignments" activityId={step.assignment_id} />}
      {reading && <div className="player-step-actions"><span />{gotIt}</div>}
    </article></div>
  }
  return createPortal(<div className="lesson-player" role="region" aria-label={tr("Урок: {0}", [courseTitle])}>
    <header className="player-topbar">
      <div className="player-crumbs">
        <button type="button" className="player-icon-button" aria-label={tr("Выйти из урока")} title={tr("Выйти из урока")} onClick={onExit}>✕</button>
        <span className="player-course" title={courseTitle}>{courseTitle}</span>{lesson && <><span aria-hidden="true">/</span><strong title={ct(lesson, 'title')}>{ct(lesson, 'title')}</strong></>}
      </div>
      <nav className="player-nav" aria-label={tr("Навигация по шагам")}>
        <button type="button" aria-label={tr("Предыдущий шаг")} disabled={!previous || previous.locked} onClick={() => previous && onSelect(previous.id)}>←</button>
        <button type="button" className="player-plan-button" onClick={() => setPlan(true)}>≡ {tr("План курса")}</button>
        <button type="button" aria-label={tr("Следующий шаг")} disabled={!next || next.locked} onClick={() => next && onSelect(next.id)}>→</button>
      </nav>
      <div className="player-tools">{lesson && !lesson.locked_reason && <button type="button" className="secondary" onClick={() => setDiscussion(true)}>💬 {tr("Обсуждение")}</button>}</div>
    </header>
    <main className="player-body">{content}</main>
    <footer className="player-footer">
      {lesson && <div className="player-segments" role="list" aria-label={tr("Шаги урока")}>{lesson.steps.map(s => <button type="button" role="listitem" key={s.id} disabled={s.locked} title={`${s.position}. ${ct(s, 'title')}`} aria-label={`${s.position}. ${ct(s, 'title')}${s.completed ? ' ✓' : ''}`} aria-current={s.id === selectedId ? 'step' : undefined} className={`${s.completed ? 'is-done' : ''} ${s.id === selectedId ? 'is-current' : ''}`} onClick={() => onSelect(s.id)} />)}</div>}
    </footer>
    {plan && <Modal title={courseTitle} wide onClose={() => setPlan(false)}>
      <CoursePlan modules={modules} selectedId={selectedId} onSelect={id => { setPlan(false); onSelect(id) }} />
      <div className="player-modal-actions"><button type="button" className="secondary" onClick={onExit}>{tr("← Вернуться к курсу")}</button></div>
    </Modal>}
    {discussion && lesson && <Modal title={tr("Обсуждение: {0}", [ct(lesson, 'title')])} wide onClose={() => setDiscussion(false)}>
      <LessonPulse key={`pulse-${lesson.id}-${runId}`} lessonId={lesson.id} runId={runId} />
      <Discussion key={`${lesson.id}-${runId}`} lessonId={lesson.id} runId={runId} />
    </Modal>}
  </div>, document.body)
}
