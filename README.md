# KeyVault Agent（弹性记忆库）

本地加密的公司记忆库：不只记密码，还能记 Token、KEY、服务器、邮箱用途、业务备注。  
**字段名不固定**，可随时增减；通过 Cursor MCP 让 AI **写入 + 读取回答**。

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

建议分类（也可自创）：企业基础 / 开放平台支付 / 国外网站 / 国内网站 / 服务器及数据库 / 域名DNS邮件 / Whisperkin / 杂记 / 其他

## 另一台电脑怎么部署

请看详细说明：**[其他电脑安装.md](./其他电脑安装.md)**（含 Windows / Mac 一键脚本）。

一句话：

1. **GitHub** 装程序（`install-windows.ps1` 或 `install-macos.sh`）  
2. **OneDrive** 同步同一个 `vault.kvault`  
3. 界面点「接入 Cursor AI」→ MCP 亮绿灯  

## 本地管理界面（你自己也能看、能改）

AI 用 MCP；你自己用浏览器界面——两端读写的是**同一个加密库文件**。

**Mac 最省事：** Finder 里双击 `scripts/KeyVault启动.command`（会自动开服务并打开网页）。  
**Windows：** 双击 `scripts/KeyVault启动.bat`。

也可以命令行：

```powershell
cd "D:\projects\key angent"
.\scripts\start-ui.ps1
```

浏览器打开 `http://127.0.0.1:8799`：

1. 首次点「首次创建库」并设置主密码  
2. 之后可搜索、新建资产、加字段；右侧可建「提醒」  
3. 到期前（默认 3 天）打开界面会顶部告警；Cursor 里 AI 也会先提醒  
4. 点「SYNC MCP」把 AI 接入配好  

提醒也可对 AI 说：`提醒我 2026-09-01 续费 Cloudflare`。  

以后若要打成安装包 / Dock 图标，见 **[包装成可用项目.md](./包装成可用项目.md)**。


默认库路径：`C:\Users\你的用户名\OneDrive\KeyVault\vault.kvault`（本机 OneDrive 已可用）。  
若改用坚果云：先安装坚果云客户端，同步出本机 `KeyVault` 文件夹后，在界面里改路径即可。

## 先激活虚拟环境（Windows PowerShell）

```powershell
cd "D:\projects\key angent"
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
```

## 快速开始

```powershell
# 1) 创建库
keyvault init

# 2) 新增一条：任意字段
keyvault add --name "Cloudflare-域名解析" --category "国外网站" --summary "域名解析与 CDN" `
  --field "账号=you@qq.com|登录邮箱" `
  --field "密码=xxxx|登录密码|secret" `
  --field "API Token=xxxx|调用 Cloudflare API|secret" `
  --expires-at 2026-12-31

# 3) 以后又多了一个字段？直接补
keyvault field-set "Cloudflare-域名解析" --key "Zone ID" --value "abc123" --purpose "域名 Zone"

# 4) 搜索 / 查看
keyvault list --query Cloudflare
keyvault get "Cloudflare-域名解析" --show-secret
keyvault expiring --within-days 14
```

环境变量：

| 变量 | 作用 |
|---|---|
| `KEYVAULT_PATH` | 库文件路径（多机共享指到网盘） |
| `KEYVAULT_PASSWORD` | 主密码（MCP 必填） |

## 以后新资产怎么加（推荐让 AI 做）

对话示例：

> 帮我记一条：分类=服务器及数据库，名称=腾讯云-官网CVM  
> 字段：IP=1.2.3.4（公网），账号=ubuntu，密码=***（SSH），用途=官网服务器  
> 过期：2027-01-01

AI 会调用 `add_entry`。若后来又有 SecretId：

> 给「腾讯云-官网CVM」加字段 SecretId=xxx，用途=API 调用

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
|---|---|
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
- 主密码不要进 Git；截图/聊天尽量少贴明文密钥
