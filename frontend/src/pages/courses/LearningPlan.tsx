import { useEffect, useState, type FormEvent } from 'react'
import { apiRequest } from '../../api'
import { ct } from '../../i18n/content'
import { t } from '../../i18n/language'
import { errorMessage, formatDate, inputDate } from '../study/types'
import InlineStepQuiz from '../study/InlineStepQuiz'
import { QuizEditor } from '../study/Quizzes'
import './LearningPlan.css'

type Module = { locked_reason?: string; id: number; title: string; opens_at: string | null; due_at: string | null; available: boolean; is_published: boolean; lesson_id: number | null;
  deadline_state?: string | null; completed_steps: number; total_steps: number; overdue_count?: number; completed_count?: number; waiting_count?: number }
type Checkpoint = { id?: number; quiz_id: number; title?: string; kind: 'weekly' | 'monthly'; period: number; required: boolean; pass_percent: number; opens_at?: string | null; closes_at?: string | null; override_opens_at: string | null; override_closes_at: string | null; state?: string; best_percent?: number | null; passed?: boolean; has_attempts?: boolean }
type Plan = { run_id: number; course_id: number; kind: string; release_mode: string; starts_at: string | null; can_manage: boolean; modules: Module[]; checkpoints: Checkpoint[]; quizzes: { id: number; title: string; is_published: boolean }[] }
const iso = (value: string) => value ? new Date(value).toISOString() : null

export default function LearningPlan({ courseId, runId, canEditQuiz = false, onSaved }: { courseId: number; runId: number; canEditQuiz?: boolean; onSaved?: () => void }) {
  const [plan, setPlan] = useState<Plan | null>(null), [error, setError] = useState(''), [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false), [revision, setRevision] = useState(0), [createQuiz, setCreateQuiz] = useState(false)
  const [selectedQuiz, setSelectedQuiz] = useState<number | null>(null)
  useEffect(() => {
    let alive = true
    let timer: ReturnType<typeof setInterval> | undefined
    async function load() {
      try {
        const value = await apiRequest<Plan>(`/api/courses/runs/${runId}/learning-plan/`)
        if (alive) {
          setPlan(value); setError('')
          if (!value.can_manage && !timer) timer = setInterval(load, 30000)
        }
      } catch (e) { if (alive) setError(errorMessage(e)) }
    }
    void load()
    return () => { alive = false; if (timer) clearInterval(timer) }
  }, [runId, revision])
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!plan) return
    // Read native date inputs before the busy render. Calendar edits and keyboard
    // edits must submit the actual displayed values, including cleared fields.
    const fields = new FormData(event.currentTarget)
    const dateValue = (name: string) => iso(String(fields.get(name) || ''))
    const modules = plan.modules.map(m => ({ id: m.id,
      opens_at: dateValue(`module-${m.id}-opens`), due_at: dateValue(`module-${m.id}-due`) }))
    const checkpoints = plan.checkpoints.map((c, index) => ({ quiz_id: c.quiz_id, kind: c.kind, period: c.period,
      required: c.required, pass_percent: c.pass_percent,
      override_opens_at: c.has_attempts ? c.override_opens_at : dateValue(`check-${index}-opens`),
      override_closes_at: c.has_attempts ? c.override_closes_at : dateValue(`check-${index}-closes`) }))
    setBusy(true); setError(''); setMessage('')
    try {
      const result = await apiRequest<Plan>(`/api/courses/runs/${runId}/learning-plan/`, 'PUT', {
        release_mode: 'dates', starts_at: dateValue('starts_at'), modules, checkpoints,
      })
      setPlan(result); setMessage('Учебный план сохранён'); onSaved?.()
    } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }
  function updateCheck(index: number, change: Partial<Checkpoint>) {
    setPlan(p => p ? { ...p, checkpoints: p.checkpoints.map((c, i) => i === index ? { ...c, ...change } : c) } : p)
  }
  function updateModule(id: number, change: Partial<Module>) {
    setPlan(p => p ? { ...p, modules: p.modules.map(m => m.id === id ? { ...m, ...change } : m) } : p)
  }
  function effectiveCheckDate(c: Checkpoint, closing: boolean) {
    const custom = closing ? c.override_closes_at : c.override_opens_at
    if (custom || !plan?.starts_at) return custom
    const days = Math.max(1, Math.min(520, c.period * (c.kind === 'monthly' ? 4 : 1))) * 7 + (c.kind === 'monthly' ? (closing ? 2 : 0) : (closing ? 0 : -2))
    return new Date(Date.parse(plan.starts_at) + days*86400000).toISOString()
  }
  function addCheck(kind: 'weekly' | 'monthly') {
    setPlan(p => p ? { ...p, checkpoints: [...p.checkpoints, { quiz_id: 0, kind, period: Math.max(0, ...p.checkpoints.filter(c => c.kind === kind).map(c => c.period))+1,
      required: true, pass_percent: 60, override_opens_at: null, override_closes_at: null }] } : p)
  }
  if (!plan) return <section className="study-card">{error ? <p role="alert" className="error">{t(error)}</p> : <p>{t('Загрузка учебного плана…')}</p>}</section>
  return <section className="learning-plan study-card"><div className="section-heading"><div><p className="eyebrow">{plan.kind === 'cohort' ? t('Расписание этой группы') : t('Расписание курса')}</p><h2>{t('Учебный план')}</h2></div>{!plan.can_manage && <button className="secondary" onClick={() => setRevision(n => n+1)}>{t('Обновить')}</button>}</div>
    {error && <p role="alert" className="error">{t(error)}</p>}{message && <p role="status" className="success">{t(message)}</p>}
    {plan.can_manage ? <>
      {createQuiz && <QuizEditor courseId={courseId} initialTitle={t('Контрольный тест')} onCancel={() => setCreateQuiz(false)} onSaved={(id, title) => { setPlan(p => p ? { ...p, quizzes: [...p.quizzes, { id, title, is_published: false }], checkpoints: p.checkpoints.map((c, i) => i === p.checkpoints.findIndex(v => !v.quiz_id) ? { ...c, quiz_id: id } : c) } : p); setCreateQuiz(false) }} />}
      <form onSubmit={save}><fieldset disabled={busy} className="plan-editor"><div className="form-grid"><label>{t('Начало обучения')}<input name="starts_at" type="datetime-local" value={inputDate(plan.starts_at)} onChange={e => setPlan({ ...plan, starts_at: iso(e.target.value) })} /></label></div>
      
      <h3>{t('Сроки модулей')}</h3><div className="plan-modules">{plan.modules.map(m => <article className="plan-module" key={m.id}><strong>{ct(m, 'title')}{!m.is_published ? t(' · черновик') : ''}</strong>
        <label>{t('Дата открытия')}<input name={`module-${m.id}-opens`} aria-label={t('Открытие модуля: {0}', [ct(m, 'title')])} type="datetime-local" value={inputDate(m.opens_at)} onChange={e => updateModule(m.id, { opens_at: iso(e.target.value) })} /></label>
        <label>{t('Дедлайн прохождения')}<input name={`module-${m.id}-due`} aria-label={t('Дедлайн модуля: {0}', [ct(m, 'title')])} type="datetime-local" min={inputDate(m.opens_at)} value={inputDate(m.due_at)} onChange={e => updateModule(m.id, { due_at: iso(e.target.value) })} /></label>
        {m.due_at ? <><div className="module-deadline-counts"><span>{t('Пройдено: {0}', [m.completed_count ?? 0])}</span><span className={m.overdue_count ? 'error' : ''}>{t('Просрочено: {0}', [m.overdue_count ?? 0])}</span>{Boolean(m.waiting_count) && <span>{t('На проверке: {0}', [m.waiting_count])}</span>}</div><button type="button" className="secondary" onClick={() => updateModule(m.id, { due_at: null })}>{t('Убрать дедлайн')}</button></> : <span className="muted">{t('Без дедлайна')}</span>}
      </article>)}</div>
      <h3>{t('Контрольные тесты')}</h3>
      {plan.checkpoints.map((c, index) => <article className="plan-checkpoint" key={`${c.kind}-${index}`}><div className="form-grid"><label>{t('Контроль')}<select disabled={c.has_attempts} value={c.kind} onChange={e => updateCheck(index, { kind: e.target.value as Checkpoint['kind'] })}><option value="weekly">{t('Недельный тест')}</option><option value="monthly">{t('Контроль за 4 недели')}</option></select></label><label>{c.kind === 'weekly' ? t('Номер недели') : t('Номер периода из 4 недель')}<input type="number" min={1} max={c.kind === 'weekly' ? 520 : 130} disabled={c.has_attempts} value={c.period} onChange={e => updateCheck(index, { period: Number(e.target.value) })} /></label><label>{t('Тест')}<select disabled={c.has_attempts} value={c.quiz_id} onChange={e => updateCheck(index, { quiz_id: Number(e.target.value) })}><option value={0}>{t('Выберите тест')}</option>{plan.quizzes.map(q => <option key={q.id} value={q.id}>{ct(q, 'title')}{!q.is_published ? t(' · черновик') : ''}</option>)}</select></label><label>{t('Проходной балл, %')}<input type="number" min={0} max={100} disabled={c.has_attempts} value={c.pass_percent} onChange={e => updateCheck(index, { pass_percent: Number(e.target.value) })} /></label><label>{t('Своя дата открытия теста')}<input name={`check-${index}-opens`} type="datetime-local" disabled={c.has_attempts} value={inputDate(c.override_opens_at)} onChange={e => updateCheck(index, { override_opens_at: iso(e.target.value) })} /></label><label>{t('Своя дата закрытия теста')}<input name={`check-${index}-closes`} type="datetime-local" disabled={c.has_attempts} value={inputDate(c.override_closes_at)} onChange={e => updateCheck(index, { override_closes_at: iso(e.target.value) })} /></label></div><p className="muted">{t('Открытие: {0}', [formatDate(effectiveCheckDate(c, false))])} · {t('До: {0}', [formatDate(effectiveCheckDate(c, true))])}</p><label className="check"><input type="checkbox" checked={c.required} onChange={e => updateCheck(index, { required: e.target.checked })} />{t('Учитывать в завершении курса')}</label>{c.has_attempts ? <small className="muted">{t('У теста уже есть попытки. Назначение, даты и шкала защищены от изменения.')}</small> : <button type="button" className="secondary" onClick={() => setPlan({ ...plan, checkpoints: plan.checkpoints.filter((_, i) => i !== index) })}>{t('Убрать из плана')}</button>}</article>)}
      <div className="action-row"><button type="button" className="secondary" onClick={() => addCheck('weekly')}>{t('+ Недельный тест')}</button><button type="button" className="secondary" onClick={() => addCheck('monthly')}>{t('+ Контроль за 4 недели')}</button>{canEditQuiz && <button type="button" className="secondary" onClick={() => setCreateQuiz(true)}>{t('Создать тест')}</button>}</div>
      <div className="action-row"><button type="submit" disabled={busy || plan.checkpoints.some(c => !c.quiz_id)}>{busy ? t('Сохранение…') : t('Сохранить учебный план')}</button></div></fieldset></form>
    </> : <><div className="plan-modules">{plan.modules.map((m, i) => <article className="plan-module" key={m.id}><span className="eyebrow">{t('Модуль {0}', [i+1])}</span><h3>{ct(m, 'title')}</h3><p>{m.available ? t('Доступен') : m.opens_at ? t('Открытие: {0}', [formatDate(m.opens_at)]) : t('Ожидает назначения в план')}</p>
      {m.due_at && <><p className={`module-deadline ${m.deadline_state === 'overdue' ? 'error' : ''}`}>{t('Пройти до: {0}', [formatDate(m.due_at)])}</p>{m.total_steps > 0 && <span>{m.completed_steps}/{m.total_steps} {t('обязательных шагов')}</span>}{m.deadline_state && <strong className={m.deadline_state === 'overdue' ? 'error' : ''}>{m.deadline_state === 'completed' ? t('Пройден') : m.deadline_state === 'waiting' ? t('На проверке') : m.deadline_state === 'overdue' ? t('Дедлайн просрочен') : ''}</strong>}</>}
      {!m.available && m.locked_reason && <small className="muted">{t(m.locked_reason)}</small>}{m.available && m.lesson_id && <a className="button-link" href={`#course=${courseId}&run=${runId}&lesson=${m.lesson_id}`}>{t('Открыть модуль')}</a>}</article>)}</div>
      <h3>{t('Контрольные тесты')}</h3>{!plan.checkpoints.length && <p className="muted">{t('Преподаватель ещё не назначил контрольные тесты.')}</p>}{plan.checkpoints.map(c => <article className="plan-checkpoint" key={c.id}><span className="eyebrow">{c.kind === 'weekly' ? t('Неделя {0}', [c.period]) : t('Период {0}: четыре учебные недели', [c.period])}</span><h3>{ct(c, 'title')}</h3><p>{t('Открытие: {0}', [formatDate(c.opens_at)])} · {t('До: {0}', [formatDate(c.closes_at)])}</p><p>{c.passed ? t('Зачтено') : c.state === 'open' ? t('Можно пройти') : c.state === 'upcoming' ? t('Откроется по расписанию') : c.state === 'closed' ? t('Приём ответов завершён') : t('Тест ещё готовится')}{c.best_percent != null ? ` · ${c.best_percent}%` : ''}</p><button className="secondary" disabled={c.state === 'draft'} onClick={() => setSelectedQuiz(c.quiz_id)}>{t('Открыть тест')}</button></article>)}
      {selectedQuiz && <InlineStepQuiz courseId={courseId} runId={runId} quizId={selectedQuiz} onCompleted={() => setRevision(n => n+1)} />}</>}
  </section>
}
