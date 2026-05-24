# 类型管理导入 Excel - 开发方案

## 概述

节点类型已支持导出为 Excel（.xlsx），但缺少对应的导入功能。本方案新增 Excel 导入端点，读取与导出相同格式的 xlsx 文件，支持新建类型和覆盖更新已有类型。

本次仅实现节点类型导入，边类型暂不改造。

---

## 涉及文件

| 层 | 文件 | 改动类型 |
|---|---|---|
| 后端 Schema | `backend/app/admin/schemas/node_type.py` | 新增 `TypeImportResult` |
| 后端路由 | `backend/app/admin/node_type.py` | 新增 `POST /node-types/import` + `/import/preview` |
| 前端 API | `frontend/src/api/types.ts` | 新增 `nodeTypeApi.import` + `importPreview` |
| 前端组件 | `frontend/src/components/types/NodeTypeTable.vue` | 新增导入按钮 + 文件处理 + 覆盖确认弹窗 |

---

## 1. 导入策略

### 1.1 冲突处理

以**编码（code）**为唯一标识匹配现有类型：

| 场景 | 处理 |
|------|------|
| code 不存在 | **新建**类型 + 字段 |
| code 已存在 | **覆盖更新**类型元数据 + **替换**所有字段（先删后插） |

> 选择覆盖而非跳过：导入的典型场景是 导出→修改→导回，用户期望最终结果与 Excel 内容一致。

### 1.2 覆盖确认

导入时如果存在已有类型将被覆盖，前端通过 **预览 → 确认 → 导入** 三步流程处理：

1. 用户选择文件 → 调用 `POST /node-types/import/preview` 解析 Excel
2. 后端返回三类数据：`toCreate`（新建）、`toUpdate`（覆盖）、`errors`（跳过）
3. 若 `toUpdate` 非空 → 弹出确认对话框，列出将覆盖的类型（旧名 → 新名）
4. 用户点"确认导入" → 调用 `POST /node-types/import` 实际执行
5. 若全部新建（`toUpdate` 为空）→ 跳过确认，直接导入

### 1.3 事务

整个导入在一个事务中完成。解析阶段发现的格式错误（如缺少 Sheet）在事务外报错；行级字段缺失在事务内跳过并记录。

---

## 2. Excel 格式（与导出一致）

```
Sheet 1: "类型汇总"
| ID | 编码 | 名称 | 分类 | 图标 | 颜色 | 形状 | 渲染模式 | DN模板 | 描述 | 创建时间 | 更新时间 |

Sheet 2+: 以类型 code 命名
| 字段标识 | 显示名称 | 字段类型 | 最大长度 | 默认值 | 选项 | 必填 | 排序 |
```

### 2.1 列映射

**类型汇总 Sheet：**

| Excel 列 | 列索引 | 对应字段 | 必填 | 备注 |
|----------|--------|---------|------|------|
| ID | 0 | — | | **不导入**（重新分配） |
| 编码 | 1 | code | ✅ | 唯一标识 |
| 名称 | 2 | name | ✅ | |
| 分类 | 3 | category | ✅ | |
| 图标 | 4 | icon | | |
| 颜色 | 5 | color | | |
| 形状 | 6 | shape | | |
| 渲染模式 | 7 | render_mode | | 默认 "none" |
| DN模板 | 8 | dn_template | | |
| 描述 | 9 | description | | |
| 创建时间 | 10 | — | | **不导入** |
| 更新时间 | 11 | — | | **不导入** |

**字段 Sheet：**

| Excel 列 | 列索引 | 对应字段 | 必填 | 备注 |
|----------|--------|---------|------|------|
| 字段标识 | 0 | field_key | ✅ | |
| 显示名称 | 1 | field_label | ✅ | |
| 字段类型 | 2 | field_type | ✅ | text/number/select/boolean |
| 最大长度 | 3 | max_length | | text 类型必填 |
| 默认值 | 4 | default_value | | |
| 选项 | 5 | options | | select 类型建议填 |
| 必填 | 6 | required | | "是"→1，其他→0 |
| 排序 | 7 | sort_order | | 默认 0 |

---

## 3. 后端

### 3.1 新增 Schema

```python
class TypeImportResult(CamelModel):
    created: int = 0
    updated: int = 0
    total_fields: int = 0
    errors: list[str] = []
```

### 3.2 新增端点

```
POST /admin/api/node-types/import
Content-Type: multipart/form-data
Body: file (.xlsx)
```

**处理流程：**

```
1. 接收上传的 .xlsx → 校验文件名后缀
2. openpyxl.load_workbook() 加载
3. 校验 Sheet "类型汇总" 存在
4. 遍历"类型汇总"行（跳过表头），按列索引读取
5. 逐行：
   a. 校验 code/name/category 非空
   b. code 查数据库 → 存在则 UPDATE，不存在则 INSERT
   c. 按 code 找对应字段 Sheet → 删除旧字段 → INSERT 新字段
6. 返回 TypeImportResult
```

### 3.3 伪代码

```python
from fastapi import UploadFile

@router.post("/node-types/import")
async def import_node_types(file: UploadFile):
    if not file.filename.endswith('.xlsx'):
        raise HTTPException(400, detail={"code": 40210, "message": "仅支持 .xlsx 文件"})

    contents = await file.read()
    wb = load_workbook(filename=BytesIO(contents))

    if "类型汇总" not in wb.sheetnames:
        raise HTTPException(400, detail={"code": 40211, "message": "缺少「类型汇总」Sheet"})

    ws = wb["类型汇总"]
    result = TypeImportResult()

    with transaction() as conn:
        for row in ws.iter_rows(min_row=2, values_only=True):
            code = row[1]
            name = row[2]
            category = row[3]

            if not code or not name or not category:
                result.errors.append(f"编码={code} 缺少必填字段，跳过")
                continue

            existing = conn.execute(
                "SELECT id FROM node_types WHERE code = ?", (code,)
            ).fetchone()

            if existing:
                type_id = existing["id"]
                conn.execute(
                    """UPDATE node_types SET name=?, category=?, icon=?, color=?,
                       shape=?, render_mode=?, dn_template=?, description=?
                       WHERE id=?""",
                    (name, category, row[4], row[5], row[6],
                     row[7] or "none", row[8], row[9], type_id),
                )
                result.updated += 1
            else:
                type_id = _new_id()
                conn.execute(
                    """INSERT INTO node_types (id, code, name, category, icon, color,
                       shape, render_mode, dn_template, description)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (type_id, code, name, category, row[4], row[5],
                     row[6], row[7] or "none", row[8], row[9]),
                )
                result.created += 1

            # 导入字段
            sheet_name = _safe_sheet_name(code)
            if sheet_name in wb.sheetnames:
                conn.execute("DELETE FROM node_type_fields WHERE node_type_id = ?", (type_id,))
                for frow in wb[sheet_name].iter_rows(min_row=2, values_only=True):
                    fkey, flabel, ftype = frow[0], frow[1], frow[2]
                    if not fkey or not flabel or not ftype:
                        continue
                    conn.execute(
                        """INSERT INTO node_type_fields
                           (node_type_id, field_key, field_label, field_type,
                            max_length, default_value, options, required, sort_order)
                           VALUES (?,?,?,?,?,?,?,?,?)""",
                        (type_id, fkey, flabel, ftype,
                         frow[3], frow[4], frow[5],
                         1 if str(frow[6]).strip() == "是" else 0,
                         frow[7] or 0),
                    )
                    result.total_fields += 1

    return {"code": 0, "data": result.model_dump(mode="json", by_alias=True), "message": "ok"}
```

---

## 4. 前端

### 4.1 `types.ts` — 新增导入函数

```typescript
export interface TypeImportResult {
  created: number
  updated: number
  totalFields: number
  errors: string[]
}

export const nodeTypeApi = {
  import: (file: File): Promise<TypeImportResult> => {
    const form = new FormData()
    form.append('file', file)
    return http.post('/node-types/import', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(r => r.data.data)
  },
}
```

### 4.2 `NodeTypeTable.vue` — UI

```html
<!-- 隐藏文件输入 -->
<input ref="fileInputRef" type="file" accept=".xlsx"
       style="display: none" @change="handleFileChosen" />

<!-- 工具栏：紧跟导出按钮 -->
<a-button @click="handleImportClick">
  <template #icon><ImportOutlined /></template>
  导入
</a-button>
```

```typescript
const fileInputRef = ref<HTMLInputElement>()

function handleImportClick() { fileInputRef.value?.click() }

async function handleFileChosen(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  ;(e.target as HTMLInputElement).value = ''
  if (!file) return
  try {
    const result = await nodeTypeApi.import(file)
    const parts: string[] = []
    if (result.created) parts.push(`新建 ${result.created} 个`)
    if (result.updated) parts.push(`更新 ${result.updated} 个`)
    parts.push(`导入 ${result.totalFields} 个字段`)
    message.success(parts.join('，'))
    if (result.errors.length) message.warning(result.errors.join('；'))
    refresh()
  } catch {}
}
```

---

## 5. 实现顺序

| 步骤 | 内容 |
|------|------|
| 1 | 后端 Schema：`TypeImportResult` + `TypeImportPreview` + `TypeImportPreviewItem` |
| 2 | 后端路由：`_load_import_workbook` + `POST /node-types/import/preview` + `POST /node-types/import` |
| 3 | 前端 API：`nodeTypeApi.importPreview` + `nodeTypeApi.import` + 相关接口 |
| 4 | 前端 UI：`NodeTypeTable.vue` 导入按钮 + 预览 + 覆盖确认弹窗 |
| 5 | 联调测试 |

---

## 6. 测试要点

### 6.1 成功场景

| 场景 | 操作 | 预期页面提示 | 结果 |
|------|------|-------------|------|
| 全部新建 | 导入含 3 个新 code 的 xlsx | `message.success`: "新建 3 个，导入 12 个字段" | ✅ |
| 全部覆盖 | 导入含 2 个已存在 code 的 xlsx | `message.success`: "更新 2 个，导入 8 个字段" | ✅ |
| 混合 | 导入含 1 个新 code + 1 个已存在 code | `message.success`: "新建 1 个，更新 1 个，导入 10 个字段" | ✅ |
| 无字段的 Sheet | 某个类型的字段 Sheet 存在但无数据行 | `message.success`: 正常导入，字段数不含该类型 | ✅ |

### 6.2 部分失败场景（事务内跳过）

| 场景 | 操作 | 预期页面提示 | 结果 |
|------|------|-------------|------|
| 某行缺必填列 | Excel 中某类型缺名称 | `message.success`: 成功部分 + `message.warning`: "编码=xxx 缺少必填字段，跳过" | ✅ |
| 字段 Sheet 缺失 | 类型 code 在 Excel 中无对应 Sheet | `message.success`: 类型创建/更新成功 | ✅ |

### 6.3 前置校验失败场景（事务外，文件级）

| 场景 | 操作 | 预期页面提示 | 结果 |
|------|------|-------------|------|
| 非 xlsx 文件 | 选一个 .json 或 .txt 文件 | `message.error`: "[40210] 仅支持 .xlsx 文件" | ✅ |
| 缺少类型汇总 Sheet | xlsx 中无"类型汇总" Sheet | `message.error`: "[40212] 缺少「类型汇总」Sheet" | ✅ |
| xlsx 损坏 | 选一个打不开的文件 | `message.error`: "[40211] 文件无法解析" | ✅ |

### 6.4 覆盖确认

| 场景 | 操作 | 预期页面提示 | 结果 |
|------|------|-------------|------|
| 有覆盖类型 | 导入含已存在 code 的 xlsx | 弹出确认框，列出新建/覆盖/跳过三类 | ✅ |
| 名称未变 | 旧名与新名相同（如端口→端口） | 仅显示 code + 名称，不显示无意义的"→" | ✅ |
| 名称变更 | 旧名与新名不同（如 Pod→PodUpdated） | 显示 "code（旧名 → 新名）" | ✅ |
| 确认覆盖 | 点"确认导入" | 执行导入，提示更新 N 个 | ✅ |
| 取消覆盖 | 点"取消" | 不执行导入，无任何变更 | ✅ |
| 全部新建 | 导入全部为新的 xlsx | 不弹确认框，直接导入 | ✅ |

### 6.5 边界情况

| 场景 | 操作 | 预期页面提示 | 结果 |
|------|------|-------------|------|
| 未选文件 | 弹出文件选择器后点取消 | 无任何提示 | ✅ |
| 导入后列表刷新 | 任意成功导入 | 页面表格自动刷新 | ✅ |
| 重复导入同一文件 | 连续两次导入同一个 xlsx | 第二次弹确认框 → 确认后提示"更新 N 个" | ✅ |
| 字段 Sheet 名超 31 字符 | 类型 code 超长（截断匹配） | 按 `_safe_sheet_name` 规则匹配 | ✅ |

### 6.6 编译与格式

- [x] 前端 TypeScript 编译零错误
- [x] 后端 Python 无语法错误，`openpyxl` 正常加载
