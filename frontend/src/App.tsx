import { ct } from './i18n/content'
import { readApiJson } from './i18n/contentStore'
import { localizedLabels, t as tr } from './i18n/language'
import AnalyticsPage from './pages/analytics/AnalyticsPage'
import usePresence from './pages/analytics/usePresence'
import { canonicalPage, homeFor, navigationFor, routePage, workspaceFor, workspaceTitle } from './workspaces'
import SystemPage from './pages/admin/SystemPage'
import AdminControl from './pages/management/AdminControl'
import StudentsPage from './pages/management/StudentsPage'
import ReviewQueue from './pages/study/ReviewQueue'
import './pages/management/Management.css'
import NavIcon from './components/NavIcon'
import WorkspaceSearch from './components/WorkspaceSearch'
import LanguageSwitcher from './components/LanguageSwitcher'
import PasswordRecovery from './components/PasswordRecovery'
import { bindLanguageUser, getLanguageRevision, useLanguage } from './i18n/language'
import ReviewWorkspace from './pages/workspace/Grading'
import QuestionBank from './pages/workspace/AuthorTools'
import CoursePreview from './pages/workspace/CoursePreview'
import { AttentionPage, QuestionsPage } from './pages/workspace/WorkspaceHome'
import TeacherDashboard from './pages/teacher/TeacherDashboard'
import CoursesPage from './pages/courses/CoursesPage'
import UsersPage from './pages/admin/UsersPage'
import MyLearning from './pages/courses/MyLearning'
import Notifications, { NotificationCount } from './pages/communication/Notifications'
import { useEffect, useState, type FormEvent } from 'react'
import { enrollRequest, getCookie, loginRequest, registerRequest, type User } from './api'
import Profile from './pages/Profile'
import AgendaPage from './pages/study/AgendaPage'
import './App.css'
import './Workspace.css'
import './Brand.css'
import './pages/workspace/WorkspaceHub.css'
import './styles/shell.css'
import './styles/patterns.css'
import AccountMenu from './components/AccountMenu'

const roles = localizedLabels({
  student: 'Студент',
  teacher: 'Преподаватель',
  admin: 'Администратор',
})

function App() {
  useLanguage()
  const [user, setUser] = useState<User | null>(null)
  usePresence(['preview', 'reset-password', 'forgot-password'].includes(routePage()) ? undefined : user?.id)
  const [mobileMenu, setMobileMenu] = useState(false)
  const [username, setUsername] = useState('')
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [password, setPassword] = useState('')
  const [email, setEmail] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(routePage)
  const [profileId, setProfileId] = useState(() => new URLSearchParams(location.hash.slice(1)).get('profile') || 'me')
  const [showLogin, setShowLogin] = useState(false)
  const [pendingCourseId, setPendingCourseId] = useState<number | null>(null)
  const [openCourseId, setOpenCourseId] = useState<number | null>(() => Number(new URLSearchParams(location.hash.slice(1)).get('course')) || null)
  const [routeRevision, setRouteRevision] = useState(0)
  useEffect(() => {
    function navigate() {
      setMobileMenu(false)
      const id = Number(new URLSearchParams(location.hash.slice(1)).get('course')) || null
      setOpenCourseId(id)
      const route = new URLSearchParams(location.hash.slice(1))
      if (route.has('profile')) setProfileId(route.get('profile') || 'me')
      setPage(routePage())
      setRouteRevision(v => v + 1)
    }
    window.addEventListener('hashchange', navigate)
    return () => window.removeEventListener('hashchange', navigate)
  }, [])
  function openCourse(id: number | null) {
    if (!id) { navigatePage(user ? workspaceFor(user) === 'admin' ? 'admin-courses' : workspaceFor(user) === 'teacher' ? 'teaching' : 'catalog' : 'catalog'); return }
    setOpenCourseId(id)
    if (id) setPage('catalog')
    window.history.replaceState(null, '', id ? `#course=${id}` : location.pathname)
  }

  useEffect(() => {
    let active = true
    const languageRevision = getLanguageRevision()
    fetch('/api/auth/csrf/', { credentials: 'include' }).catch(() => {})

    fetch('/api/auth/me/', {
      credentials: 'include',
    })
      .then(async response => {
        if (response.ok && active) {
          const currentUser: User = await readApiJson(response)
          if (!active) return
          bindLanguageUser(currentUser.id, currentUser.preferred_language, languageRevision)
          setUser(currentUser)
          if (!location.hash) { const home = homeFor(currentUser); setPage(home); window.history.replaceState(null, '', `#page=${home}`) }
        }
      })
      .catch(() => { if (active) setError('Ошибка подключения к Django') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  async function completePendingEnroll(courseId: number) {
    await enrollRequest(courseId)
    setPendingCourseId(null)
    setPage('catalog')
    setOpenCourseId(courseId)
  }

  async function handleLogin(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setError('')
    if (authMode === 'register' && password !== confirmPassword) {
      setError('Пароли не совпадают')
      return
    }
    setLoading(true)

    let signedIn = false
    try {
      const nextUser = authMode === 'register'
        ? await registerRequest(username, email, password, firstName, lastName)
        : await loginRequest(username, password)

      signedIn = true
      bindLanguageUser(nextUser.id, nextUser.preferred_language)
      setUser(nextUser)
      if (!openCourseId && pendingCourseId === null) navigatePage(homeFor(nextUser))
      setPassword('')
      setConfirmPassword('')
      setShowLogin(false)
      setAuthMode('login')

      if (pendingCourseId !== null) {
        const id = pendingCourseId
        setPendingCourseId(null)
        try {
          await completePendingEnroll(id)
        } catch (err) {
          // Вход уже выполнен; не показываем повторно модальное окно авторизации.
          setError(err instanceof Error ? err.message : 'Не удалось записаться на курс')
        }
      }
    } catch (err) {
      if (!signedIn) {
        setError(err instanceof Error ? err.message : 'Ошибка соединения')
      }
    } finally {
      setLoading(false)
    }
  }

  async function handleLogout() {
    try {
      const response = await fetch('/api/auth/logout/', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'X-CSRFToken': getCookie('csrftoken'),
        },
      })

      if (!response.ok) {
        throw new Error(tr("Ошибка выхода"))
      }

      setUser(null)
      bindLanguageUser(null)
      setError('')
      setPage('catalog')
      setOpenCourseId(null)
      window.history.replaceState(null, '', '#page=catalog')
      setPendingCourseId(null)
    } catch {
      setError('Не удалось выйти из системы')
    }
  }

  function requestAuthForCourse(courseId: number) {
    setPendingCourseId(courseId)
    setShowLogin(true)
    setAuthMode('login')
    setError('')
  }

  if (loading && !user && !showLogin) {
    return <div className="app-loading" role="status"><img src="/brand/btbs-color.png" alt="BTBS" width="56" height="66" /><p>{tr("Загружаем ваше пространство…")}</p></div>
  }

  const workspace = workspaceFor(user)
  const activePage = canonicalPage(page, user)
  const activeNav = activePage === 'review-workspace' ? 'reviews' : activePage === 'preview' ? workspace === 'admin' ? 'admin-courses' : 'teaching' : activePage
  const items = user ? navigationFor(user).map(item => ({ ...item, label: tr(item.label) })) : [{ id: 'catalog', label: tr("Каталог курсов"), icon: '▦' }]
  const inCourse = activePage === 'catalog' && openCourseId !== null
  const personalLearning = Boolean(user && workspace !== 'student' && new URLSearchParams(location.hash.slice(1)).get('mode') === 'personal' && ['learning', 'deadlines', 'analytics'].includes(activePage))
  const recoveryPage = ['forgot-password', 'reset-password'].includes(activePage)
  const permitted = recoveryPage || (!user ? activePage === 'catalog' : items.some(item => item.id === activePage) || ['profile', 'notifications'].includes(activePage) || (workspace !== 'student' && ['review-workspace', 'preview'].includes(activePage)) || inCourse || personalLearning)
  function navigatePage(next: string) {
    setMobileMenu(false)
    setPage(next); setOpenCourseId(null)
    setRouteRevision(v => v + 1)
    if (next === 'profile') setProfileId('me')
    window.location.assign(next === 'profile' ? '#profile=me' : `#page=${next}`)
  }
  return (
    <div className={`layout ${inCourse ? 'course-mode' : ''}`}>
      <header className="topbar">
        {user && <button className="workspace-menu-toggle" aria-label={tr("Меню кабинета")} aria-expanded={mobileMenu} aria-controls="workspace-navigation" onClick={() => setMobileMenu(v => !v)}>{mobileMenu ? '×' : '☰'}</button>}
        <a className="brand notranslate" translate="no" lang="en" href={`#page=${user ? homeFor(user) : 'catalog'}`} aria-label="BTBS"><img src="/brand/btbs-color.png" alt="" width="43" height="51" /><span className="brand-wordmark"><strong>BTBS</strong></span></a>
        <div className="workspace-context"><span>{user ? workspaceTitle(user) : tr("Онлайн-обучение")}</span>{inCourse || activePage === 'preview' ? <a href={`#page=${homeFor(user)}`}>{tr("← Вернуться в кабинет")}</a> : <strong>{ct(items.find(i => i.id === activeNav), "label") || (activePage === 'profile' ? tr("Мой профиль") : activePage === 'notifications' ? tr("Уведомления") : tr("Рабочее пространство"))}</strong>}</div>
        {user && user.admin_scope !== 'system' && <WorkspaceSearch />}
        <div className="header-actions">{user ? <>
          <button className="notification-button" aria-label={tr("Уведомления")} aria-current={activePage === 'notifications' ? 'page' : undefined} onClick={() => navigatePage('notifications')}><NavIcon name="notifications" /><NotificationCount /></button>
          <AccountMenu name={user.display_name || user.username} roleLabel={user.role_label ? tr(user.role_label) : roles[user.role]} onProfile={() => navigatePage('profile')} onLogout={handleLogout} />
        </> : <>
          <LanguageSwitcher />
          <button className="login-button" onClick={() => { setPendingCourseId(null); setAuthMode('login'); setShowLogin(true); setError('') }}>{tr("Войти")}</button>
          <button className="register-button" onClick={() => { setPendingCourseId(null); setAuthMode('register'); setShowLogin(true); setError('') }}>{tr("Регистрация")}</button>
        </>}</div>
      </header>
      <aside id="workspace-navigation" className={`sidebar ${mobileMenu ? 'is-open' : ''}`}>
        <div className="sidebar-caption">{user ? workspaceTitle(user) : tr("Образовательная платформа")}</div>
        <nav aria-label={user ? workspaceTitle(user) : tr("Навигация")}>
          {items.map(item => <button key={item.id} className={activeNav === item.id ? 'active' : ''} aria-current={activeNav === item.id ? 'page' : undefined} onClick={() => navigatePage(item.id)}><NavIcon name={item.id} />{ct(item, "label")}</button>)}
        </nav>
        
      </aside>
      <main className="content">
        {personalLearning && <p className="management-note"><a href={`#page=${homeFor(user)}`}>{tr("Вернуться в ")}{workspaceTitle(user).toLowerCase()} →</a></p>}
        {error && !showLogin && <p className="error">{tr(error)}</p>}

        
{recoveryPage ? <PasswordRecovery key={activePage + routeRevision} reset={activePage === 'reset-password'} login={() => { navigatePage('catalog'); setShowLogin(true); setAuthMode('login'); setError('') }} /> : activePage === 'system' && permitted && user ? <SystemPage /> : activePage === 'preview' && permitted && user ? <CoursePreview key={routeRevision} /> : activePage === 'review-workspace' && permitted && user ? <ReviewWorkspace key={routeRevision} /> : activePage === 'questions' && permitted && user ? <QuestionsPage key={routeRevision} /> : activePage === 'attention' && permitted && user ? <AttentionPage key={routeRevision} /> : activePage === 'bank' && permitted && user ? <QuestionBank key={routeRevision} /> : !permitted ? <section className="workspace-denied"><h2>{tr("Этот раздел недоступен в вашем кабинете")}</h2><p>{tr("Ваш кабинет: ")}{workspaceTitle(user)}{tr(". Выберите нужный раздел в меню.")}</p><button onClick={() => navigatePage(user ? homeFor(user) : 'catalog')}>{tr("Перейти в свой кабинет")}</button></section> : activePage === 'analytics' && user ? <AnalyticsPage key={`${user.id}-${routeRevision}`} user={user} /> : activePage === 'profile' && user ? <Profile key={profileId} profileId={profileId} onSaved={name => setUser(current => current ? { ...current, display_name: name } : current)} /> : activePage === 'notifications' && user ? <Notifications /> : activePage === 'learning' && user ? <MyLearning /> : activePage === 'deadlines' && user ? <AgendaPage /> : activePage === 'users' && user?.role === 'admin' ? <UsersPage current={user} /> : activePage === 'students' && user ? <StudentsPage key={`${user.id}-${routeRevision}`} admin={workspace === 'admin'} /> : activePage === 'reviews' && user ? workspace === 'admin' ? <AdminControl key={`reviews-${routeRevision}`} user={user} section="reviews" /> : <section className="management-page"><div><h2>{tr("Проверка работ моих учеников")}</h2></div><ReviewQueue userId={user.id} /></section> : ['admin', 'admin-teachers', 'admin-courses', 'admin-activity'].includes(activePage) && user?.role === 'admin' ? <AdminControl key={`${activePage}-${routeRevision}`} user={user} section={activePage === 'admin-teachers' ? 'teachers' : activePage === 'admin-courses' ? 'courses' : activePage === 'admin-activity' ? 'activity' : 'overview'} /> : activePage === 'teaching' && user ? <TeacherDashboard /> : <CoursesPage key={routeRevision} user={user} openCourseId={openCourseId} onOpenCourse={openCourse} onNeedAuth={requestAuthForCourse} />}

      </main>
      <footer className="workspace-footer"><div><img src="/brand/btbs-black.png" alt="BTBS" width="27" height="32" /><span>{tr("Цифровое пространство обучения")}</span></div><span>{tr("Знания. Практика. Результат.")}</span></footer>

      {showLogin && !recoveryPage && (
        <div className="login-overlay">
          <div className="login-dialog" role="dialog" aria-modal="true" aria-labelledby="auth-title">
          <aside className="login-brand-panel"><img src="/brand/btbs-white.png" alt="BTBS" width="130" height="152" /><span className="login-brand-label">{tr("Образовательная платформа")}</span><h2>{tr("Знания, которые")}<br />{tr("становятся навыками.")}</h2><span className="login-brand-footer">{tr("Учитесь. Пробуйте. Достигайте.")}</span></aside>
          <div className="login-card">
            <div className="auth-language"><LanguageSwitcher /></div>
            <p className="eyebrow">{tr("Добро пожаловать в BTBS")}</p>
            <h1 id="auth-title">{authMode === 'login' ? tr("С возвращением") : tr("Начните учиться")}</h1>
            

            <form onSubmit={handleLogin}>
              {authMode === 'register' && <>
                <label>{tr("Фамилия")}<input autoComplete="family-name" value={lastName} onChange={e => setLastName(e.target.value)} maxLength={150} required /></label>
                <label>{tr("Имя")}<input autoComplete="given-name" value={firstName} onChange={e => setFirstName(e.target.value)} maxLength={150} required /></label>
              </>}
              <input
                type="text"
                placeholder={authMode === 'login' ? tr("Логин или email") : tr("Логин")}
                aria-label={authMode === 'login' ? tr("Логин или email") : tr("Логин")}
                autoComplete="username"
                autoCapitalize="none"
                autoCorrect="off"
                spellCheck={false}
                value={username}
                onChange={e => setUsername(e.target.value)}
                required
              />

              {authMode === 'register' && (
                <input
                  type="email"
                  placeholder={tr("Email")}
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  autoComplete="email"
                  required
                />
              )}

              <input
                type="password"
                placeholder={tr("Пароль")}
                aria-label={tr("Пароль")}
                value={password}
                onChange={e => setPassword(e.target.value)}
                autoComplete={authMode === 'register' ? 'new-password' : 'current-password'}
                minLength={authMode === 'register' ? 8 : undefined}
                required
              />

              {authMode === 'register' && (
                <input
                  type="password"
                  placeholder={tr("Повторите пароль")}
                  value={confirmPassword}
                  onChange={e => setConfirmPassword(e.target.value)}
                  autoComplete="new-password"
                  required
                />
              )}

              {error && <p className="error">{tr(error)}</p>}

              {authMode === 'login' && <a className="forgot-password-link" href="#page=forgot-password" onClick={() => { setShowLogin(false); setPassword(''); setError('') }}>{tr('Забыли пароль?')}</a>}
              <button type="submit" disabled={loading}>
                {loading ? tr("Подключаемся...") : authMode === 'login' ? tr("Войти") : tr("Создать аккаунт")}
              </button>
              <button
                type="button"
                className="login-cancel"
                onClick={() => {
                  setAuthMode(authMode === 'login' ? 'register' : 'login')
                  setError('')
                  setPassword('')
                  setConfirmPassword('')
                }}
              >
                {authMode === 'login' ? tr("Нет аккаунта? Зарегистрироваться") : tr("Уже есть аккаунт? Войти")}
              </button>
            </form>
          </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default App
