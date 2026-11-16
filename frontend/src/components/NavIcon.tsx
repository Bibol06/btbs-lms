const paths: Record<string, string> = {
  questions: 'M4 3h16v13H9l-5 5V3zm4 5h8m-8 4h5',
  attention: 'm12 3 10 18H2L12 3zm0 6v5m0 3h.01',
  bank: 'M4 3h16v18H4V3zm4 5h8m-8 4h8m-8 4h5',
  learning: 'M3 9l9-6 9 6v11H3V9zm6 11v-7h6v7',
  admin: 'M3 3h7v7H3zm11 0h7v7h-7zM3 14h7v7H3zm11 0h7v7h-7z',
  teaching: 'M4 4h7a3 3 0 0 1 3 3v14a4 4 0 0 0-4-2H4V4zm10 3a3 3 0 0 1 3-3h4v15h-3a4 4 0 0 0-4 2',
  deadlines: 'M8 2v4m8-4v4M3 10h18M4 4h16v17H4V4zm4 10h3m-3 3h7',
  reviews: 'M9 4H5v17h14V4h-4M9 2h6v5H9V2zm-1 12 3 3 5-6',
  analytics: 'M4 3v18h18M8 16v-5m5 5V7m5 9V4',
  students: 'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2m18 0v-2a4 4 0 0 0-3-3.9M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8m8-7.8a4 4 0 0 1 0 7.6',
  catalog: 'M3 3h7v7H3zm11 0h7v7h-7zM3 14h7v7H3zm11 0h7v7h-7z',
  'admin-courses': 'M4 4h16v16H4V4zm5 0v16m-5-5h16',
  'admin-teachers': 'm2 8 10-5 10 5-10 5L2 8zm4 3v6l6 4 6-4v-6m4-3v8',
  users: 'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2m18 0v-2a4 4 0 0 0-3-3.9M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8m8-7.8a4 4 0 0 1 0 7.6',
  'admin-activity': 'M4 4h16v17H4V4zm4-2v4m8-4v4M8 10h8m-8 4h8m-8 4h5',
  notifications: 'M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M9 21h6',
  profile: 'M20 21v-2a5 5 0 0 0-5-5H9a5 5 0 0 0-5 5v2m8-11a4 4 0 1 0 0-8 4 4 0 0 0 0 8',
}

export default function NavIcon({ name }: { name: string }) {
  return <svg className="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name] || paths.catalog} /></svg>
}
