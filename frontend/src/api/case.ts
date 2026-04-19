const SNAKE_RE = /_([a-z0-9])/g
const CAMEL_RE = /[A-Z]/g

const toCamel = (key: string): string =>
  key.replace(SNAKE_RE, (_, c: string) => c.toUpperCase())

const toSnake = (key: string): string =>
  key.replace(CAMEL_RE, (c) => `_${c.toLowerCase()}`)

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

export function snakeizeKeys<T = unknown>(input: unknown): T {
  if (Array.isArray(input)) {
    return input.map((item) => snakeizeKeys(item)) as unknown as T
  }
  if (input && typeof input === 'object' && input.constructor === Object) {
    const out: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(input as Record<string, unknown>)) {
      out[toSnake(k)] = snakeizeKeys(v)
    }
    return out as T
  }
  return input as T
}
