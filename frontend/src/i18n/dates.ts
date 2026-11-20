import { getLanguage, getLocale } from './language'

// Chromium ships reduced locale data for Kazakh: Intl prints "2026 M11 23" instead of
// month names. Kazakh dates are therefore formatted here; ru/en keep Intl.
const KK_MONTHS = ['қаңтар', 'ақпан', 'наурыз', 'сәуір', 'мамыр', 'маусым', 'шілде', 'тамыз', 'қыркүйек', 'қазан', 'қараша', 'желтоқсан']
const KK_MONTHS_SHORT = ['қаң.', 'ақп.', 'нау.', 'сәу.', 'мам.', 'мау.', 'шіл.', 'там.', 'қыр.', 'қаз.', 'қар.', 'жел.']
const KK_WEEKDAYS = ['жс', 'дс', 'сс', 'ср', 'бс', 'жм', 'сб']

export type DateKind = 'datetime' | 'date' | 'dayMonth' | 'weekdayDayMonth'

const pad = (value: number) => String(value).padStart(2, '0')

/** Format a date for the interface language. */
export function localDate(value: Date, kind: DateKind = 'datetime'): string {
  if (Number.isNaN(value.getTime())) return ''
  if (getLanguage() === 'kk') {
    const day = value.getDate(), month = value.getMonth(), year = value.getFullYear()
    const time = `${pad(value.getHours())}:${pad(value.getMinutes())}`
    if (kind === 'date') return `${pad(day)}.${pad(month + 1)}.${year}`
    if (kind === 'dayMonth') return `${day} ${KK_MONTHS_SHORT[month]}`
    if (kind === 'weekdayDayMonth') return `${KK_WEEKDAYS[value.getDay()]}, ${day} ${KK_MONTHS_SHORT[month]}`
    return `${day} ${KK_MONTHS[month]} ${year}, ${time}`
  }
  const options: Record<DateKind, Intl.DateTimeFormatOptions> = {
    datetime: { dateStyle: 'medium', timeStyle: 'short' },
    date: {},
    dayMonth: { day: 'numeric', month: 'short' },
    weekdayDayMonth: { weekday: 'short', day: 'numeric', month: 'short' },
  }
  return kind === 'date' ? value.toLocaleDateString(getLocale()) : value.toLocaleString(getLocale(), options[kind])
}
