const SNAKE_RE = /_([a-z0-9])/g

const toCamel = (key: string): string =>
  key.replace(SNAKE_RE, (_, c: string) => c.toUpperCase())

export function camelizeKeys<T = unknown>(input: unknown): T {
  if (Array.isArray(input)) {
    return input.map((item) => camelizeKeys(item)) as unknown as T
  }
  if (input && typeof input === 'object' && input.constructor === Object) {
    const out: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(input as Record<string, unknown>)) {
      out[toCamel(k)] = camelizeKeys(v)
    }
    return out as T
  }
  return input as T
}
