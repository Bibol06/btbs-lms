export type Chapter = { start: number; title: string; text: string }

const STAMP = /^\s*(?:(\d{1,2}):)?(\d{1,2}):(\d{2})\s*[-–—.)]?\s*(.*)$/

/** "MM:SS Title" (or H:MM:SS) starts a chapter; following lines are its text. */
export function parseTranscript(source: string): Chapter[] {
  const chapters: Chapter[] = []
  for (const line of source.split('\n')) {
    const match = line.match(STAMP)
    if (match) {
      const start = Number(match[1] ?? 0) * 3600 + Number(match[2]) * 60 + Number(match[3])
      chapters.push({ start, title: match[4].trim(), text: '' })
    } else if (line.trim()) {
      if (!chapters.length) chapters.push({ start: 0, title: '', text: '' })
      const last = chapters[chapters.length - 1]
      last.text = last.text ? `${last.text} ${line.trim()}` : line.trim()
    }
  }
  return chapters
}
