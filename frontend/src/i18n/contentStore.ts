/** Response objects carry their own field translations; no shared text cache. */
export async function readApiJson(response: Response) { return response.json() }

export function originalPayload(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(originalPayload)
  if (Object.prototype.toString.call(value) === '[object Date]') return value
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).filter(([key]) => key !== '_text' && key !== '_course_policy').map(([key, child]) => [key, originalPayload(child)]))
  return value
}
