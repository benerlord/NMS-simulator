import { keyMatch, coerceValue } from './jsonFieldMatch'
import type { FieldLike } from './jsonFieldMatch'

export interface BulkPreviewValid {
  index: number
  name: string
  attrs: Record<string, string>
  x: number
  y: number
  warnings: string[]  // 值不兼容的字段 label 列表（该字段不填但行仍导入）
}

export interface BulkPreviewSkipped {
  index: number
  name: string | null
  reason: string
  raw: Record<string, unknown>
}

export interface BulkPreview {
  valid: BulkPreviewValid[]
  skipped: BulkPreviewSkipped[]
  duplicatesInBatch: Array<{ index: number; name: string }>
  unmatchedKeys: string[]
}

export interface LayoutOptions {
  startX: number
  startY: number
  cols: number
  dx?: number
  dy?: number
}

export type ParseResult =
  | { ok: true; items: Record<string, unknown>[] }
  | { ok: false; error: string }

const DEFAULT_DX = 220
const DEFAULT_DY = 140

export function parseBulkJson(text: string): ParseResult {
  const trimmed = text.trim()
  if (!trimmed) return { ok: false, error: '请粘贴 JSON 数组' }
  let parsed: unknown
  try {
    parsed = JSON.parse(trimmed)
  } catch (e: any) {
    return { ok: false, error: `JSON 解析失败：${e?.message || '语法错误'}` }
  }
  if (!Array.isArray(parsed)) {
    return { ok: false, error: `JSON 顶层必须是数组，收到 ${typeof parsed}` }
  }
  const badIdx: number[] = []
  for (let i = 0; i < parsed.length; i++) {
    const v = parsed[i]
    if (v === null || typeof v !== 'object' || Array.isArray(v)) {
      badIdx.push(i)
    }
  }
  if (badIdx.length > 0) {
    return { ok: false, error: `第 ${badIdx.join(', ')} 项不是 object` }
  }
  return { ok: true, items: parsed as Record<string, unknown>[] }
}

function extractName(
  item: Record<string, unknown>,
  nameKey: string,
  typeName: string,
  autoIdx: number,
): string {
  if (nameKey === '__auto__') {
    return `${typeName}_${autoIdx}`
  }
  for (const [k, v] of Object.entries(item)) {
    if (keyMatch(k, nameKey)) {
      if (v === null || v === undefined) return ''
      return String(v).trim()
    }
  }
  return ''
}

export function buildBulkPreview(
  items: Record<string, unknown>[],
  fields: FieldLike[],
  nameKey: string,
  typeName: string,
  existingNames: Set<string>,
  layout: LayoutOptions,
): BulkPreview {
  const result: BulkPreview = {
    valid: [],
    skipped: [],
    duplicatesInBatch: [],
    unmatchedKeys: [],
  }
  const dx = layout.dx ?? DEFAULT_DX
  const dy = layout.dy ?? DEFAULT_DY
  const cols = Math.max(1, Math.floor(layout.cols))
  const seenInBatch = new Set<string>()
  const unmatchedSet = new Set<string>()

  let autoIdx = 1
  for (let idx = 0; idx < items.length; idx++) {
    const item = items[idx]
    const name = extractName(item, nameKey, typeName, autoIdx)
    if (nameKey === '__auto__') autoIdx += 1

    if (!name) {
      result.skipped.push({ index: idx, name: null, reason: 'name 为空', raw: item })
      continue
    }
    if (existingNames.has(name)) {
      result.skipped.push({ index: idx, name, reason: '画布已有同名节点', raw: item })
      continue
    }
    if (seenInBatch.has(name)) {
      result.duplicatesInBatch.push({ index: idx, name })
      continue
    }

    const attrs: Record<string, string> = {}
    const warnings: string[] = []

    for (const [jsonKey, jsonValue] of Object.entries(item)) {
      const matched = fields.find((f) => keyMatch(jsonKey, f.fieldKey))
      if (!matched) {
        unmatchedSet.add(jsonKey)
        continue
      }
      const coerced = coerceValue(jsonValue, matched.fieldType, matched.options)
      if (!coerced.ok) {
        warnings.push(matched.fieldLabel)
        continue
      }
      attrs[matched.fieldKey] = coerced.value
    }

    for (const f of fields) {
      if (!attrs[f.fieldKey] && f.defaultValue) {
        attrs[f.fieldKey] = f.defaultValue
      }
    }

    let missingRequired: string | null = null
    for (const f of fields) {
      if (f.required && !attrs[f.fieldKey]) {
        missingRequired = f.fieldLabel
        break
      }
    }
    if (missingRequired) {
      result.skipped.push({
        index: idx,
        name,
        reason: `必填字段「${missingRequired}」缺失`,
        raw: item,
      })
      continue
    }

    const validIdx = result.valid.length
    const x = Math.round(layout.startX + (validIdx % cols) * dx)
    const y = Math.round(layout.startY + Math.floor(validIdx / cols) * dy)

    result.valid.push({ index: idx, name, attrs, x, y, warnings })
    seenInBatch.add(name)
  }

  result.unmatchedKeys = Array.from(unmatchedSet)
  return result
}
