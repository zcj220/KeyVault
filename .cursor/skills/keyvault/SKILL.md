---
name: keyvault
description: >-
  使用本地 KeyVault MCP 管理公司记忆库与待办提醒：密码、Token、服务器、业务备注，
  以及到期前提醒。用户口述写入、提问读取、要求提醒事项时使用。会话开始应先看提醒。
---

# KeyVault 弹性记忆库 + 提醒

## 会话开始（很重要）

先调用 `vault_status` 或 `list_reminders(only_due=true)`。  
若 `reminders_due_count > 0`，**先用一两句话提醒用户有哪些待办**（标题、到期日、剩余天数），再继续其它工作。

## 核心模型

- **Entry**：名称、分类、用途摘要、标签、过期日 + 任意弹性字段（key/value/purpose/secret）
- **Reminder**：标题、到期日 `due_at`、提前天数（默认 3）、备注、是否完成
- 字段名可自由：Token / KEY / AccessKeyId…
- 建议分类：企业基础、开放平台支付、国外网站、国内网站、服务器及数据库、域名DNS邮件、Whisperkin、杂记

## 写入资产（改密码 / 同类别新增 —— 直接跟 AI 说即可）

用户说例如：

- 「Cloudflare 密码改成 xxx，帮我更新进记忆库」
- 「国外网站再加一条：xxx，账号密码是…」
- 「把腾讯云那条的 SecretKey 换成新的」

AI 应主动写入，不要只口头记下：

1. 先 `search_entries` 看有没有同名/同类
2. 已有 → `update_entry` / `upsert_field` / `update_credential`
3. 没有 → `add_entry`（分类尽量与同类一致，如「国外网站」）
4. 成功后只确认「已写入」，不主动复述完整密钥

## 一键导出

用户说「导出全部 / 按分类导出」时，调用 `export_vault`：

- `format=md`：按分类 Markdown（默认可含明文）
- `format=json`：按分类 JSON
- `format=encrypted`：加密 `.kvault` 备份（最安全）

文件会写到用户「下载」文件夹。

## 提醒（用户自己写或让 AI 写）

用户说「提醒我…」「三天后要续费…」「记一下下周交…」时：

1. 解析标题、到期日、备注；未说提前天数则用 3
2. 调用 `add_reminder(title, due_at, notes, remind_before_days=3)`
3. 回复已记下，并说明从哪天开始会提醒

完成时：`complete_reminder`  
- 仅一次：标记完成  
- 每周/每月/每季度/每年：自动滚到下一期，继续提醒  

查看：`list_reminders` / `list_reminders(only_due=true)`  
周期参数 `repeat`：`once` | `weekly` | `monthly` | `quarterly` | `yearly`  
（每周按到期日的星期几；每月按几号；每季度=每3个月；每年按月日。无需再自定义复杂规则。）

## 读取资产

1. `search_entries` → `get_entry`
2. 多条匹配先问清楚
3. 凭证过期要提醒
4. 不整库导出明文
