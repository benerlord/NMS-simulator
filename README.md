# 网管系统模拟工具

一个面向网管类系统（拓扑 + REST API）的本地模拟工具：在画布上拖拽出任意规模的设备拓扑，把每个节点的属性当作"数据源"，再以可配置的 HTTP 接口暴露出去——让上游采集插件、Postman 调试、CI 回归脱离真实网管即可完成全部联调与异常注入。

---

## 1. 功能速览

| 模块 | 路径 | 说明 |
|---|---|---|
| 拓扑管理 | `/topologies` | 列表 / 增删改查 / JSON 导入导出 / 一键进画布 |
| 拓扑画布 | `/topologies/:id/canvas` | AntV X6 + 拖拽 + 自动保存 + WebSocket 多端同步 |
| 类型管理 | `/types` | 节点类型 / 边类型 / 字段定义（默认内置 11 节点 + 5 边类型） |
| 接口配置 | `/apis` | 把拓扑数据封装成 HTTP 接口；支持 SQL / 静态体两种数据源、响应模板、异常注入（延迟 + 概率错误）、Token 鉴权 |
| Token 管理 | `/tokens` | 颁发 / 撤销 / 清理过期；xtoken / Basic 两种认证模式 |
| 系统设置 | `/settings` | 自动保存间隔、模拟接口路径前缀（热生效）、运行时只读信息 |

**Mock 调用方**：直接 `GET <mock_path_prefix><接口路径>`，前缀默认空，配的什么路径就直接命中什么路径。

---

## 2. 30 分钟启动指南

### 前置依赖

| 工具 | 推荐版本 | 验证 |
|---|---|---|
| Python | 3.9+ | `python --version` |
| Node.js | 20+ | `node --version` |
| pnpm | 8+ | `pnpm --version`（没有就 `npm i -g pnpm`） |

> Windows 直接用系统 Python / Node 即可；macOS / Linux 推荐 `pyenv` + `nvm`。

### 步骤一：克隆 + 安装

```bash
# 拉代码（任选一项）
git clone <repo-url> InterfaceTest
cd InterfaceTest

# 后端依赖（建议用 venv）
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
pip install -r backend/requirements.txt

# 前端依赖
cd frontend
pnpm install
cd ..
```

### 步骤二：启动后端

```bash
# Windows
start.bat

# macOS / Linux
./start.sh
```

启动成功输出：
```
INFO:     Uvicorn running on http://0.0.0.0:8080
INFO:     mock.registry: prefix = ''
INFO:     mock.registry: loaded N routes
```

健康检查：`curl http://127.0.0.1:8080/admin/api/health` → `{"code":0,"data":{"status":"ok"},"message":"ok"}`

首次启动会自动：
- 在 `backend/data/app.db` 建库（SQLite + WAL）
- 跑迁移建 12 张表
- 灌种子（11 节点类型 + 5 边类型 + 3 项默认设置）

### 步骤三：启动前端

新开一个终端：

```bash
cd frontend
pnpm dev
```

打开 <http://localhost:5173> → 自动跳转到 `/topologies`。

### 步骤四：上手（5 分钟）

1. **建拓扑**：点击右上"新建" → 命名 → 进入画布
2. **拖节点**：从左侧"类型面板"拖任意节点到画布；填名称 + 属性
3. **连边**：点工具栏"连线"按钮 → 选源节点 → 选边类型 → 选目标节点
4. **配接口**：到 `/apis` → 新建 → 选刚才的拓扑 → SQL 数据源 → 写形如 `SELECT name, dn FROM nodes WHERE topology_id = :topology_id`
5. **调用 mock**：`curl http://127.0.0.1:8080/<刚才配的 path>` → 看到拓扑数据返回

---

## 3. 端口 / 环境变量

后端读 `backend/.env`（参考 `backend/.env.example`）：

| 变量 | 默认 | 说明 |
|---|---|---|
| `APP_HOST` | `0.0.0.0` | 绑定地址 |
| `APP_PORT` | `8080` | 监听端口 |
| `DB_PATH` | `./data/app.db` | SQLite 文件路径，相对 `backend/` |
| `LOG_LEVEL` | `INFO` | uvicorn 日志级别 |
| `AUTOSAVE_INTERVAL` | `60` | 画布自动保存间隔（秒，可 UI 改） |

前端开发时通过 `VITE_BACKEND` 改后端地址（默认 `http://localhost:8080`）：

```bash
VITE_BACKEND=http://192.168.1.10:8080 pnpm dev
```

Vite 已配 `/admin/api`、`/admin/ws` 两条 proxy 规则，所以前端业务代码统一走 `/admin/api/...` 相对路径。

---

## 4. 仓库结构

```
InterfaceTest/
├── backend/                     # FastAPI + SQLite
│   ├── app/
│   │   ├── main.py              # 入口 + lifespan + 路由挂载
│   │   ├── core/                # 配置 / 请求管道 / WS hub / 响应模板
│   │   ├── db/                  # 连接 / 迁移 / 种子
│   │   ├── admin/               # /admin/api/** 管理接口
│   │   │   ├── topology.py      # 拓扑 CRUD + import/export (M4-02)
│   │   │   ├── node.py / edge.py / node_type.py / edge.py
│   │   │   ├── api_config.py    # mock 接口配置
│   │   │   ├── token.py         # Token CRUD
│   │   │   ├── settings.py      # 系统设置（含 mock_path_prefix 热重载）
│   │   │   └── schemas/         # Pydantic v2 模型（CamelModel）
│   │   └── mock/                # /<mock_path_prefix>/** 动态路由
│   │       ├── registry.py      # 路由动态注册 / reload
│   │       ├── handler.py       # 入口
│   │       └── 6 步管道走 core/request_pipeline.py
│   ├── data/app.db              # 运行时生成
│   ├── requirements.txt
│   └── .env.example
├── frontend/                    # Vue 3.5 + Vite + Ant Design Vue 4 + AntV X6
│   ├── src/
│   │   ├── api/                 # axios 封装 + 类型 + 各资源 SDK
│   │   ├── composables/         # use* 复用逻辑
│   │   ├── components/          # 业务组件
│   │   ├── views/               # 6 个一级页面
│   │   ├── layouts/AppLayout.vue
│   │   ├── router/index.ts
│   │   └── ws/                  # WebSocket client
│   └── package.json
├── docs/                        # 6 份核心设计文档（中文）
│   ├── 网管系统模拟工具-需求分析.md
│   ├── 系统架构设计.md
│   ├── 数据库表设计.md
│   ├── API接口设计.md
│   ├── 开发方案.md
│   └── 开发进度.md              # 每日进度日志
├── test_scripts/                # 端到端 / 性能基准脚本
│   ├── test_settings_m4_01.py
│   ├── test_topology_io_m4_02.py
│   ├── bench_m4_03.py
│   └── ...（M3 系列 mock 测试）
├── start.sh / start.bat         # 后端一键启动
└── README.md                    # ← 本文件
```

---

## 5. 测试 & 性能基准

后端要先起在 `127.0.0.1:8080`，然后：

```bash
# 系统设置热生效 + mock_path_prefix 热重载
python test_scripts/test_settings_m4_01.py

# 拓扑 JSON 导入/导出 + 错误路径
python test_scripts/test_topology_io_m4_02.py

# 30k 节点性能基准（首次会建 fixture，约 1.5s）
python test_scripts/bench_m4_03.py [--reset]

# Mock 接口管道（M3）
python test_scripts/test_mock_m3_01.py   # 路由 + 静态体
python test_scripts/test_mock_m3_02.py   # SQL 数据源
python test_scripts/test_mock_m3_03.py   # 6 步管道完整链路
python test_scripts/test_mock_m3_05.py   # 异常注入（延迟 + 概率错误）
```

M4-03 性能基准（30k 节点 / 30k 边）实测：

| 指标 | 实测 | 阈值 |
|---|---|---|
| GET /graph 全量 | 1001 ms | <3000 ms |
| GET /nodes 分页（任意页） | 17–42 ms | <1000 ms |
| PATCH /canvas 30k 坐标批量保存 | 288 ms | <3000 ms |

---

## 6. 故障排查

| 现象 | 原因 / 处理 |
|---|---|
| 启动后端报 `ModuleNotFoundError: app` 或 uvicorn 报 `import_from_string` 失败 | 你在仓库根跑命令了。手动启动必须先 `cd backend` 再跑 `python -m app.main` 或 `python -m uvicorn app.main:app`；用 `start.sh / start.bat` 会自动 cd，不会踩这个坑 |
| 前端打开白屏 + 控制台 `Failed to fetch /admin/api/health` | 后端没起，或端口被占。Windows: `netstat -ano \| findstr 8080`；`Stop-Process -Id <PID> -Force` |
| Mock 调用返回 404 | 检查 `/settings` 里的 `mock_path_prefix` 是不是预期的；改前缀后会自动热重载，不需要重启进程 |
| Mock 调用返回 `400` + `code: 40025` | 严格白名单拦截：该接口在 `config.request.query` 中声明了允许的 query 字段，调用方传了未声明的字段。要么把该字段加入 query 声明，要么关闭严格白名单开关（前端接口编辑弹窗 → 请求规格 → 启用 Query 严格白名单） |
| `pnpm install` 卡住 | 设国内镜像：`pnpm config set registry https://registry.npmmirror.com` |
| 改完 `.env` 不生效 | `start.sh / start.bat` 在启动时读取 `backend/.env`；改完要重启进程；`autosave_interval` / `mock_path_prefix` 例外，可以在 `/settings` 页热改 |
| 删库重来 | 删 `backend/data/app.db*`（含 `-wal`、`-shm`）后重启，自动重建 |
| `curl http://127.0.0.1:5173` 拒绝连接，但浏览器开 `localhost:5173` 正常 | Vite 默认绑 IPv6 `::1`；用 `localhost` 或 `[::1]:5173` 访问；浏览器无感 |

---

## 7. 设计文档

进阶阅读全部在 `docs/`：

- **[需求分析](docs/网管系统模拟工具-需求分析.md)** — 用户故事、痛点、范围
- **[系统架构](docs/系统架构设计.md)** — 部署图 / 模块切分 / 路由树
- **[数据库表设计](docs/数据库表设计.md)** — 12 张表 DDL 与字段说明
- **[API 接口设计](docs/API接口设计.md)** — 所有 `/admin/api/**` 端点
- **[开发方案](docs/开发方案.md)** — M1–M4 里程碑与验收
- **[开发进度](docs/开发进度.md)** — 按日期记录的工程笔记（含 root cause 分析）

---

## 8. 许可证

内部学习项目，未指定开源许可。
