import { qa, type Role } from './qa'

export type Visit = { role: Role; label: string; hash: string }

const c = qa.courses, r = qa.runs, s = qa.steps
const course = (id: number, run: number, tab: string) => `#course=${id}&run=${run}&tab=${tab}`
const step = (id: number) => `#course=${c.main}&run=${r.cohort}&step=${id}`
const pages = (role: Role, ids: string[]) => ids.map(id => ({ role, label: id, hash: `#page=${id}` }))

const adminPages = ['admin', 'attention', 'analytics', 'admin-teachers', 'students', 'reviews', 'questions', 'admin-courses', 'bank', 'admin-activity', 'system', 'catalog']

/** Every page each role can reach (routes from workspaces.ts / App.tsx). */
export const visits: Visit[] = [
  { role: 'guest', label: 'catalog', hash: '#page=catalog' },
  { role: 'guest', label: 'course-card', hash: `#course=${c.main}` },
  { role: 'guest', label: 'forgot-password', hash: '#page=forgot-password' },

  ...pages('student', ['learning', 'deadlines', 'analytics', 'catalog', 'notifications']),
  { role: 'student', label: 'profile', hash: '#profile=me' },
  ...['overview', 'plan', 'results', 'announcements', 'messages', 'settings'].map(tab => ({ role: 'student' as Role, label: `course-${tab}`, hash: course(c.main, r.cohort, tab) })),
  ...Object.entries(s).map(([kind, id]) => ({ role: 'student' as Role, label: `player-${kind}`, hash: step(id) })),
  { role: 'student', label: 'edge-course-start', hash: course(c.edge, r.edge, 'lessons') },
  { role: 'student', label: 'empty-course-card', hash: `#course=${c.empty}` },
  ...pages('student_empty', ['learning', 'deadlines', 'analytics']),

  ...pages('teacher', ['teaching', 'reviews', 'questions', 'attention', 'students', 'analytics', 'bank', 'catalog', 'notifications']),
  { role: 'teacher', label: 'profile', hash: '#profile=me' },
  ...['plan', 'overview', 'lessons', 'publication', 'assignments', 'quizzes', 'results', 'announcements', 'messages', 'groups', 'settings'].map(tab => ({ role: 'teacher' as Role, label: `course-${tab}`, hash: course(c.main, r.cohort, tab) })),
  { role: 'teacher', label: 'edge-course-editor', hash: course(c.edge, r.edge, 'lessons') },
  { role: 'teacher', label: 'empty-course-editor', hash: `#course=${c.empty}&tab=lessons` },
  { role: 'teacher', label: 'draft-course-editor', hash: `#course=${c.draft}&tab=lessons` },
  { role: 'teacher', label: 'student-preview', hash: `#page=preview&course_id=${c.main}&run_id=${r.cohort}` },
  { role: 'teacher', label: 'edge-student-preview', hash: `#page=preview&course_id=${c.edge}&run_id=${r.edge}` },

  ...pages('editor', ['teaching']),
  { role: 'editor', label: 'course-lessons', hash: course(c.main, r.self_paced, 'lessons') },
  { role: 'editor', label: 'course-publication', hash: course(c.main, r.self_paced, 'publication') },
  ...pages('group_teacher', ['teaching', 'reviews']),
  { role: 'group_teacher', label: 'course-results', hash: course(c.main, r.cohort, 'results') },

  ...pages('admin_full', [...adminPages, 'users']),
  ...pages('admin_learning', adminPages.filter(id => id !== 'system')),
  ...pages('admin_system', ['system', 'users', 'catalog']),
]
