# 类型管理导出 Excel - 开发方案

## 概述

类型管理的节点类型页面有"批量导出"功能，当前导出为 JSON 文件（`.json`），不便于直接查看和编辑。本方案将导出格式改为 Excel（`.xlsx`），按类型分 Sheet 组织。本次仅实现节点类型导出，边类型暂不改造。

---

## 涉及文件

| 层 | 文件 | 改动类型 |
|---|---|---|
| 后端依赖 | `backend/requirements.txt` | 新增 `openpyxl` |
| 后端路由 | `backend/app/admin/node_type.py` | 重写 `export_node_types`，返回二进制 Excel |
| 前端 HTTP | `frontend/src/api/http.ts` | 响应拦截器增加 blob 透传 |
| 前端 API | `frontend/src/api/types.ts` | 导出函数改为返回 Blob |
| 前端组件 | `frontend/src/components/types/NodeTypeTable.vue` | 下载逻辑从 JSON 改为 Excel |
| 前端工具 | `frontend/src/utils/download.ts` | 新增 Blob 下载函数 + Excel 文件名 |

---

## 1. Excel 格式设计

### 核心原则

导出的核心挑战是**一对多关系**：一个类型下面有多个自定义字段。JSON 用嵌套数组表达，Excel 通过**多 Sheet 结构**解决——每个类型的字段独占一个 Sheet。

### Sheet 结构

```
Sheet 1: "类型汇总"        ← 所有节点类型的基本信息（一行一个）
Sheet 2: "<类型1编码>"     ← 类型1的自定义字段
Sheet 3: "<类型2编码>"     ← 类型2的自定义字段
Sheet 4: "<类型3编码>"     ← 类型3的自定义字段
...
```

### Sheet 1: 类型汇总

一行一个节点类型，列出所有基本属性：

| ID | 编码 | 名称 | 分类 | 图标 | 颜色 | 形状 | 渲染模式 | DN模板 | 描述 | 创建时间 | 更新时间 |

### Sheet 2+: 各类型字段

每个节点类型的自定义字段独占一个 Sheet，Sheet 名用类型的**编码（code）**。列：

| 字段标识 | 显示名称 | 字段类型 | 最大长度 | 默认值 | 选项 | 必填 | 排序 |

> Sheet 名用 code 而非 name，因为 code 是英文标识符且唯一。Excel Sheet 名限制 31 字符，code 超长时截断前 28 字符 + `"..."`。

### 示例：导出 Pod 和 VM 两个类型

**Sheet 1「类型汇总」:**

| ID | 编码 | 名称 | 分类 | ... |
|----|------|------|------|-----|
| nt_pod | pod | Pod | physical | ... |
| nt_vm | vm | 虚拟机 | virtual | ... |

**Sheet 2「pod」:**

| 字段标识 | 显示名称 | 字段类型 | 最大长度 | 默认值 | 必填 | 排序 |
|---------|---------|---------|---------|--------|------|------|
| namespace | 命名空间 | text | 100 | | 是 | 0 |
| hostname | 主机名 | text | 255 | | 是 | 1 |

**Sheet 3「vm」:**

| 字段标识 | 显示名称 | 字段类型 | 最大长度 | 默认值 | 必填 | 排序 |
|---------|---------|---------|---------|--------|------|------|
| vcpu | vCPU数量 | number | | 2 | 否 | 0 |
| memory | 内存大小 | number | | 4096 | 否 | 1 |

---

## 2. 后端

### 2.1 依赖

`requirements.txt` 新增 `openpyxl>=3.1.0`（当前环境已安装 v3.1.5）。

### 2.2 Excel 构建函数

```python
import re
from io import BytesIO
from openpyxl import Workbook
from fastapi.responses import StreamingResponse

# Excel Sheet 名不允许的字符
_SHEET_INVALID_CHARS = re.compile(r'[\\\*/\[\]\?:]')


def _safe_sheet_name(code: str) -> str:
    """将节点类型编码转为合法的 Excel Sheet 名（<=31 字符）"""
    name = _SHEET_INVALID_CHARS.sub('_', code)
    if len(name) > 31:
        name = name[:28] + "..."
    return name


def _build_node_types_excel(items: list[dict]) -> BytesIO:
    wb = Workbook()

    # Sheet 1: 类型汇总
    ws1 = wb.active
    ws1.title = "类型汇总"
    ws1.append(["ID", "编码", "名称", "分类", "图标", "颜色", "形状",
                 "渲染模式", "DN模板", "描述", "创建时间", "更新时间"])
    for item in items:
        ws1.append([
            item.get("id"), item.get("code"), item.get("name"),
            item.get("category"), item.get("icon"), item.get("color"),
            item.get("shape"), item.get("renderMode"), item.get("dnTemplate"),
            item.get("description"), item.get("createdAt"), item.get("updatedAt"),
        ])

    # Sheet 2+: 每个类型一个 Sheet，只放该类型的自定义字段
    for item in items:
        fields = item.get("fields") or []
        sheet_name = _safe_sheet_name(item.get("code", item.get("id", "unknown")))

        ws = wb.create_sheet(title=sheet_name)
        ws.append(["字段标识", "显示名称", "字段类型", "最大长度",
                    "默认值", "选项", "必填", "排序"])
        for f in fields:
            ws.append([
                f.get("fieldKey"), f.get("fieldLabel"),
                f.get("fieldType"), f.get("maxLength"), f.get("defaultValue"),
                f.get("options"), "是" if f.get("required") else "否",
                f.get("sortOrder"),
            ])

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output
```

### 2.3 修改导出端点

```python
@router.post("/node-types/export")
def export_node_types(data: TypeExportRequest):
    with connect() as conn:
        if data.ids:
            placeholders = ",".join("?" for _ in data.ids)
            rows = conn.execute(
                f"SELECT * FROM node_types WHERE id IN ({placeholders}) ORDER BY category, name",
                tuple(data.ids),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM node_types ORDER BY category, name"
            ).fetchall()

        items = []
        for r in rows:
            item = NodeTypeDetail(
                id=r["id"], code=r["code"], name=r["name"],
                category=r["category"], icon=r["icon"], color=r["color"],
                shape=r["shape"], render_mode=r["render_mode"],
                dn_template=r["dn_template"], description=r["description"],
                created_at=r["created_at"], updated_at=r["updated_at"],
                fields=_get_node_type_fields(conn, r["id"]),
            )
            items.append(item.model_dump(mode="json", by_alias=True))

    excel = _build_node_types_excel(items)
    return StreamingResponse(
        excel,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=node-types-export.xlsx"},
    )
```

> 查询逻辑完全不变，只改变最终的响应格式（JSON dict → StreamingResponse）。

### 2.4 边类型导出

暂不改造。`export_edge_types` 端点保持不变（继续返回 JSON）。后续如需改造，按照相同模式新增 `_build_edge_types_excel` 即可。

---

## 3. 前端

### 3.1 `http.ts` — 响应拦截器增加 blob 透传

导出请求的响应是二进制 Blob，不能被拦截器当成 JSON envelope 处理：

```typescript
http.interceptors.response.use(
  (resp: AxiosResponse<ApiEnvelope>) => {
    // 二进制响应（文件下载）直接透传，不处理 JSON envelope
    if (resp.config.responseType === 'blob' || resp.config.responseType === 'arraybuffer') {
      return resp
    }
    // ... 原有 JSON envelope 逻辑不变 ...
  },
  // error handler 不变
)
```

### 3.2 `download.ts` — 新增工具函数

```typescript
export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export function timestampExcelFilename(prefix: string): string {
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  const ts = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}T${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`
  return `${prefix}-${ts}.xlsx`
}
```

### 3.3 `types.ts` — 节点类型导出改为返回 Blob

```typescript
export const nodeTypeApi = {
  export: (ids?: string[]): Promise<Blob> =>
    http.post('/node-types/export', { ids }, { responseType: 'blob' }).then(r => r.data),
}
```

`edgeTypeApi.export` 保持不变（继续返回 JSON）。

> 不能使用 `apiPost` 封装，因为 `apiPost` 会解包 `resp.data.data`（JSON envelope），对 Blob 不适用。

### 3.4 `NodeTypeTable.vue` — handler 改造

```typescript
async function handleExport() {
  try {
    const ids = selectedRowKeys.value.length > 0 ? selectedRowKeys.value : undefined
    const blob = await nodeTypeApi.export(ids)
    downloadBlob(blob, timestampExcelFilename('node-types-export'))
    message.success('导出成功')
  } catch {}
}
```

导入调整：
```typescript
import { downloadBlob, timestampExcelFilename } from '@/utils/download'
```

### 3.5 `EdgeTypeTable.vue` — 不改动

边类型导出按钮和逻辑保持现状（继续导出 JSON）。

---

## 4. 实现顺序

| 步骤 | 内容 |
|------|------|
| 1 | `requirements.txt` 新增 `openpyxl>=3.1.0` |
| 2 | 后端：新增 `_safe_sheet_name` + `_build_node_types_excel` |
| 3 | 后端：重写 `export_node_types` 返回 StreamingResponse |
| 4 | 前端 `http.ts`：拦截器增加 blob 透传 |
| 5 | 前端 `download.ts`：新增 `downloadBlob` + `timestampExcelFilename` |
| 6 | 前端 `types.ts`：`nodeTypeApi.export` 改为 `responseType: 'blob'` |
| 7 | 前端 `NodeTypeTable.vue`：修改 handler |
| 8 | 联调测试 |

---

## 5. 测试要点

- [x] 后端：POST `/node-types/export` 全部类型 → 返回 `.xlsx` 文件（14 Sheet, 15KB）
- [x] 后端：POST `/node-types/export` 指定 ids → 仅返回选中类型（3 Sheet, 6.5KB）
- [x] 后端：导出的 xlsx 文件可被 openpyxl 正常打开
- [x] 后端：Sheet 1 名为「类型汇总」、后续 Sheet 名为各类型的 code
- [x] 后端：每个类型的字段 Sheet 中不含其他类型的字段
- [x] 后端：边类型 `/edge-types/export` 不受影响，仍返回 JSON（5 items）
- [x] 前端：点击"批量导出" → 浏览器下载 `.xlsx` 文件（文件名含时间戳）
- [x] 前端：选中部分类型后导出 → 仅导出选中的（curl 验证）
- [x] 前端：不勾选直接导出 → 导出全部
- [x] 前端：边类型导出按钮不受影响，仍下载 JSON
- [x] 前端 TypeScript 编译零错误
