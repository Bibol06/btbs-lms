import MaterialViewer from '../../components/MaterialViewer'
import { ct } from '../../i18n/content'
import { createPortal } from 'react-dom'
import RichLessonContent from '../../components/RichLessonContent'
import LessonContentEditor from '../../components/LessonContentEditor'
import InlineStepQuiz from '../study/InlineStepQuiz'
import { stepKindCaption } from '../../i18n/captions'
import { t as tr } from '../../i18n/language'
import LessonPulse from '../workspace/LessonPulse'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { apiRequest } from '../../api'
import { errorMessage, formatDate } from '../study/types'
import StudyPanel from '../study/StudyPanel'
import CodeExercise from '../study/CodeExercise'
import PracticeFields from '../study/PracticeFields'
import { practiceValues } from '../study/practiceValues'
import { QuizEditor } from '../study/Quizzes'
import { loadStepChoices, type StepChoices } from './stepChoices'
import ConfirmAction from '../study/ConfirmAction'
import LessonPlayer, { CoursePlan } from './LessonPlayer'
import TeacherMediaUploader from '../teacher/TeacherMediaUploader'
import { Discussion } from '../communication/Communication'

type StepInfo = { id: number; title: string; kind: string; position: number; is_published: boolean; required: boolean; completed: boolean; locked: boolean }
type LessonInfo = { id: number; title: string; position: number; is_published: boolean; locked_reason: string; steps: StepInfo[] }
type ModuleInfo = { id: number; title: string; position: number; is_published: boolean; opens_at: string | null; due_at?: string | null; deadline_state?: string | null; prerequisite_id: number | null; lessons: LessonInfo[] }
type Structure = { modules: ModuleInfo[]; last_step_id: number | null; can_edit: boolean; can_manage: boolean; progress: { total: number; completed: number; percent: number } }
type StepDetail = { id: number; lesson_id: number; title: string; kind: string; content: string; video_url: string; transcript: string; is_published: boolean; required: boolean; pass_percent: number; material_id: number | null; assignment_id: number | null; quiz_id: number | null; code_problem_id: number | null; material: { id: number; title: string; url: string; kind: string; filename?: string } | null; completed: boolean }
type Editor = { kind: 'module'; initial?: ModuleInfo } | { kind: 'lesson'; module: ModuleInfo; initial?: LessonInfo } | { kind: 'step'; lesson: LessonInfo; initial?: StepDetail }

function CodeProblemBuilder({ courseId, runId, onCreated }: { courseId: number; runId: number; onCreated: (id: number) => void }) {
  const [cases, setCases] = useState([{ stdin: '', expected: '', is_sample: true }])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); e.stopPropagation(); const data = new FormData(e.currentTarget); setBusy(true)
    try {
      const result = await apiRequest<{ id: number }>(`/api/code/courses/${courseId}/problems/?run_id=${runId}`, 'POST', { title: data.get('title'), statement: data.get('statement'), starter_code: data.get('starter_code'), max_attempts: Number(data.get('max_attempts')), test_cases: cases, ...practiceValues(data) })
      onCreated(result.id)
    } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }
  return <form className="study-form" onSubmit={save}><h3>{tr("Новая задача Python")}</h3><label>{tr("Название задачи")}<input name="title" required maxLength={200} /></label><label>{tr("Условие задачи")}<textarea name="statement" rows={5} required maxLength={30000} /></label><PracticeFields /><label>{tr("Начальный код")}<textarea className="code-editor" name="starter_code" rows={4} maxLength={20000} /></label><label>{tr("Лимит отправок")}<input type="number" min={1} max={100} name="max_attempts" defaultValue={20} required /></label>
    {cases.map((c, i) => <fieldset key={i}><legend>{tr("Проверочный тест ")}{i+1}</legend><div className="form-grid"><label>{tr("Ввод")}<textarea value={c.stdin} onChange={e => setCases(current => current.map((v, j) => j === i ? { ...v, stdin: e.target.value } : v))} maxLength={10000} /></label><label>{tr("Ожидаемый вывод")}<textarea value={c.expected} onChange={e => setCases(current => current.map((v, j) => j === i ? { ...v, expected: e.target.value } : v))} maxLength={10000} /></label></div><label className="check"><input type="checkbox" checked={c.is_sample} onChange={e => setCases(current => current.map((v, j) => j === i ? { ...v, is_sample: e.target.checked } : v))} /> {tr(" Показывать этот пример студенту")}</label>{cases.length > 1 && <button type="button" className="danger" onClick={() => setCases(current => current.filter((_, j) => j !== i))}>{tr("Удалить тестовый пример")}</button>}</fieldset>)}
    <button type="button" className="secondary" disabled={cases.length >= 20} onClick={() => setCases(current => [...current, { stdin: '', expected: '', is_sample: false }])}>{tr("+ Тестовый пример")}</button>{error && <p role="alert" className="error">{tr(error)}</p>}<button disabled={busy}>{tr("Создать задачу Python")}</button>
  </form>
}

function CurriculumEditor({ courseId, runId, editor, modules, onSaved, onCancel }: { courseId: number; runId: number; editor: Editor; modules: ModuleInfo[]; onSaved: (stepId?: number) => void; onCancel: () => void }) {
  const [kind, setKind] = useState(editor.kind === 'step' ? editor.initial?.kind ?? 'text' : '')
  const [choices, setChoices] = useState<StepChoices>({ assignments: [], quizzes: [], problems: [], materials: [] })
  const [problemId, setProblemId] = useState(editor.kind === 'step' ? editor.initial?.code_problem_id ?? 0 : 0)
  const [builder, setBuilder] = useState(false)
  const [quizId, setQuizId] = useState(editor.kind === 'step' ? editor.initial?.quiz_id ?? 0 : 0)
  const [quizBuilder, setQuizBuilder] = useState<{ title: string } | null>(null)
  const quizSelect = useRef<HTMLSelectElement>(null)
  const [choicesRevision, setChoicesRevision] = useState(0)
  const [choicesState, setChoicesState] = useState({ loading: editor.kind === 'step', study: '', code: '', file: '' })
  const [uploadingContent, setUploadingContent] = useState(false)
  const [contentDraft, setContentDraft] = useState(editor.kind === 'step' ? editor.initial?.content ?? '' : '')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    let alive = true
    if (editor.kind === 'step') {
      loadStepChoices(courseId, runId, editor.lesson.id).then(result => {
        if (!alive) return
        setChoices(previous => ({ ...previous, ...result.choices }))
        if (result.choices.quizzes) setQuizId(previous => result.choices.quizzes!.some(quiz => quiz.id === previous) ? previous : 0)
        setChoicesState({ loading: false, ...result.errors })
      })
    }
    return () => { alive = false }
  }, [courseId, runId, editor, choicesRevision])
  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    if (uploadingContent) { setError('Дождитесь завершения загрузки изображения.'); return }
    const data = new FormData(e.currentTarget); setError(''); setBusy(true)
    try {
      if (editor.kind === 'module') {
        await apiRequest(editor.initial ? `/api/learning/modules/${editor.initial.id}/` : `/api/learning/courses/${courseId}/structure/`, editor.initial ? 'PATCH' : 'POST', {
          title: data.get('title'), is_published: data.has('published'), prerequisite_id: Number(data.get('prerequisite_id')) || null })
      } else if (editor.kind === 'lesson') {
        await apiRequest(editor.initial ? `/api/learning/teacher/lessons/${editor.initial.id}/` : `/api/learning/teacher/courses/${courseId}/lessons/`, editor.initial ? 'PATCH' : 'POST', {
          title: data.get('title'), is_published: data.has('published'), module_id: Number(data.get('module_id')), ...(editor.initial ? {} : { content: data.get('content') || '' }) })
      } else {
        const result = await apiRequest<{ id?: number; step?: { id: number } }>(editor.initial ? `/api/learning/steps/${editor.initial.id}/?run_id=${runId}` : `/api/learning/lessons/${editor.lesson.id}/steps/`, editor.initial ? 'PATCH' : 'POST', {
          title: data.get('title'), kind, content: data.get('content') || '', video_url: data.get('video_url') || '', ...(kind === 'video' ? { transcript: data.get('transcript') || '' } : {}),
          is_published: data.has('published'), required: data.has('required'), pass_percent: Number(data.get('pass_percent') ?? 60),
          assignment_id: kind === 'assignment' ? Number(data.get('assignment_id')) : null,
          quiz_id: kind === 'quiz' ? quizId : null,
          material_id: kind === 'file' ? Number(data.get('material_id')) : null,
          code_problem_id: kind === 'code' ? problemId : null,
        })
        onSaved(result.id ?? result.step?.id); return
      }
      onSaved()
    } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }
  const initial = editor.initial
  const choiceError = ['quiz', 'assignment'].includes(kind) ? choicesState.study : kind === 'code' ? choicesState.code : kind === 'file' ? choicesState.file : ''
  const missingQuiz = editor.kind === 'step' && kind === 'quiz' && !quizId
  return <div>
    {builder && <CodeProblemBuilder courseId={courseId} runId={runId} onCreated={id => { setProblemId(id); setBuilder(false) }} />}
    {quizBuilder && <QuizEditor courseId={courseId} initialTitle={quizBuilder.title} onSaved={(id, title) => {
      setChoices(previous => ({ ...previous, quizzes: [...previous.quizzes, { id, title }] }))
      setChoicesState({ loading: true, study: '', code: '', file: '' })
      setQuizId(id); setQuizBuilder(null); setChoicesRevision(value => value + 1)
      window.requestAnimationFrame(() => quizSelect.current?.focus())
    }} onCancel={() => { setQuizBuilder(null); quizSelect.current?.focus() }} />}
    <form className="study-form" onSubmit={save}><h3>{initial ? tr("Редактирование") : tr("Создание")}: {editor.kind === 'module' ? tr("модуль") : editor.kind === 'lesson' ? tr("урок") : tr("шаг")}</h3>
      <label>{tr("Название")}<input name="title" required maxLength={200} defaultValue={initial?.title} /></label>
      {editor.kind === 'module' && editor.initial && <><a href={`#course=${courseId}&run=${runId}&tab=plan`}>{tr('Сроки модуля')}</a><label>{tr("Сначала завершить модуль")}<select name="prerequisite_id" defaultValue={editor.initial.prerequisite_id ?? ''}><option value="">{tr("Нет ограничения")}</option>{modules.filter(m => m.id !== editor.initial?.id).map(m => <option value={m.id} key={m.id}>{ct(m, "title")}</option>)}</select></label></>}
      {editor.kind === 'lesson' && <><label>{tr("Модуль")}<select name="module_id" defaultValue={editor.module.id}>{modules.map(m => <option value={m.id} key={m.id}>{ct(m, "title")}</option>)}</select></label>{!editor.initial && <LessonContentEditor label={tr('Первый текстовый шаг')} value={contentDraft} onChange={setContentDraft} rows={5} maxLength={50000} />}</>}
      {editor.kind === 'step' && <>
        <label>{tr("Тип шага")}<select value={kind} disabled={busy || uploadingContent} onChange={e => setKind(e.target.value)}><option value="text">{tr("Текст")}</option><option value="video">{tr("Видео")}</option><option value="file">{tr("Файл")}</option><option value="assignment">{tr("Домашнее задание")}</option><option value="quiz">{tr("Тест")}</option><option value="code">{tr("Задача Python")}</option></select></label>
        {kind === 'text' && <LessonContentEditor label={tr('Содержание шага')} lessonId={editor.lesson.id} runId={runId} value={contentDraft} onChange={setContentDraft} maxLength={100000} rows={12} onUploadingChange={setUploadingContent} />}
        {kind === 'video' && <><label>{tr("Ссылка на видео (YouTube или файл .mp4)")}<input type="url" name="video_url" defaultValue={editor.initial?.video_url} required maxLength={200} /></label>
          <label>{tr("Транскрипт: строка «00:00 Заголовок» начинает главу, ниже — её текст")}<textarea name="transcript" rows={8} maxLength={50000} defaultValue={editor.initial?.transcript} placeholder={'00:00 Привет, Python!\nВ этом уроке…\n00:35 Переменные\n…'} /></label></>}
        {kind === 'file' && <label>{tr("Материал урока")}<select name="material_id" defaultValue={editor.initial?.material_id ?? ''} required><option value="">{tr("Выберите загруженный файл")}</option>{choices.materials.map(v => <option key={v.id} value={v.id}>{ct(v, "title")}</option>)}</select></label>}
        {kind === 'assignment' && <label>{tr("Задание")}<select name="assignment_id" defaultValue={editor.initial?.assignment_id ?? ''} required><option value="">{tr("Выберите задание из раздела «Задания»")}</option>{choices.assignments.map(v => <option key={v.id} value={v.id}>{ct(v, "title")}</option>)}</select></label>}
        {kind === 'quiz' && <>
          <label>{tr("Тест")}<select ref={quizSelect} name="quiz_id" value={quizId || ''} onChange={event => setQuizId(Number(event.target.value))} required disabled={choicesState.loading}>
            <option value="">{choicesState.loading ? tr('Загрузка тестов…') : tr("Выберите тест из раздела «Тесты»")}</option>
            {choices.quizzes.map(v => <option key={v.id} value={v.id}>{ct(v, "title")}</option>)}
          </select></label>
          {!choicesState.loading && !choicesState.study && !choices.quizzes.length && <p className="muted" role="status">{tr('В этом курсе пока нет тестов. Создайте тест здесь, затем сохраните шаг.')}</p>}
          <div className="action-row"><button type="button" className="secondary" disabled={busy || Boolean(quizBuilder)} onClick={event => {
            const titleField = event.currentTarget.form?.elements.namedItem('title') as HTMLInputElement | null
            setQuizBuilder({ title: titleField?.value || '' })
          }}>{tr('+ Создать тест для шага')}</button><button type="button" className="secondary" disabled={busy || choicesState.loading} onClick={() => { setChoicesState({ loading: true, study: '', code: '', file: '' }); setChoicesRevision(value => value + 1) }}>{tr('Обновить')}</button></div>
          
        </>}
        {kind === 'code' && <><label>{tr("Задача Python")}<select value={problemId} onChange={e => setProblemId(Number(e.target.value))} required><option value={0}>{tr("Выберите или создайте задачу")}</option>{choices.problems.map(v => <option key={v.id} value={v.id}>{ct(v, "title")}</option>)}{problemId > 0 && !choices.problems.some(p => p.id === problemId) && <option value={problemId}>{tr("Созданная задача #")}{problemId}</option>}</select></label><button type="button" className="secondary" onClick={() => setBuilder(v => !v)}>{tr("+ Создать задачу Python с тестами")}</button></>}
        <label className="check"><input type="checkbox" name="required" defaultChecked={editor.initial?.required ?? true} /> {tr(" Обязательный шаг")}</label>
        {['assignment', 'quiz'].includes(kind) && <label>{tr("Проходной балл, %")}<input type="number" name="pass_percent" min={0} max={100} defaultValue={editor.initial?.pass_percent ?? 60} /></label>}
      </>}
      {editor.kind === 'step' && choiceError && <div role="alert"><p className="error">{tr('Не удалось загрузить список материалов шага: {0}', [tr(choiceError)])}</p><button type="button" className="secondary" disabled={choicesState.loading} onClick={() => { setChoicesState({ loading: true, study: '', code: '', file: '' }); setChoicesRevision(value => value + 1) }}>{tr('Повторить загрузку')}</button></div>}
      <label className="check"><input type="checkbox" name="published" defaultChecked={initial?.is_published ?? false} /> {tr(" Опубликовать")}</label>
      {error && <p className="error" role="alert">{tr(error)}</p>}<div className="action-row editor-save-bar"><button disabled={busy || uploadingContent || missingQuiz || Boolean(quizBuilder) || (editor.kind === 'step' && ['quiz', 'assignment', 'code', 'file'].includes(kind) && choicesState.loading)}>{busy ? tr('Сохранение…') : tr("Сохранить")}</button><button type="button" className="secondary" onClick={onCancel} disabled={busy || uploadingContent}>{tr("Отмена")}</button></div>
    </form>
  </div>
}

export default function Curriculum({ courseId, runId, courseTitle = '', navigationHost, onNavigate }: { courseId: number; runId: number; courseTitle?: string; navigationHost?: HTMLElement | null; onNavigate?: () => void }) {
  const [structure, setStructure] = useState<Structure | null>(null)
  const [lastCheckedAt, setLastCheckedAt] = useState(() => Date.now())
  const [selectedId, setSelectedId] = useState<number | null>(() => Number(new URLSearchParams(location.hash.slice(1)).get('step')) || null)
  const [visitId, setVisitId] = useState(() => crypto.randomUUID())
  const [step, setStep] = useState<StepDetail | null>(null)
  const [revision, setRevision] = useState(0)
  const [editing, setEditing] = useState(() => new URLSearchParams(location.hash.slice(1)).get('edit') === '1')
  const [outlineCollapsed, setOutlineCollapsed] = useState(false)
  const [editor, setEditor] = useState<Editor | null>(null)
  const [error, setError] = useState('')
  // Learners study in the full-screen player; editors open it on demand (null = not decided yet).
  const [playerOpen, setPlayerOpen] = useState<boolean | null>(null)
  const refresh = () => setRevision(v => v + 1)
  useEffect(() => {
    let alive = true
    apiRequest<Structure>(`/api/learning/courses/${courseId}/structure/?run_id=${runId}`).then(data => {
      if (alive) {
        setStructure(data); setLastCheckedAt(Date.now()); setError('')
        setPlayerOpen(current => current ?? !data.can_manage)
        const all = data.modules.flatMap(m => m.lessons.flatMap(l => l.steps))
        const route = new URLSearchParams(location.hash.slice(1))
        const requestedLesson = data.modules.flatMap(m => m.lessons).find(l => l.id === Number(route.get('lesson')))
        if (data.can_edit && requestedLesson && !requestedLesson.steps.length && route.get('edit') === '1') {
          setEditing(true); setEditor({ kind: 'step', lesson: requestedLesson }); setSelectedId(null); setStep(null)
          return
        }
        const target = requestedLesson?.steps[0]?.id
        const available = all.filter(s => !s.locked)
        setSelectedId(current => available.some(s => s.id === current) ? current : available.some(s => s.id === target) ? target! : available.some(s => s.id === data.last_step_id) ? data.last_step_id : available[0]?.id ?? null)
      }
    }).catch(err => { if (alive) setError(errorMessage(err)) })
    return () => { alive = false }
  }, [courseId, runId, revision])
  useEffect(() => {
    let alive = true
    if (!selectedId) return
    apiRequest<{ step: StepDetail }>(`/api/learning/steps/${selectedId}/?run_id=${runId}`).then(data => {
      if (!alive) return
      setStep(data.step); setError(''); window.history.replaceState(null, '', `#course=${courseId}&run=${runId}&step=${selectedId}${new URLSearchParams(location.hash.slice(1)).get('comment') ? `&comment=${new URLSearchParams(location.hash.slice(1)).get('comment')}` : ''}`)
      return apiRequest(`/api/learning/steps/${selectedId}/visit/?run_id=${runId}`, 'POST', { visit_id: visitId })
    }).catch(err => { if (alive) { setStep(null); setError(errorMessage(err)) } })
    return () => { alive = false }
  }, [selectedId, courseId, runId, revision, visitId])
  async function action(url: string, method: string, payload?: unknown) {
    try { await apiRequest(url, method, payload); refresh() } catch (err) { setError(errorMessage(err)) }
  }
  if (!structure) return <p>{error || tr("Загрузка программы курса…")}</p>
  const lessons = structure.modules.flatMap(m => m.lessons)
  const all = lessons.flatMap(l => l.steps)
  const lesson = lessons.find(l => l.steps.some(s => s.id === selectedId))
  const module = structure.modules.find(m => m.lessons.some(l => l.id === lesson?.id))
  const currentIndex = all.findIndex(s => s.id === selectedId)
  const select = (id: number) => { setStep(null); setSelectedId(id); setVisitId(crypto.randomUUID()); onNavigate?.() }
  async function complete(id: number) {
    try { await apiRequest(`/api/learning/steps/${id}/complete/?run_id=${runId}`, 'POST', { completed: true }); refresh(); return true }
    catch (err) { setError(errorMessage(err)); return false }
  }
  const openAt = (id: number | null) => { if (id) select(id); setPlayerOpen(true) }
  if (playerOpen && all.length > 0) {
    return <LessonPlayer courseTitle={courseTitle} courseId={courseId} runId={runId} modules={structure.modules} step={step} selectedId={selectedId}
      canManage={structure.can_manage} error={error} onSelect={select} onComplete={complete} onRefresh={refresh} onExit={() => setPlayerOpen(false)}
      openDiscussion={Boolean(new URLSearchParams(location.hash.slice(1)).get('comment'))} />
  }
  if (!structure.can_manage) {
    const resume = all.find(s => s.id === selectedId && !s.locked) ?? all.find(s => !s.locked && !s.completed) ?? all.find(s => !s.locked)
    const done = structure.progress
    return <section className="course-start">
      <div className="course-start-hero"><div><h2>{courseTitle || tr("Программа курса")}</h2><p className="muted">{tr("Пройдено ")}{done.completed}/{done.total} {tr(" обязательных шагов · ")}{done.percent}%</p></div>
        {resume && <button onClick={() => openAt(resume.id)}>{done.completed ? tr("Продолжить обучение →") : tr("Начать обучение →")}</button>}</div>
      {error && <p className="error" role="alert">{tr(error)}</p>}
      <CoursePlan modules={structure.modules} selectedId={selectedId} onSelect={openAt} />
    </section>
  }
  async function move(kind: string, ids: number[], id: number, direction: number, parentId?: number) {
    const index = ids.indexOf(id); const next = index + direction
    if (next < 0 || next >= ids.length) return
    const copy = [...ids]; [copy[index], copy[next]] = [copy[next], copy[index]]
    await action(`/api/learning/courses/${courseId}/reorder/`, 'POST', { kind, ids: copy, parent_id: parentId })
  }
  const outline = <aside className="lesson-sidebar" hidden={outlineCollapsed}><h3>{tr("Программа курса")}</h3>{structure.modules.map(m => <div className="module-outline" key={m.id}>
        <h4>{m.position}. {ct(m, "title")}{!m.is_published ? tr(" · черновик") : ''}</h4>
        {m.opens_at && <small className="module-release-caption">{tr('Открытие: {0}', [formatDate(m.opens_at)])}</small>}
        {m.due_at && <small className={`module-release-caption ${m.deadline_state === 'overdue' ? 'error' : ''}`}>{tr('Пройти до: {0}', [formatDate(m.due_at)])}{m.deadline_state === 'overdue' && <><br />{tr('Дедлайн просрочен')}</>}</small>}
        {structure.can_manage && <a href={`#course=${courseId}&run=${runId}&tab=plan`}>{tr('Сроки модуля')}</a>}
        {structure.can_edit && editing && <div className="action-row"><button className="secondary" onClick={() => setEditor({ kind: 'module', initial: m })}>{tr("Настроить модуль")}</button><button className="secondary" onClick={() => setEditor({ kind: 'lesson', module: m })}>{tr("+ Урок")}</button><button className="secondary" aria-label={tr("Поднять модуль {0}", [ct(m, "title")])} onClick={() => move('modules', structure.modules.map(v => v.id), m.id, -1)}>↑</button><button className="secondary" aria-label={tr("Опустить модуль {0}", [ct(m, "title")])} onClick={() => move('modules', structure.modules.map(v => v.id), m.id, 1)}>↓</button>{!m.lessons.length && <ConfirmAction label={tr("Удалить модуль")} question={tr("Удалить пустой модуль?")} onConfirm={() => action(`/api/learning/modules/${m.id}/`, 'DELETE')} />}</div>}
        {m.lessons.map(l => <div key={l.id}><strong>{ct(l, "title")}{!l.is_published ? tr(" · черновик") : ''}</strong>{l.locked_reason && <p className="muted">🔒 {tr(l.locked_reason)}</p>}{l.steps.map(s => <button aria-current={s.id === selectedId ? 'step' : undefined} className={`lesson-item ${s.id === selectedId ? 'selected' : ''} ${s.completed ? 'completed' : ''}`} key={s.id} disabled={s.locked} onClick={() => select(s.id)}><span className="outline-check">{s.completed ? '✓' : s.locked ? '🔒' : '○'}</span><span>{s.position}. {ct(s, "title")}</span>{!s.is_published ? tr(" · черновик") : ''}</button>)}{structure.can_edit && editing && <button className="secondary" onClick={() => setEditor({ kind: 'step', lesson: l })}>{tr("+ Шаг в урок")}</button>}</div>)}
      </div>)}</aside>
  return <section className="study-section">
    {navigationHost && createPortal(outline, navigationHost)}
    <div className="lesson-progress">{structure.can_manage ? <strong>{tr("Программа курса · ")}{structure.progress.total} {tr("обязательных шагов")}</strong> : <><strong>{tr("Пройдено ")}{structure.progress.completed}/{structure.progress.total} {tr(" обязательных шагов · ")}{structure.progress.percent}%</strong><progress max={100} value={structure.progress.percent} /></>}</div>
    {error && <p className="error" role="alert">{tr(error)}</p>}
    {all.length > 0 && <div className="editor-switch"><button className="secondary" onClick={() => setPlayerOpen(true)}>{tr("▶ Открыть урок как ученик")}</button></div>}
    {structure.can_edit && <div className="editor-switch"><button className="secondary" onClick={() => { setEditing(v => !v); setEditor(null) }}>{editing ? tr("Завершить редактирование") : tr("Редактировать программу")}</button></div>}
    {structure.can_edit && editing && <div className="action-row"><button onClick={() => setEditor({ kind: 'module' })}>{tr("+ Модуль")}</button></div>}
    {editor && <CurriculumEditor key={`${editor.kind}-${editor.initial?.id ?? 'new'}-${editor.kind === 'lesson' ? editor.module?.id : editor.kind === 'step' ? editor.lesson.id : ''}`} courseId={courseId} runId={runId} editor={editor} modules={structure.modules} onSaved={id => { setEditor(null); if (id) setSelectedId(id); refresh() }} onCancel={() => setEditor(null)} />}
    {!navigationHost && <div className="outline-toolbar"><button className="secondary" aria-expanded={!outlineCollapsed} onClick={() => setOutlineCollapsed(v => !v)}>{outlineCollapsed ? tr("Показать программу курса") : tr("Свернуть программу курса")}</button></div>}
    <div hidden={Boolean(editor)} className={`lesson-layout ${navigationHost ? 'external-outline' : ''} ${outlineCollapsed ? 'outline-collapsed' : ''}`}>
      {!navigationHost && outline}
      <div>
        {lesson && <><div className="section-heading"><h2>{ct(lesson, "title")}</h2>{structure.can_edit && editing && module && <button className="secondary" onClick={() => setEditor({ kind: 'lesson', initial: lesson, module })}>{tr("Настроить урок")}</button>}</div>
          <div className="step-strip">{lesson.steps.map(s => <button key={s.id} className={s.id === selectedId ? '' : 'secondary'} disabled={s.locked} title={`${ct(s, "title")} · ${stepKindCaption(s.kind)}`} onClick={() => select(s.id)}>{s.completed ? '✓' : s.position} · {s.kind === 'code' ? 'Python' : s.kind === 'quiz' ? tr("Тест") : s.kind === 'assignment' ? tr("Задание") : s.kind === 'video' ? tr("Видео") : s.kind === 'file' ? tr("Файл") : tr("Текст")}</button>)}</div>
        </>}
        {step && step.id === selectedId && <article className="lesson-content"><div className="lesson-step-heading"><h3>{ct(step, "title")}</h3>{structure.can_edit && lesson && <div className="action-row"><button className="secondary" onClick={() => { setEditing(true); setEditor({ kind: 'step', lesson, initial: step }) }}>{tr('Редактировать шаг')}</button><button className="secondary" onClick={() => { setEditing(true); setEditor({ kind: 'step', lesson }) }}>{tr('+ Шаг в урок')}</button></div>}</div>
          {step.kind === 'text' && <RichLessonContent content={ct(step, "content") || tr("Содержание пока не добавлено.")} runId={runId} />}
          {step.kind === 'video' && <p><a href={step.video_url} target="_blank" rel="noreferrer">{tr("Смотреть видео →")}</a></p>}
          {step.kind === 'file' && step.material && <MaterialViewer key={step.material.id} material={{ ...step.material, title: ct(step.material, 'title') }} />}
          {step.kind === 'assignment' && step.assignment_id && <StudyPanel courseId={courseId} runId={runId} tab="assignments" activityId={step.assignment_id} />}
          {step.kind === 'quiz' && step.quiz_id && <InlineStepQuiz courseId={courseId} runId={runId} quizId={step.quiz_id} onCompleted={refresh} />}
          {step.kind === 'code' && step.code_problem_id && <CodeExercise key={step.id} problemId={step.code_problem_id} runId={runId} onCompleted={refresh} />}
          {!structure.can_manage && ['text', 'video', 'file'].includes(step.kind) && <div className="action-row"><button onClick={() => action(`/api/learning/steps/${step.id}/complete/?run_id=${runId}`, 'POST', { completed: !step.completed })}>{step.completed ? tr("✓ Изучено · снять отметку") : tr("Отметить шаг изученным")}</button></div>}
          {structure.can_edit && editing && lesson && <div className="action-row"><button className="secondary" onClick={() => move('steps', lesson.steps.map(s => s.id), step.id, -1, lesson.id)}>{tr("← Раньше")}</button><button className="secondary" onClick={() => move('steps', lesson.steps.map(s => s.id), step.id, 1, lesson.id)}>{tr("Позже →")}</button><ConfirmAction label={tr("Удалить шаг")} question={tr("Удалить этот шаг и отметки его прохождения?")} onConfirm={() => action(`/api/learning/steps/${step.id}/`, 'DELETE')} /></div>}
        </article>}
        {(!step || step.id !== selectedId) && !error && (selectedId !== null ? <p className="muted" role="status">{tr('Загрузка…')}</p> : all.length > 0 && all.every(item => item.locked) ? <section className="course-locked-state"><span aria-hidden="true">◷</span><h2>{tr('Материалы пока закрыты')}</h2><p>{tr('Вы записаны на курс. Доступ к урокам откроется по расписанию преподавателя.')}</p>{structure.modules.filter(item => item.lessons.some(value => value.locked_reason)).map(item => <p key={item.id}><strong>{ct(item, 'title')}</strong><br />{item.opens_at && new Date(item.opens_at).getTime() > lastCheckedAt ? tr('Открытие: {0}', [formatDate(item.opens_at)]) : tr(item.lessons.find(value => value.locked_reason)?.locked_reason)}</p>)}<button className="secondary" onClick={refresh}>{tr('Проверить доступ снова')}</button></section> : <div className="empty-state"><h3>{structure.can_edit ? tr('Соберите первый урок') : tr('Материалы ещё готовятся')}</h3><p>{structure.can_edit ? tr('Создайте модуль, добавьте урок и наполните его учебными шагами.') : tr('Преподаватель добавит материалы. Они появятся в программе курса.')}</p>{structure.can_edit && <button onClick={() => { setEditing(true); setEditor({ kind: structure.modules.length ? 'lesson' : 'module', ...(structure.modules.length ? { module: structure.modules[0] } : {}) } as Editor) }}>{structure.modules.length ? tr('+ Урок') : tr('+ Модуль')}</button>}</div>)}
        <div className="action-row lesson-bottom-navigation" hidden={currentIndex < 0}><button className="secondary" disabled={currentIndex <= 0 || all[currentIndex-1]?.locked} onClick={() => select(all[currentIndex-1].id)}>{tr("← Предыдущий шаг")}</button><button disabled={currentIndex < 0 || currentIndex >= all.length-1 || all[currentIndex+1]?.locked} onClick={() => select(all[currentIndex+1].id)}>{tr("Следующий шаг →")}</button></div>
        {structure.can_edit && editing && lesson && <div className="action-row"><button className="secondary" onClick={() => action(`/api/learning/teacher/lessons/${lesson.id}/`, 'PATCH', { is_published: !lesson.is_published })}>{lesson.is_published ? tr("Скрыть урок") : tr("Опубликовать урок")}</button><ConfirmAction label={tr("Удалить урок")} question={tr("Удалить урок, шаги и материалы?")} onConfirm={() => action(`/api/learning/teacher/lessons/${lesson.id}/`, 'DELETE')} /></div>}
        {structure.can_edit && editing && <TeacherMediaUploader courseId={courseId} onUploaded={refresh} />}
        {lesson && !lesson.locked_reason && <LessonPulse key={`pulse-${lesson.id}-${runId}`} lessonId={lesson.id} runId={runId} />}
        {lesson && !lesson.locked_reason && <Discussion key={`${lesson.id}-${runId}`} lessonId={lesson.id} runId={runId} />}
      </div>
    </div>
  </section>
}
