function lines(value: FormDataEntryValue | null) {
  return String(value ?? '').split('\n').map(line => line.trim()).filter(Boolean)
}

/** Context, instructions and hints of the practice screen, shared by the create and edit forms. */
export function practiceValues(form: FormData) {
  return { context: String(form.get('context') ?? ''), instructions: lines(form.get('instructions')), hints: lines(form.get('hints')) }
}
