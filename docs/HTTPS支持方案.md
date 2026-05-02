# HTTPS 支持 — 开发方案设计

## 1. 背景与需求

| 维度 | 现状 | 目标 |
|------|------|------|
| 调用方协议 | 测试插件针对生产网管系统使用 **HTTPS** | mock 工具提供 `https://` 入口，满足调用方的 TLS 校验 |
| 后端 | `uvicorn` 仅监听 HTTP（`http://0.0.0.0:8080`） | 可配置化切换至 HTTPS |
| 证书 | 无 | 支持自签证书自动生成 + 用户自定义证书两种模式 |
| 影响面 | — | admin API、mock 路由、WebSocket 均需适配 |

**核心场景**：用户在接口配置中创建了 `POST /rest/plat/smapp/v1/oauth/token`（PUT），测试插件以 `https://127.0.0.1:8443/rest/plat/smapp/v1/oauth/token` 发起请求，mock 工具返回静态响应体。

---

## 2. 方案对比

### 方案 A — 全量 HTTPS（推荐）

```
┌──────────────────────────────────────────┐
│  uvicorn (单一进程)                        │
│  https://0.0.0.0:8443                    │
│  ├─ /admin/api/**   ← 管理 API（HTTPS）    │
│  ├─ /admin/ws       ← WebSocket（WSS）     │
│  └─ /rest/**        ← mock 路由（HTTPS）    │
└──────────────────────────────────────────┘
       ▲ HTTPS (self-signed cert)
       │
┌──────┴───────┐
│ 测试插件      │  ← 直接调 https://127.0.0.1:8443/...
└──────────────┘
```

| 优点 | 缺点 |
|------|------|
| 架构简单，单进程无额外依赖 | admin 前端也必须走 HTTPS（Vite proxy 配置 `secure: false` 即可） |
| `.env` 一个开关控制 HTTP ↔ HTTPS | 切换协议需重启（uvicorn 无法热切换 TLS） |
| 后端改动量小（约 40 行） | 不能同时暴露 HTTP + HTTPS（选方案 B 解决） |

### 方案 B — 双端口混合

```
┌─────────────────┐    ┌──────────────────┐
│ uvicorn #1 (HTTP)│    │ uvicorn #2 (HTTPS)│
│ 0.0.0.0:8080    │    │ 0.0.0.0:8443     │
│ /admin/api/**    │    │ /rest/**         │
│ /admin/ws        │    │ (仅 mock 路由)    │
└─────────────────┘    └──────────────────┘
```

| 优点 | 缺点 |
|------|------|
| admin 前端维持 HTTP，零感知 | 需管理两个进程（start.bat 需启动两个 uvicorn） |
| mock 路由与 admin 彻底隔离 | RouteRegistry 需要按实例拆分（admin 实例不加载 mock 路由，HTTPS 实例不加载 admin 路由） |
| 更贴近"对外=HTTPS，对内=HTTP"的生产部署模型 | 代码改动量翻倍；WS 推送跨实例问题（mock 实例保存拓扑时需要通知 admin 实例的 WS 客户端） |

### 推荐结论

**推荐方案 A**。理由：
- 本工具是本地开发/测试工具，不是生产服务——admin 前端走 HTTPS 无实际障碍（Vite proxy + `secure: false` 对自签证书透明）
- 单进程运维简单，启动脚本仅需增加 SSL 参数
- 未来如需双协议，加一层 Nginx 反向代理做 TLS 终结即可，无需改代码

---

## 3. 方案 A 详细设计

### 3.1 新增环境变量

在 `backend/.env.example` 中增加 4 个变量：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `APP_SSL_ENABLED` | `false` | `true` 时启用 HTTPS |
| `APP_SSL_CERTFILE` | `./data/ssl/cert.pem` | SSL 证书文件路径（相对 backend/） |
| `APP_SSL_KEYFILE` | `./data/ssl/key.pem` | SSL 私钥文件路径 |
| `APP_SSL_KEYFILE_PASSWORD` | （空） | 私钥密码（PEM 加密时使用，明文为空） |

`APP_PORT` 默认值保持不变（`8080`），用户如需 HTTPS 建议改为 `8443`。

### 3.2 自签证书自动生成

**触发条件**：`APP_SSL_ENABLED=true` 且证书/私钥文件不存在。

**生成逻辑**（在 `app/main.py` 的 `main()` 或独立 `cli.py` 中）：

```
1. 检查 certfile / keyfile 是否存在
2. 不存在 → 用 Python 标准库 cryptography 或  subprocess(openssl) 生成：
   - RSA 2048-bit 私钥
   - 自签名 X.509 证书，CN=127.0.0.1，SAN=DNS:localhost,IP:127.0.0.1
   - 有效期 3650 天
   - 写入 ./data/ssl/{cert,key}.pem
3. 存在 → 直接使用
```

**为什么不依赖 openssl？** Windows 环境 openssl 不一定在 PATH 中。优先使用 Python `cryptography` 库（已在 requirements.txt 或作为可选依赖加入），备选方案是提供一个独立的 `gen_cert.py` 脚本。

### 3.3 后端改动清单

| # | 文件 | 改动 | 行数 |
|---|------|------|------|
| C1 | `backend/app/core/config.py` | `Settings.__init__` 读取 4 个 SSL 环境变量 | +4 |
| C2 | `backend/app/main.py` | `main()` 根据 `ssl_enabled` 向 `uvicorn.run()` 传入 `ssl_keyfile` / `ssl_certfile` / `ssl_keyfile_password`；**启动前**检查证书存在性，不存在则自动生成 | +25 |
| C3 | `backend/app/admin/schemas/settings.py` | `SettingsRuntime` 新增 `ssl_enabled: bool` 字段，展示给前端 | +1 |
| C4 | `backend/app/admin/settings.py` | `_runtime_block()` 增加 `ssl_enabled` 字段 | +1 |
| C5 | `backend/.env.example` | 追加 SSL 变量声明 | +4 |
| C6 | `start.bat` / `start.sh` | 无需改动（已通过 `.env` → `uvicorn` 链路传递），可选增加 SSL 检测提示 | 0~2 |

**总计**：~35 行后端改动。

### 3.4 前端改动清单

| # | 文件 | 改动 | 行数 |
|---|------|------|------|
| F1 | `frontend/vite.config.ts` | 当 `VITE_BACKEND` 以 `https://` 开头时自动追加 `secure: false`（接受自签证书） | +3 |
| F2 | `frontend/src/views/SettingsView.vue` | 系统设置页 `runtime` 区域展示 `ssl_enabled` 状态（绿色"已启用" / 灰色"未启用"） | +5 |
| F3 | `frontend/src/ws/client.ts` | WebSocket 客户端根据后端协议自动选择 `ws://` 或 `wss://`（当前硬编码相对路径，无需改动） | 0 |

**总计**：~8 行前端改动。

### 3.5 启动方式变化

**HTTP 模式（默认，零变化）**：
```bash
# .env 不写 APP_SSL_ENABLED 或设 false
./start.bat
# → uvicorn running on http://0.0.0.0:8080
```

**HTTPS 模式**：
```bash
# .env
APP_SSL_ENABLED=true
APP_PORT=8443

./start.bat
# → 检查 ./data/ssl/cert.pem ... 不存在，自动生成自签证书
# → uvicorn running on https://0.0.0.0:8443
```

**前端适配**：
```bash
# 后端开 HTTPS 后，前端需同步指定 https 协议
VITE_BACKEND=https://localhost:8443 pnpm dev
```

### 3.6 测试脚本适配

现有 `test_scripts/` 下的所有测试脚本使用 Python `urllib.request`，HTTPS + 自签证书场景需要在请求时传入 `context=ssl._create_unverified_context()`。

**改动策略**：在 `test_scripts/` 增加一个共享模块 `test_utils.py`，封装 `_request()` 函数，自动检测后端协议并处理 SSL 上下文。各测试脚本 import 使用，避免逐个修改。

---

## 4. 影响面评估

| 模块 | 影响 | 处理 |
|------|------|------|
| admin API（CRUD） | 无影响 | URL 不变，仅协议变化 |
| mock 路由 | **目标受益者** | 测试插件可直接以 HTTPS 调用 |
| WebSocket（`/admin/ws`） | 前端连接协议变为 `wss://` | 当前前端使用相对路径，Vite proxy 自动处理 |
| 动态路由注册（RouteRegistry） | 无影响 | 路由注册不关心传输层 |
| 请求管道（RequestPipeline） | 无影响 | 管道不感知协议 |
| SQL 执行器 / 响应模板 | 无影响 | 纯逻辑层 |
| 前端 Vite 开发服务器 | proxy target 变为 `https://` | `secure: false` 跳过证书验证 |
| 测试脚本（Python） | 需跳过自签证书验证 | `ssl._create_unverified_context()` |
| curl 调用 | 需加 `-k` / `--insecure` | README 提醒 |

---

## 5. 前置条件与风险

| 项 | 说明 |
|------|------|
| Python `cryptography` 库 | 自签证书生成需要。若用户不希望增加依赖，备选方案是提供 `gen_cert.ps1`（PowerShell，Windows 内置）或 `gen_cert.sh`（openssl）脚本手动生成 |
| 端口占用 | HTTPS 建议使用 `8443` 端口，需确认不被占用 |
| 证书信任 | 自签证书不被浏览器/系统信任是**预期行为**。前端 Vite proxy 通过 `secure: false` 绕过；测试脚本通过 `_create_unverified_context` 绕过；测试插件需配置忽略证书错误（这是调用方的责任） |
| 协议切换重启 | 从 HTTP 切换到 HTTPS（或反向）必须重启后端。这个约束是 uvicorn 的局限性，可在设置页 UI 提示 |

---

## 6. 任务分解（预估 0.5 人日）

| # | 任务 | 内容 | 预估 |
|---|------|------|------|
| H1 | 后端 SSL 配置 | `config.py` 读 SSL 变量 + `main.py` 传参给 uvicorn + 自签证书自动生成 | 1h |
| H2 | 前端适配 | Vite proxy `secure: false` + 设置页展示 SSL 状态 | 0.5h |
| H3 | 测试脚本适配 | `test_utils.py` 封装 SSL 上下文 + 全量回归 | 1h |
| H4 | 文档更新 | `.env.example` / README / 开发进度 同步 | 0.5h |

---

## 7. 遗留出口

| 出口 | 说明 |
|------|------|
| LE-01 自定义证书 | 用户提供公司内部 CA 签发的证书，设置 `APP_SSL_CERTFILE` / `APP_SSL_KEYFILE` 指向真实证书路径，关闭自动生成 |
| LE-02 双端口模式 | 如未来确实需要 admin HTTP + mock HTTPS 同时运行，可增加 `APP_MOCK_SSL_ONLY=true` 模式启动第二个 uvicorn 实例（需拆分路由挂载） |
| LE-03 Nginx 反向代理 | 如需完整 TLS 终结 + 多域名 + 日志，在工具外层套 Nginx，后端保持 HTTP |

---

## 8. 决定项（需要你确认）

1. **方案选择**：确认方案 A（全量 HTTPS），还是倾向于方案 B（双端口）？
2. **自签证书依赖**：是否接受 `cryptography` 作为新依赖，还是用 PowerShell 脚本生成？
3. **默认端口**：HTTPS 模式下建议 `8443`，是否接受？
4. **Settings 页**：SSL 开关是否需要做成 UI 可控（热切换）？我的建议是**不需要**——uvicorn 不支持热切换 TLS，只做运行时状态展示即可。
