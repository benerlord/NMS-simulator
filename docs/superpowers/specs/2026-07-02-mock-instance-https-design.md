# 实例管理支持 HTTPS 协议 - 设计方案

- 日期：2026-07-02
- 作者：benerlord
- 主题：让 `mock_instances` 每个实例独立选择 HTTP / HTTPS 启动，用一套全局共享的自签证书兜底，前端提供可复制的完整访问 URL

---

## 1. 背景与目标

### 现状

- `mock_instances` 表字段：`id / name / topology_id / port / description / enabled / status / created_at / updated_at`，UNIQUE(port)，**没有任何 SSL 相关字段**
- `backend/app/mock/instance_app.py:53` 硬编码 `uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="warning")`，**不传 ssl 参数**
- `InstanceRunner.start_instance()` 通过 `python -m app.mock.instance_app --topology-id ... --port ... --instance-id ...` 起子进程，命令行没有 ssl 参数
- 主服务已有 `settings.ssl_enabled` + `cert_utils.ensure_cert()`：自签证书 CN=127.0.0.1，SAN=`localhost`/`127.0.0.1`，有效期 10 年，通过 `cryptography` 生成，`openssl` CLI 兜底

### 目标

让每个 Mock 实例支持独立选择 HTTP 或 HTTPS 启动，客户端（采集插件 / curl / 浏览器）能直接通过 `https://localhost:port` 访问。

### 非目标

- 不做证书信任导入 / 系统信任库集成（跨平台复杂，本地模拟工具用不上）
- 不做用户上传自定义证书（YAGNI，全局自签足够）
- 不改主服务 `APP_SSL_ENABLED` 现有行为（两个系统解耦）
- 不引入 pytest 自动化测试（项目现状无测试框架，本次保持一致）

---

## 2. 决策要点

| 决策 | 选项 | 结论 | 理由 |
|---|---|---|---|
| 协议粒度 | A 每实例独立 / B 全局开关 / C 混合 | **A** | 契合"多网管模拟"产品定位，不同实例可模拟不同协议网管 |
| 证书来源 | A 全局共享自签 / B 每实例独立自签 / C 支持上传+自签兜底 | **A** | 客户端本就跳过校验，一套证书最简单；主服务的证书路径直接复用 |
| 证书信任 & URL 展示 | A 只跳过校验 / B 提供 CA 下载 / C 跳过校验 + 展示 URL 列 | **C** | 不做系统信任库集成（跨平台复杂），但展示可复制 URL 大幅提升可用性 |
| 数据库字段类型 | `protocol` 字符串 / `ssl_enabled` 布尔 | **布尔** | 只有两个值最紧凑；与后端 `settings.ssl_enabled` 命名一致 |
| 证书 bootstrap 位置 | 父进程 / 子进程 | **父进程** | 多实例并发启用 HTTPS 无竞态；生成失败时更早发现 |
| URL 拼接位置 | 后端 / 前端 | **后端** | 未来若加"访问 host"配置项无需改前端 |

---

## 3. 架构

### 3.1 组件关系

```
┌─────────────────┐        ┌────────────────────┐        ┌─────────────────────────┐
│ MockInstances   │  HTTP  │ /admin/api/mock-   │  同进程 │ InstanceRunner (父)      │
│ View / Modal    │◄──────►│ instances CRUD     │◄──────►│  ├─ ensure_cert()        │
│ (Vue3)          │        │ (mock_instance.py) │        │  └─ subprocess.Popen(...) │
└─────────────────┘        └────────────────────┘        └────────┬────────────────┘
        │                                                         │
        │ 显示 record.url                                          │ --ssl-certfile/keyfile
        ▼                                                         ▼
   "https://localhost:8081"                              ┌─────────────────────────┐
                                                        │ instance_app.py (子)     │
                                                        │  uvicorn.run(app, ssl…)  │
                                                        └─────────────────────────┘
```

### 3.2 兼容性 & 迁移

- 幂等 `ALTER TABLE mock_instances ADD COLUMN ssl_enabled INTEGER NOT NULL DEFAULT 0`
- 既有实例迁移后 `ssl_enabled=0`，回退成 HTTP，行为零变化
- 端口 UNIQUE 约束不变（一个实例只绑一个端口，无论协议）
- 主服务 `.env` 的 `APP_SSL_ENABLED` 与实例的 `ssl_enabled` 相互独立

---

## 4. 数据模型改动

### 4.1 SQL 迁移

`backend/app/db/migrations.py` 幂等 `ALTER TABLE` 块里追加：

```python
try:
    conn.execute("ALTER TABLE mock_instances ADD COLUMN ssl_enabled INTEGER NOT NULL DEFAULT 0")
except sqlite3.OperationalError:
    pass
```

### 4.2 Pydantic Schema

`backend/app/admin/schemas/mock_instance.py`：

```python
class MockInstanceCreate(CamelModel):
    ...
    ssl_enabled: bool = False           # 新增，默认 False

class MockInstanceUpdate(CamelModel):
    ...
    ssl_enabled: Optional[bool] = None  # 新增

class MockInstanceItem(CamelModel):
    ...
    ssl_enabled: bool                   # 新增
    url: str                            # 新增，后端拼好返回
```

### 4.3 前端 TS 类型

`frontend/src/api/mockInstance.ts`：

```typescript
export interface MockInstanceItem {
  ...
  sslEnabled: boolean          // 新增
  url: string                  // 新增
}

export interface MockInstanceCreate {
  ...
  sslEnabled?: boolean         // 新增
}

export interface MockInstanceUpdate {
  ...
  sslEnabled?: boolean         // 新增
}
```

驼峰转换走现有 `camelize/snakeize` 拦截器，无手工映射。

---

## 5. 后端流程

### 5.1 证书 bootstrap（父进程）

`backend/app/core/instance_runner.py` 的 `start_instance` 前置证书生成：

```python
from app.core.cert_utils import ensure_cert
from app.core.config import settings

def start_instance(self, inst_id: str, port: int, topology_id: str, ssl_enabled: bool):
    with self._lock:
        if inst_id in self._processes:
            return
        _update_status(inst_id, "starting")
        ssl_args: list[str] = []
        if ssl_enabled:
            try:
                cert, key = ensure_cert(settings.ssl_certfile, settings.ssl_keyfile)
                ssl_args = ["--ssl-certfile", cert, "--ssl-keyfile", key]
            except Exception:
                _update_status(inst_id, "error")
                return
        try:
            kwargs = {}
            if sys.platform == 'win32':
                kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
            proc = subprocess.Popen(
                [sys.executable, "-m", "app.mock.instance_app",
                 "--topology-id", topology_id,
                 "--port", str(port),
                 "--instance-id", inst_id,
                 *ssl_args],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **kwargs,
            )
            self._processes[inst_id] = proc
            _update_status(inst_id, "running")
        except Exception:
            _update_status(inst_id, "error")
```

同步调整 `restart_instance` 签名：

```python
def restart_instance(self, inst_id: str, port: int, topology_id: str, ssl_enabled: bool):
    self.stop_instance(inst_id)
    self.start_instance(inst_id, port, topology_id, ssl_enabled)
```

`sync_all` 与 `_check_and_restart` 的 DB 查询都要 SELECT 出 `ssl_enabled` 并回传给 `start_instance`：

```python
# sync_all
rows = conn.execute(
    "SELECT id, port, topology_id, ssl_enabled FROM mock_instances WHERE enabled = 1"
).fetchall()
for r in rows:
    self.start_instance(r["id"], r["port"], r["topology_id"], bool(r["ssl_enabled"]))

# _check_and_restart
row = conn.execute(
    "SELECT port, topology_id, ssl_enabled FROM mock_instances WHERE id = ? AND enabled = 1",
    (inst_id,),
).fetchone()
if row:
    self.start_instance(inst_id, row["port"], row["topology_id"], bool(row["ssl_enabled"]))
```

### 5.2 子进程入口改动

`backend/app/mock/instance_app.py`：

```python
parser.add_argument("--topology-id", required=True)
parser.add_argument("--port", type=int, required=True)
parser.add_argument("--instance-id", default=None)
parser.add_argument("--ssl-certfile", default=None)
parser.add_argument("--ssl-keyfile", default=None)
args = parser.parse_args()

init_db()
app = create_app(args.topology_id, instance_id=args.instance_id)

kwargs = {"host": "0.0.0.0", "port": args.port, "log_level": "warning"}
if args.ssl_certfile and args.ssl_keyfile:
    kwargs["ssl_certfile"] = args.ssl_certfile
    kwargs["ssl_keyfile"] = args.ssl_keyfile
uvicorn.run(app, **kwargs)
```

子进程只关心"给不给证书文件路径"，不参与配置计算。

### 5.3 URL 拼接（后端）

`backend/app/admin/mock_instance.py` 的 `list_mock_instances` 在拼 `MockInstanceItem` 时补上：

```python
proto = "https" if r["ssl_enabled"] else "http"
url = f"{proto}://localhost:{r['port']}"
...
MockInstanceItem(
    ...,
    ssl_enabled=bool(r["ssl_enabled"]),
    url=url,
)
```

Host 硬编码 `localhost`：
- 自签证书 SAN 包含 `localhost` 和 `127.0.0.1`，浏览器/curl 通用
- 未来若需要局域网访问，可加系统设置项（YAGNI 暂不做）

### 5.4 CRUD 联动

| 端点 | 改动 |
|---|---|
| `POST /mock-instances` | 接受 `sslEnabled`，写入 DB；`enabled=true` 时调 `start_instance(..., ssl_enabled)` |
| `PUT /mock-instances/{id}` | 接受 `sslEnabled`；DB 更新后重读 `port, topology_id, enabled, ssl_enabled`：`enabled=true` → `restart_instance(..., ssl_enabled)`，`enabled=false` → `stop_instance` |
| `PATCH /mock-instances/{id}/enabled` | 从 DB 读 `ssl_enabled` 传给 runner |
| `GET /mock-instances` | SELECT `ssl_enabled` 并拼 `url` 返回 |

### 5.5 协议热切换

用户在 UI 把已启用实例从 HTTP 改为 HTTPS（或反向）：

- `PUT` 落库后，`restart_instance` 会先 `stop_instance`（`proc.kill()` + `wait(3)`）再 `start_instance`
- 新 `start_instance` 走新分支带上 SSL 参数
- 老进程 kill → 端口释放 → 新进程用新协议 bind，一次 restart 完事
- 同一 `inst_id` 由 `self._lock` 串行化，天然规避竞态

---

## 6. 前端 UX

### 6.1 MockInstanceModal —— 新增"协议"字段

在"端口"下方加一个 `Radio.Group`：

```
协议  ○ HTTP  ● HTTPS
      提示：HTTPS 使用系统自签证书，客户端需跳过证书校验
```

- `Radio.Group` 单选（比 Switch 更清晰表达"两个协议二选一"）
- 新建时默认 `HTTP`
- 编辑时回显 `props.editing.sslEnabled` → HTTP/HTTPS
- HTTPS 选中时下方显示浅灰提示（`<div class="ant-form-item-extra">`）
- `formState` 加 `sslEnabled: false`，`handleSubmit` 提交时带上
- `handleCreate` / `handleUpdate` payload 类型接口一并加 `sslEnabled?: boolean`

### 6.2 MockInstancesView 列表 —— 新增"访问地址"列

当前列：名称 / 端口 / 所属拓扑 / 启用 / 接口数 / 创建时间 / 操作

调整后：

| 名称 | 端口 | **协议** | **访问地址** | 所属拓扑 | 启用 | 接口数 | 创建时间 | 操作 |

- **协议列**（宽 80）：`<Tag color="blue">HTTP</Tag>` / `<Tag color="green">HTTPS</Tag>`
- **访问地址列**（宽 240）：
  ```vue
  <Typography.Text copyable code>{{ record.url }}</Typography.Text>
  ```
  antd `Typography.Text copyable` 自带复制图标 + 复制成功提示
- 若 `enabled=false`，URL 用 `type="secondary"` 显示为灰色，附 tooltip"实例未启用，当前不可访问"

### 6.3 涉及文件

| 文件 | 改动 |
|---|---|
| `frontend/src/components/mockInstance/MockInstanceModal.vue` | +Radio.Group 协议字段 + formState.sslEnabled + payload 类型 |
| `frontend/src/views/MockInstancesView.vue` | +协议列 / +访问地址列 + handleCreate/handleUpdate 传 sslEnabled |
| `frontend/src/api/mockInstance.ts` | `MockInstanceItem` 加 `sslEnabled` / `url`；Create/Update 加 `sslEnabled?` |

### 6.4 不做

- 不做首次启用 HTTPS 的引导弹窗（证书由父进程自动生成，用户无感）
- 不做 CA 证书下载入口（避免跨平台系统信任库集成的复杂度）

---

## 7. 错误处理

| 场景 | 处理策略 |
|---|---|
| 启用 HTTPS 但 `ensure_cert` 失败（openssl 缺失且未装 cryptography） | 父进程捕获异常 → `_update_status(inst_id, "error")` → 不启动子进程；前端刷新看到 status=error |
| 子进程绑定端口冲突（切换时旧进程未完全释放） | `stop_instance` 已 `proc.kill()` + `proc.wait(timeout=3)`；仍冲突则走 `_check_and_restart` 限流路径（1 分钟 3 次上限） |
| 证书生成成功但 uvicorn 起不来（如证书损坏） | 子进程立即崩溃 → 健康检查发现 → 限流重启 → 最终标 error |
| 切协议时旧进程未及时退出 | `restart_instance` 内部串行 `stop → wait(3s) → start`；同 inst_id 由 `self._lock` 串行化 |
| 前端 URL 列在 `enabled=false` 时展示 | URL 仍显示（灰色 secondary）+ tooltip "实例未启用，当前不可访问" |
| SQLite 迁移多次执行 | `ALTER TABLE ... ADD COLUMN` 已在 try/except OperationalError 里，幂等 |

**不处理**：客户端证书信任问题（用户跳过校验即可），跨主机访问的证书 SAN 问题（超出本地模拟工具范围）。

---

## 8. 测试计划

按顺序手工验收，全绿即通过：

1. **迁移幂等**：拉起后端两次，`mock_instances` 表存在 `ssl_enabled` 列且不重复报错
2. **默认 HTTP 兼容**：既有实例列表刷新，`sslEnabled=false`、`url` 是 `http://localhost:xxx`，行为零变化
3. **新建 HTTPS 实例**：Modal 选 HTTPS → 提交 → 列表刷新看到协议列 Tag=HTTPS + URL 前缀 https；`curl -k https://localhost:port/<any-mock-path>` 能拿到响应
4. **证书首次生成**：删除 `backend/data/ssl/`，新建 HTTPS 实例 → 目录被自动重建，`cert.pem` + `key.pem` 生成
5. **HTTP → HTTPS 热切换**：编辑已运行的 HTTP 实例改成 HTTPS → 保存 → 子进程重启 → 老端口不再响应 HTTP，改由 HTTPS 服务
6. **HTTPS → HTTP 反向切换**：同上反向
7. **禁用 HTTPS 实例**：关闭 enabled → 子进程 kill → `curl -k https://localhost:port` 应连接被拒
8. **端口占用冲突**：并发创建两个同端口 HTTPS 实例，DB UNIQUE 约束正确阻止（既有校验回归）
9. **前端 URL 复制**：点击 URL 旁边的复制图标 → 粘贴板得到 `https://localhost:port`
10. **健康监控**：手动 kill HTTPS 子进程 → 15 秒内被 `_check_and_restart` 拉起，重启后仍是 HTTPS

**不做的自动化测试**：项目当前无 pytest 框架，本次不引入，保持一致。

---

## 9. 影响文件清单

### 后端

| 文件 | 改动类型 |
|---|---|
| `backend/app/db/migrations.py` | +1 段幂等 ALTER TABLE |
| `backend/app/admin/schemas/mock_instance.py` | Schema 加 `ssl_enabled` / `url` 字段 |
| `backend/app/admin/mock_instance.py` | CRUD 端点接受/回写 `ssl_enabled`；list 拼 `url` |
| `backend/app/core/instance_runner.py` | `start_instance` / `restart_instance` / `sync_all` / `_check_and_restart` 加 `ssl_enabled` 参数；父进程 `ensure_cert` |
| `backend/app/mock/instance_app.py` | argparse +2 参数；uvicorn 按需传 ssl kwargs |

### 前端

| 文件 | 改动类型 |
|---|---|
| `frontend/src/api/mockInstance.ts` | `MockInstanceItem` / Create / Update 类型加字段 |
| `frontend/src/components/mockInstance/MockInstanceModal.vue` | +Radio.Group 协议字段 + formState + payload |
| `frontend/src/views/MockInstancesView.vue` | +协议列 / +访问地址列 + handle\* 传 `sslEnabled` |

---

## 10. 未来工作（超出本次范围）

- 访问 host 可配置（局域网/多网卡场景）
- 支持用户上传自定义证书（如需匹配特定域名）
- 每实例独立证书（如需在 SAN 里带上实例名做区分）
- 自动化 pytest 测试框架搭建
