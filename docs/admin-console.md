# 管理员控制台启动文档

本文档用于说明 InkSight 管理员控制台的用途、启动方式和安全配置原则。
这部分代码会保留在开源仓中，因此本文档不会写死端口号、管理员账号或管理员密码；所有敏感信息都通过环境变量注入。

## 1. 管理员控制台是什么

管理员控制台是一套独立于主站 `webapp/` 的管理界面，由两部分组成：

- `adminapp/`：Next.js 管理前端，只暴露管理员登录页和管理界面
- `backend/api/routes/admin.py`：FastAPI 管理接口，负责登录、统计、邀请码、日志查询

推荐部署方式：

- 将管理前端作为一个独立服务运行
- 将管理接口复用现有 `backend/`
- 通过反向代理或部署平台把管理台挂到你自己的内网或公网地址
- 不在公开文档、页面导航或仓库示例里写死实际访问地址

## 2. 当前支持的功能

当前管理台已经支持以下能力：

- 管理员账号密码登录
- 邀请码批量生成
- 基础运营概览
- 应用事件日志检索
- 用户概览
- 设备概览
- 实时轮询刷新

### 邀请码管理

- 批量生成邀请码
- 配置每个邀请码增加的免费额度
- 配置前缀和备注
- 查看批次、使用状态和使用人

### 基础运营概览

- 注册用户总数
- 累计 LLM 调用次数
- 邀请码已使用 / 未使用数量
- 最近错误事件
- 最近管理员操作记录

### 日志查看

当前日志页优先展示应用内事件日志，而不是直接读取服务器 stdout 文件。
这样做的好处是字段结构稳定、易于筛选，也更适合开源项目中的跨环境部署。

当前日志表支持查看：

- 时间
- 分类与级别
- 事件类型
- API 类型
- Model 名称
- 用户
- 设备
- Raw Message

其中：

- 无设备预览产生的日志会在设备列显示 `no device preview`
- API 类型会区分 `invite code` 和 `api url`
- Model 列会显示本次调用对应的模型名

## 3. 安全配置原则

为了避免把敏感信息直接暴露在开源仓中，建议遵循以下原则：

- 管理员账号仅通过环境变量注入
- 管理员密码只保存哈希，不保存明文
- 管理台端口仅通过环境变量注入
- 管理台地址不要写进公开说明、页面导航或示例截图
- 公网部署时开启 HTTPS，并打开安全 Cookie

当前代码已经支持以下安全点：

- 管理员账号来自环境变量 `ADMIN_CONSOLE_USERNAME`
- 管理员密码哈希来自环境变量 `ADMIN_CONSOLE_PASSWORD_HASH`
- 管理员会话签名密钥来自环境变量 `ADMIN_CONSOLE_SESSION_SECRET`
- 管理员 Cookie 是否开启 `Secure` 由 `ADMIN_CONSOLE_COOKIE_SECURE` 控制
- `adminapp` 启动时必须通过 `ADMIN_CONSOLE_PORT` 或 `PORT` 传入端口，不再使用仓库中的硬编码端口

## 4. 启动前准备

### 依赖要求

- Python 3.10+
- Node.js 20+
- `pip`
- `npm`

### 安装依赖

后端：

```bash
cd backend
pip install -r requirements.txt
python scripts/setup_fonts.py
```

管理前端：

```bash
cd adminapp
npm install
```

## 5. 生成管理员密码哈希

管理员密码不要直接写进环境变量。
先在本地生成 PBKDF2 哈希，再把哈希结果填入 `ADMIN_CONSOLE_PASSWORD_HASH`。

示例命令：

```bash
cd backend

python3 - <<'PY'
from core.config_store import _hash_password

password = input("Admin password: ").strip()
print(_hash_password(password)[0])
PY
```

输出结果形如：

```text
<salt_hex>:<derived_key_hex>
```

把这段完整输出保存到你自己的部署环境变量中即可，不要提交到仓库。

## 6. 关键环境变量

### 后端管理接口

这些变量由 `backend/` 使用：

- `ADMIN_CONSOLE_USERNAME`
- `ADMIN_CONSOLE_PASSWORD_HASH`
- `ADMIN_CONSOLE_SESSION_SECRET`
- `ADMIN_CONSOLE_COOKIE_SECURE`

建议额外准备两项启动变量：

- `ADMIN_CONSOLE_BACKEND_HOST`
- `ADMIN_CONSOLE_BACKEND_PORT`

这两个变量不是后端代码内部读取的配置项，而是推荐你在启动命令里使用的部署变量，用来避免把监听地址写死在脚本和文档中。

### 管理前端

这些变量由 `adminapp/` 使用：

- `INKSIGHT_BACKEND_API_BASE`
- `ADMIN_CONSOLE_PORT` 或 `PORT`
- `ADMIN_CONSOLE_HOST`（可选）

其中：

- `INKSIGHT_BACKEND_API_BASE` 指向运行中的后端 API 地址
- `ADMIN_CONSOLE_PORT` 控制管理前端监听端口
- `ADMIN_CONSOLE_HOST` 控制管理前端监听网卡

## 7. 启动管理接口

先为当前 shell 注入环境变量：

```bash
export ADMIN_CONSOLE_USERNAME='<set-locally>'
export ADMIN_CONSOLE_PASSWORD_HASH='<set-locally>'
export ADMIN_CONSOLE_SESSION_SECRET='<generate-locally>'
export ADMIN_CONSOLE_COOKIE_SECURE='true'

export ADMIN_CONSOLE_BACKEND_HOST='<set-locally>'
export ADMIN_CONSOLE_BACKEND_PORT='<set-locally>'
```

如果你还没有生成会话密钥，可以用下面的命令：

```bash
python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
```

然后启动后端：

```bash
cd backend

python3 -m uvicorn api.index:app \
  --host "${ADMIN_CONSOLE_BACKEND_HOST}" \
  --port "${ADMIN_CONSOLE_BACKEND_PORT}"
```

说明：

- 管理接口复用主后端进程，不需要单独维护另一套数据库
- 管理接口路径位于 `/api/admin/*`
- 如果你已经有主站后端在运行，也可以把这些环境变量注入到同一个后端进程中

## 8. 启动管理前端

为管理前端注入运行参数：

```bash
export INKSIGHT_BACKEND_API_BASE='http://127.0.0.1:<your-admin-backend-port>'
export ADMIN_CONSOLE_HOST='<set-locally>'
export ADMIN_CONSOLE_PORT='<set-locally>'
```

本地开发：

```bash
cd adminapp
npm run dev
```

生产启动：

```bash
cd adminapp
npm run build
npm run start
```

说明：

- `adminapp` 会拒绝在未提供 `ADMIN_CONSOLE_PORT` 或 `PORT` 的情况下启动
- 这样可以避免把管理台端口硬编码在开源仓脚本中
- 管理前端通过 `/api/admin/*` 代理到 `INKSIGHT_BACKEND_API_BASE`

## 9. 启动后的验证

完成后，请使用你自己的管理台地址访问登录页：

```text
http(s)://<your-admin-console-host>:<your-admin-console-port>/login
```

建议验证：

- 能否打开登录页
- 能否使用你自己配置的管理员账号登录
- 总览页是否正常加载
- 邀请码是否能生成
- 日志页是否能看到最近应用事件

## 10. 部署建议

如果你准备长期使用管理员控制台，推荐补上这些部署措施：

- 给管理台单独域名或子路径，不公开展示
- 只在反向代理层暴露管理前端，不直接暴露原始监听地址
- 开启 HTTPS
- `ADMIN_CONSOLE_COOKIE_SECURE=true`
- 给 `/api/admin/auth/login` 所在服务加上基础监控和失败告警
- 结合反向代理额外做 IP 白名单或访问控制

## 11. 常见问题

### 登录总是失败

优先检查：

- `ADMIN_CONSOLE_USERNAME` 是否和输入一致
- `ADMIN_CONSOLE_PASSWORD_HASH` 是否由同一份密码生成
- `ADMIN_CONSOLE_SESSION_SECRET` 是否为空
- 后端是否已经重启并加载了最新环境变量

### 前端能打开，但数据加载失败

优先检查：

- `INKSIGHT_BACKEND_API_BASE` 是否指向正确的后端地址
- 后端是否真的启用了管理员环境变量
- 浏览器请求 `/api/admin/auth/me` 是否返回 200 或 401

### 启动时提示缺少端口

这是预期行为。`adminapp` 已经去掉仓库内硬编码端口，必须通过以下任一变量传入：

- `ADMIN_CONSOLE_PORT`
- `PORT`

### 公网部署要不要继续隐藏地址

建议继续隐藏。
“隐藏地址”不能代替鉴权，但能减少无意义扫描和误访问。
真正的安全边界仍然应当是：

- 账号密码
- 安全 Cookie
- HTTPS
- 限流
- 审计日志
