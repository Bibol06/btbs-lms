import { t as tr } from '../../i18n/language'

export default function PracticeFields({ initial }: { initial?: { context: string; instructions: string[]; hints: string[] } }) {
  return <>
    <label>{tr("Что уже подготовлено (контекст)")}<textarea name="context" rows={3} maxLength={10000} defaultValue={initial?.context} placeholder={tr("Например: список scores уже загружен")} /></label>
    <label>{tr("Инструкции — по одной на строку")}<textarea name="instructions" rows={4} defaultValue={initial?.instructions.join('\n')} placeholder={tr("Посчитайте сумму\nВыведите результат")} /></label>
    <label>{tr("Подсказки — по одной на строку, открываются по очереди")}<textarea name="hints" rows={3} defaultValue={initial?.hints.join('\n')} /></label>
  </>
}
