export interface FieldLike {
  fieldKey: string
  fieldLabel: string
  fieldType: 'text' | 'number' | 'select' | 'boolean' | 'array'
  maxLength?: number | null
  defaultValue?: string | null
  options?: string | null
  required: boolean
  sortOrder: number
}

export interface FillPreview {
  toFill: Array<{ fieldKey: string; fieldLabel: string; newValue: string }>
  toOverwrite: Array<{ fieldKey: string; fieldLabel: string; oldValue: string; newValue: string }>
  incompatible: Array<{ fieldKey: string; fieldLabel: string; jsonValue: unknown; reason: string }>
  unmatched: string[]
}

export interface GeneratePreview {
  toCreate: FieldLike[]
  skippedExisting: string[]
  skippedInferable: string[]
}

function normalize(s: string): string {
  return s.replace(/[_\-\s]/g, '').toLowerCase()
}

export function keyMatch(jsonKey: string, fieldKey: string): boolean {
  if (jsonKey === fieldKey) return true
  if (jsonKey.toLowerCase() === fieldKey.toLowerCase()) return true
  return normalize(jsonKey) === normalize(fieldKey)
}

type MatchableField = Pick<FieldLike, 'fieldKey' | 'fieldLabel' | 'fieldType' | 'options'>

export function coerceValue(
  jsonValue: unknown,
  fieldType: FieldLike['fieldType'],
  options: string | null | undefined,
): { ok: true; value: string } | { ok: false; reason: string } {
  if (fieldType === 'text') {
    if (jsonValue === null) return { ok: true, value: '' }
    if (typeof jsonValue === 'string') return { ok: true, value: jsonValue }
    if (typeof jsonValue === 'number' || typeof jsonValue === 'boolean') {
      return { ok: true, value: String(jsonValue) }
    }
    return { ok: false, reason: 'text 字段不支持 object/array 值' }
  }
  if (fieldType === 'number') {
    if (typeof jsonValue === 'number') return { ok: true, value: String(jsonValue) }
    if (typeof jsonValue === 'string') {
      const n = Number(jsonValue)
      if (Number.isNaN(n)) return { ok: false, reason: '值无法解析为数字' }
      return { ok: true, value: String(n) }
    }
    return { ok: false, reason: 'number 字段值必须是数字或数字字符串' }
  }
  if (fieldType === 'select') {
    if (typeof jsonValue !== 'string') return { ok: false, reason: 'select 字段值必须是字符串' }
    const opts = (options || '').split(',').map((s) => s.trim()).filter(Boolean)
    if (!opts.includes(jsonValue)) return { ok: false, reason: `值不在选项列表 [${opts.join(', ')}] 中` }
    return { ok: true, value: jsonValue }
  }
  if (fieldType === 'boolean') {
    if (typeof jsonValue === 'boolean') return { ok: true, value: String(jsonValue) }
    if (jsonValue === 'true' || jsonValue === 'false') return { ok: true, value: jsonValue }
    return { ok: false, reason: 'boolean 字段值必须是 true/false' }
  }
  if (fieldType === 'array') {
    if (Array.isArray(jsonValue)) return { ok: true, value: JSON.stringify(jsonValue) }
    if (typeof jsonValue === 'string') {
      try {
        const p = JSON.parse(jsonValue)
        if (Array.isArray(p)) return { ok: true, value: jsonValue }
      } catch { /* ignore */ }
      return { ok: false, reason: '值不是合法的 JSON array 字符串' }
    }
    return { ok: false, reason: 'array 字段值必须是数组' }
  }
  return { ok: false, reason: `未知字段类型 ${fieldType}` }
}

export function buildFillPreview(
  json: Record<string, unknown>,
  fields: MatchableField[],
  currentValues: Record<string, string>,
): FillPreview {
  const result: FillPreview = { toFill: [], toOverwrite: [], incompatible: [], unmatched: [] }

  for (const [jsonKey, jsonValue] of Object.entries(json)) {
    const matched = fields.find((f) => keyMatch(jsonKey, f.fieldKey))
    if (!matched) {
      result.unmatched.push(jsonKey)
      continue
    }
    const coerced = coerceValue(jsonValue, matched.fieldType, matched.options)
    if (!coerced.ok) {
      result.incompatible.push({
        fieldKey: matched.fieldKey,
        fieldLabel: matched.fieldLabel,
        jsonValue,
        reason: coerced.reason,
      })
      continue
    }
    const current = currentValues[matched.fieldKey] ?? ''
    if (current === '' || current === coerced.value) {
      result.toFill.push({
        fieldKey: matched.fieldKey,
        fieldLabel: matched.fieldLabel,
        newValue: coerced.value,
      })
    } else {
      result.toOverwrite.push({
        fieldKey: matched.fieldKey,
        fieldLabel: matched.fieldLabel,
        oldValue: current,
        newValue: coerced.value,
      })
    }
  }
  return result
}

function inferField(jsonKey: string, jsonValue: unknown, sortOrder: number):
  | { ok: true; field: FieldLike }
  | { ok: false; reason: string } {
  if (jsonValue === null) return { ok: false, reason: 'null 无法推断类型' }
  if (typeof jsonValue === 'object' && !Array.isArray(jsonValue)) {
    return { ok: false, reason: '嵌套 object 不支持' }
  }
  if (typeof jsonValue === 'string') {
    const maxLength = Math.max(50, Math.ceil((jsonValue.length + 20) / 10) * 10)
    return {
      ok: true,
      field: {
        fieldKey: jsonKey,
        fieldLabel: jsonKey,
        fieldType: 'text',
        maxLength,
        defaultValue: jsonValue,
        options: null,
        required: false,
        sortOrder,
      },
    }
  }
  if (typeof jsonValue === 'number') {
    return {
      ok: true,
      field: {
        fieldKey: jsonKey,
        fieldLabel: jsonKey,
        fieldType: 'number',
        maxLength: null,
        defaultValue: String(jsonValue),
        options: null,
        required: false,
        sortOrder,
      },
    }
  }
  if (typeof jsonValue === 'boolean') {
    return {
      ok: true,
      field: {
        fieldKey: jsonKey,
        fieldLabel: jsonKey,
        fieldType: 'boolean',
        maxLength: null,
        defaultValue: String(jsonValue),
        options: null,
        required: false,
        sortOrder,
      },
    }
  }
  if (Array.isArray(jsonValue)) {
    return {
      ok: true,
      field: {
        fieldKey: jsonKey,
        fieldLabel: jsonKey,
        fieldType: 'array',
        maxLength: null,
        defaultValue: JSON.stringify(jsonValue),
        options: null,
        required: false,
        sortOrder,
      },
    }
  }
  return { ok: false, reason: `未识别的 JSON 值类型 ${typeof jsonValue}` }
}

export function buildGeneratePreview(
  json: Record<string, unknown>,
  existingFields: Pick<FieldLike, 'fieldKey'>[],
  sortOrderStart: number,
): GeneratePreview {
  const result: GeneratePreview = { toCreate: [], skippedExisting: [], skippedInferable: [] }
  let i = 0

  for (const [jsonKey, jsonValue] of Object.entries(json)) {
    const exists = existingFields.some((f) => keyMatch(jsonKey, f.fieldKey))
    if (exists) {
      result.skippedExisting.push(jsonKey)
      continue
    }
    const inferred = inferField(jsonKey, jsonValue, sortOrderStart + i)
    if (!inferred.ok) {
      result.skippedInferable.push(jsonKey)
      continue
    }
    result.toCreate.push(inferred.field)
    i += 1
  }
  return result
}
