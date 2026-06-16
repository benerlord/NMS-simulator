import type { NodeTypeFieldItem, EdgeTypeFieldItem } from '@/api/types'
import type { AlarmSchemaFieldItem } from '@/api/alarmSchema'

type FieldLike = Pick<
  NodeTypeFieldItem | EdgeTypeFieldItem | AlarmSchemaFieldItem,
  'fieldKey' | 'fieldType' | 'required'
>

/**
 * 校验整张表单：返回 { [fieldKey]: errorMessage }。
 * - required 字段空值 → '此字段为必填项'
 * - array 字段非合法 JSON array → 'JSON 语法错误' 或 '必须是 JSON array'
 * - 其它类型暂不在前端校验（依赖后端 Pydantic + DB 约束）
 */
export function validateFields(
  fields: FieldLike[],
  formData: Record<string, string>,
): Record<string, string> {
  const errs: Record<string, string> = {}
  for (const field of fields) {
    const value = formData[field.fieldKey] ?? ''
    if (field.required && !value) {
      errs[field.fieldKey] = '此字段为必填项'
      continue
    }
    if (field.fieldType === 'array' && value) {
      try {
        const parsed = JSON.parse(value)
        if (!Array.isArray(parsed)) {
          errs[field.fieldKey] = '必须是 JSON array'
        }
      } catch {
        errs[field.fieldKey] = 'JSON 语法错误'
      }
    }
  }
  return errs
}
