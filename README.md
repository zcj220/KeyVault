# KeyVault Agent（本地加密记忆库 + MCP）

本地加密的密钥/备注库：不只记密码，还能记 Token、KEY、服务器、邮箱用途、业务备注。  
**字段名不固定**，可随时增减；通过 Cursor MCP 让 AI **写入 + 读取回答**。

> **开源范围只有程序。** 密码数据在你自己的 `vault.kvault`（建议放 OneDrive / 坚果云）。  
> 请勿提交：`keyvault.local.env`、`mcp.json`、`*.kvault`、明文 Excel/导出。  
> 名称说明：本项目与微软 Azure Key Vault **无关**，是个人/小团队用的本地工具。

## 设计要点：字段可以不断变

不是 Excel 那种死列，而是：

```text
一条资产 Entry
├─ 名称 / 分类 / 整体用途 summary / 标签 / 过期日
└─ 弹性字段 fields[]（想加多少加多少）
     ├─ key: 随便起名（Token / KEY / AccessKeyId / 桶名…）
     ├─ value: 内容
     ├─ purpose: 这个字段干什么用
     └─ secret: 是否敏感（列表默认隐藏）
```

以后有新平台、新密钥：**不用改程序、不用加列**，让 AI `add_entry` 或 `upsert_field` 即可。

建议分类（也可自创）：企业基础 / 开放平台支付 / 国外网站 / 国内网站 / 服务器及数据库 / 域名DNS邮件 / 项目业务 / 杂记 / 其他

## 另一台电脑怎么部署

请看详细说明：**[其他电脑安装.md](./其他电脑安装.md)**（含 Windows / Mac 一键脚本）。

一句话：

1. **GitHub** 装程序（`install-windows.ps1` 或 `install-macos.sh`）
2. **网盘** 同步同一个 `vault.kvault`
3. 界面点「接入 Cursor AI」→ MCP 亮绿灯

## 本地管理界面（你自己也能看、能改）

AI 用 MCP；你自己用浏览器界面——两端读写的是**同一个加密库文件**。

**Mac 最省事：** 双击桌面或项目根目录的 **KeyVault.app**（青绿保险箱图标）。  
也可双击 `scripts/KeyVault启动.command`。重新生成图标应用：`./scripts/build-macos-app.sh`  
**Windows：** 先运行 `powershell -ExecutionPolicy Bypass -File .\scripts\build-windows-shortcut.ps1`，桌面会出现带图标的 **KeyVault** 快捷方式；也可双击 `scripts\KeyVault-start.bat`。

Cursor 里 MCP 已在跑时，再点启动器**不会冲突**：MCP 是对话读写库，启动器只开本机网页（端口 8799）。网页若已开着，只会再打开浏览器，不会重复起服务。两边不要同时改同一条密码即可。

也可以命令行：

```powershell
cd "D:\Projects\KeyVault"
.\scripts\start-ui.ps1
```

浏览器打开 `http://127.0.0.1:8799`：

1. 首次点「首次创建库」并设置主密码
2. 之后可搜索、新建资产、加字段；右侧可建「提醒」
3. 到期前（默认 3 天）打开界面会顶部告警；Cursor 里 AI 也会先提醒
4. 点「接入 Cursor AI」把 MCP 配好

提醒也可对 AI 说：`提醒我 2026-09-01 续费某某服务`。

以后若要打成安装包 / Dock 图标，见 **[包装成可用项目.md](./包装成可用项目.md)**。

默认库路径：`C:\Users\你的用户名\OneDrive\KeyVault\vault.kvault`。  
若改用坚果云：先安装坚果云客户端，同步出本机 `KeyVault` 文件夹后，在界面里改路径即可。

## 先激活虚拟环境（Windows PowerShell）

```powershell
cd "D:\Projects\KeyVault"
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
```

## 快速开始

```powershell
# 1) 创建库
keyvault init

# 2) 新增一条：任意字段
keyvault add --name "示例云-控制台" --category "国外网站" --summary "云服务控制台登录" `
  --field "账号=you@example.com|登录邮箱" `
  --field "密码=xxxx|登录密码|secret" `
  --field "API Token=xxxx|调用 API|secret" `
  --expires-at 2026-12-31

# 3) 以后又多了一个字段？直接补
keyvault field-set "示例云-控制台" --key "Account ID" --value "abc123" --purpose "账号标识"

# 4) 搜索 / 查看
keyvault list --query 示例云
keyvault get "示例云-控制台" --show-secret
keyvault expiring --within-days 14
```

环境变量：

| 变量 | 作用 |
| --- | --- |
| `KEYVAULT_PATH` | 库文件路径（多机共享指到网盘） |
| `KEYVAULT_PASSWORD` | 主密码（MCP 必填） |

## 以后新资产怎么加（推荐让 AI 做）

对话示例：

> 帮我记一条：分类=服务器及数据库，名称=云主机-官网  
> 字段：IP=1.2.3.4（公网），账号=ubuntu，密码=***（SSH），用途=官网服务器  
> 过期：2027-01-01

AI 会调用 `add_entry`。若后来又有 SecretId：

> 给「云主机-官网」加字段 SecretId=xxx，用途=API 调用

AI 调用 `upsert_field`。**不需要你改表头。**

## 多机共享（改这边，那边怎么知道？）

**不需要自建云服务器。** 做法是：两台电脑的 `KEYVAULT_PATH` 都指向**同一个网盘同步文件**。

```text
电脑 A 改密码 → 写入 vault.kvault
       ↓
OneDrive / 坚果云自动同步密文文件
       ↓
电脑 B 的文件更新 → 下次 AI 查询时自动重新加载最新库
```

配置要点：

1. 两台都把 `KEYVAULT_PATH` 设成网盘里同一路径下的 `vault.kvault`（例如 OneDrive\KeyVault\vault.kvault）
2. 主密码两台相同
3. **不要两台同时改**（否则网盘可能出冲突副本）
4. 改完等托盘图标同步完成，再换电脑用（一般几十秒内）

程序已支持：发现库文件被网盘更新后，会自动丢弃旧缓存、读最新内容。  
也可手动：`keyvault export` / `keyvault import --overwrite` 做备份搬家。

## 接到 Cursor

参考 `mcp.json.example`，配置：

- `python -m keyvault.mcp_server`
- `KEYVAULT_PATH` / `KEYVAULT_PASSWORD`

主要 MCP 工具：

| 工具 | 作用 |
| --- | --- |
| `add_entry` | 新建资产 + 一批弹性字段 |
| `upsert_field` | 给已有资产加/改任意字段名 |
| `remove_field` | 删某个字段 |
| `search_entries` | 搜索（默认隐藏敏感值） |
| `get_entry` | 精确读取并回答 |
| `list_expiring` | 过期巡检 |
| `export_vault` | 导出 md / json / xlsx / encrypted |

## 安全说明

- 整库加密（PBKDF2 + Fernet）
- 敏感字段列表默认显示 `***`
- 主密码、真实库文件、本地 env **不要进 Git**
- 截图/聊天尽量少贴明文密钥
- Issues / PR 里请用占位符，不要贴真实账号密码
