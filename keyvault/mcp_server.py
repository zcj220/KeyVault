from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from keyvault.config import get_master_password, get_vault_path
from keyvault.local_settings import apply_local_env
from keyvault.models import SUGGESTED_CATEGORIES, parse_expiry
from keyvault.store import VaultError, VaultStore, summarize_expiry

apply_local_env()

mcp = FastMCP("keyvault")

# stdio 进程内复用；若网盘同步改了文件，VaultStore.load 会按 mtime 自动重载
_STORE: VaultStore | None = None


def _store() -> VaultStore:
    global _STORE
    password = get_master_password()
    if not password:
        raise VaultError(
            "未设置环境变量 KEYVAULT_PASSWORD。请在 Cursor MCP 配置里设置主密码。"
        )
    path = get_vault_path()
    if (
        _STORE is None
        or _STORE.path != path
        or _STORE.password != password
    ):
        _STORE = VaultStore(path, password)
    return _STORE


def _ok(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _err(exc: Exception) -> str:
    return _ok({"error": str(exc)})


def _with_expiry_warning(view: dict[str, Any]) -> dict[str, Any]:
    if view.get("expiry_status") == "expired":
        view["warning"] = "该条目已过期，请先轮换再使用"
    elif view.get("expiry_status") == "expiring_soon":
        view["warning"] = f"该条目即将过期（剩余 {view.get('days_until_expiry')} 天）"
    return view


@mcp.tool()
def vault_status() -> str:
    """查看记忆库状态。会话开始时优先调用：会返回需要提醒的待办（到期前 N 天/已过期）。"""
    try:
        store = _store()
        # 先按磁盘最新文件加载（网盘同步后也能看到另一台电脑的修改）
        store.load()
        items = store.list_all()
        cats: dict[str, int] = {}
        for item in items:
            cats[item.category] = cats.get(item.category, 0) + 1
        due = store.due_reminders()
        return _ok(
            {
                "vault_path": str(store.path),
                "exists": store.exists(),
                "summary": summarize_expiry(items),
                "categories": cats,
                "suggested_categories": SUGGESTED_CATEGORIES,
                "reminders_due": [r.public_view() for r in due],
                "reminders_due_count": len(due),
                "alert": (
                    f"有 {len(due)} 条待办需要关注（含到期前提醒/已过期）"
                    if due
                    else "当前没有需要提醒的待办"
                ),
                "model": "弹性字段 + 提醒（默认到期前 3 天提醒）",
                "sync_hint": "KEYVAULT_PATH 放到网盘后，另一台改完会同步；读取前会自动检测文件更新",
            }
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def reload_vault() -> str:
    """强制从磁盘重新加载记忆库（网盘刚同步完、怀疑还是旧数据时用）。"""
    try:
        store = _store()
        data = store.reload()
        return _ok(
            {
                "ok": True,
                "vault_path": str(store.path),
                "entries": len(data.entries),
                "message": "已重新加载最新库文件",
            }
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def search_entries(
    query: str = "",
    category: str = "",
    tag: str = "",
    kind: str = "",
    include_expired: bool = True,
) -> str:
    """搜索资产/记忆（默认隐藏敏感字段值）。先定位，再 get_entry 取详情。"""
    try:
        items = _store().search(
            query=query,
            category=category or None,
            tag=tag or None,
            kind=kind or None,
            include_expired=include_expired,
        )
        return _ok([i.public_view(include_secret=False) for i in items])
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


# 兼容旧工具名
@mcp.tool()
def search_credentials(
    query: str = "",
    category: str = "",
    tag: str = "",
    include_expired: bool = True,
) -> str:
    """兼容旧名：等同 search_entries。"""
    return search_entries(
        query=query,
        category=category,
        tag=tag,
        include_expired=include_expired,
    )


@mcp.tool()
def get_entry(name_or_id: str, include_secret: bool = True) -> str:
    """按名称或 id 精确获取一条资产（含全部弹性字段）。回答问题/登录时用这个。"""
    try:
        item = _store().get(name_or_id)
        view = _with_expiry_warning(item.public_view(include_secret=include_secret))
        return _ok(view)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def get_credential(name_or_id: str, include_secret: bool = True) -> str:
    """兼容旧名：等同 get_entry。"""
    return get_entry(name_or_id, include_secret=include_secret)


@mcp.tool()
def list_expiring(within_days: int = 14) -> str:
    """列出已过期或即将在 within_days 天内过期的条目。"""
    try:
        store = _store()
        items = store.expiring(within_days=within_days)
        return _ok(
            {
                "within_days": within_days,
                "summary": summarize_expiry(store.list_all()),
                "items": [i.public_view(include_secret=False) for i in items],
            }
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def add_entry(
    name: str,
    category: str = "其他",
    kind: str = "asset",
    summary: str = "",
    tags: str = "",
    expires_at: str = "",
    fields_json: str = "[]",
) -> str:
    """新增一条资产。fields_json 为弹性字段数组 JSON，字段名可自由命名。

    示例 fields_json:
    [
      {"key":"账号","value":"a@b.com","purpose":"登录邮箱"},
      {"key":"Token","value":"xxx","purpose":"API调用","secret":true},
      {"key":"用途说明","value":"域名解析","purpose":"这条记录干什么"}
    ]
    """
    try:
        store = _store()
        store.load()
        entry = store.add_from_parts(
            name=name,
            category=category,
            kind=kind,
            summary=summary,
            tags=tags,
            expires_at=expires_at or None,
            fields=fields_json,
        )
        return _ok({"ok": True, "item": entry.public_view(include_secret=False)})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def add_credential(
    name: str,
    secret: str = "",
    category: str = "其他",
    username: str = "",
    host: str = "",
    tags: str = "",
    notes: str = "",
    expires_at: str = "",
) -> str:
    """兼容旧名：用账号/密码快速新增；也可随后再用 upsert_field 追加任意字段。"""
    try:
        store = _store()
        store.load()
        entry = store.add_from_parts(
            name=name,
            category=category,
            kind="account",
            summary=notes,
            tags=tags,
            expires_at=expires_at or None,
            secret=secret or None,
            username=username,
            host=host,
        )
        return _ok({"ok": True, "item": entry.public_view(include_secret=False)})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def upsert_field(
    name_or_id: str,
    key: str,
    value: str,
    purpose: str = "",
    secret: bool = False,
) -> str:
    """给已有条目新增或更新一个弹性字段。字段名可任意（Token/KEY/AccessKeyId/桶名…）。"""
    try:
        entry = _store().upsert_field(
            name_or_id,
            key=key,
            value=value,
            purpose=purpose,
            secret=secret,
        )
        return _ok({"ok": True, "item": entry.public_view(include_secret=False)})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def remove_field(name_or_id: str, field_key_or_id: str) -> str:
    """删除某条目下的一个弹性字段。"""
    try:
        entry = _store().remove_field(name_or_id, field_key_or_id)
        return _ok({"ok": True, "item": entry.public_view(include_secret=False)})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def update_entry(
    name_or_id: str,
    name: str = "",
    category: str = "",
    kind: str = "",
    summary: str = "",
    tags: str = "",
    expires_at: str = "",
    clear_expiry: bool = False,
) -> str:
    """更新条目元信息（名称/分类/用途摘要/标签/过期日）。改具体字段请用 upsert_field。"""
    try:
        fields: dict[str, object] = {}
        if name:
            fields["name"] = name
        if category:
            fields["category"] = category
        if kind:
            fields["kind"] = kind
        if summary:
            fields["summary"] = summary
        if tags:
            fields["tags"] = tags
        if clear_expiry:
            fields["expires_at"] = ""
        elif expires_at:
            fields["expires_at"] = parse_expiry(expires_at)
        item = _store().update(name_or_id, **fields)
        return _ok({"ok": True, "item": item.public_view(include_secret=False)})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def update_credential(
    name_or_id: str,
    name: str = "",
    secret: str = "",
    category: str = "",
    username: str = "",
    host: str = "",
    tags: str = "",
    notes: str = "",
    expires_at: str = "",
    clear_expiry: bool = False,
) -> str:
    """兼容旧名：可改元信息，以及账号/主机/密码三个常见字段。"""
    try:
        store = _store()
        fields: dict[str, object] = {}
        if name:
            fields["name"] = name
        if category:
            fields["category"] = category
        if tags:
            fields["tags"] = tags
        if notes:
            fields["summary"] = notes
        if username:
            fields["username"] = username
        if host:
            fields["host"] = host
        if secret:
            fields["secret"] = secret
        if clear_expiry:
            fields["expires_at"] = ""
        elif expires_at:
            fields["expires_at"] = expires_at
        item = store.update(name_or_id, **fields)
        return _ok({"ok": True, "item": item.public_view(include_secret=False)})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def delete_entry(name_or_id: str) -> str:
    """软删除一条资产（进回收站，保留 30 天）。"""
    try:
        item = _store().delete(name_or_id)
        return _ok(
            {
                "ok": True,
                "deleted": item.name,
                "message": "已移入回收站，30 天后自动彻底删除；可用 restore_entry 恢复",
            }
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def delete_credential(name_or_id: str) -> str:
    """兼容旧名：等同 delete_entry（软删除）。"""
    return delete_entry(name_or_id)


@mcp.tool()
def list_trash() -> str:
    """查看回收站中的条目。"""
    try:
        items = _store().list_trash()
        return _ok([i.public_view(include_secret=False) for i in items])
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def restore_entry(name_or_id: str) -> str:
    """从回收站恢复一条资产。"""
    try:
        item = _store().restore(name_or_id)
        return _ok({"ok": True, "item": item.public_view(include_secret=False)})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def list_reminders(include_done: bool = False, only_due: bool = False) -> str:
    """列出提醒待办。only_due=true 时只返回需要立刻提醒的（默认提前 3 天窗口内/已过期）。"""
    try:
        store = _store()
        items = store.due_reminders() if only_due else store.list_reminders(include_done=include_done)
        return _ok(
            {
                "count": len(items),
                "items": [r.public_view() for r in items],
            }
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def add_reminder(
    title: str,
    due_at: str,
    notes: str = "",
    remind_before_days: int = 3,
    repeat: str = "once",
) -> str:
    """新增提醒。due_at=YYYY-MM-DD；repeat=once|weekly|monthly|quarterly|yearly；默认提前3天提醒。"""
    try:
        item = _store().add_reminder(
            title=title,
            due_at=due_at,
            notes=notes,
            remind_before_days=remind_before_days,
            repeat=repeat,
        )
        return _ok({"ok": True, "item": item.public_view()})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def complete_reminder(id_or_title: str, done: bool = True) -> str:
    """标记提醒完成/未完成。"""
    try:
        item = _store().complete_reminder(id_or_title, done=done)
        return _ok({"ok": True, "item": item.public_view()})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def delete_reminder(id_or_title: str) -> str:
    """删除一条提醒。"""
    try:
        item = _store().delete_reminder(id_or_title)
        return _ok({"ok": True, "deleted": item.title})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def export_vault(
    format: str = "md",
    include_secret: bool = True,
) -> str:
    """按分类一键导出记忆库。format=md|json|encrypted；encrypted 导出到用户下载目录。"""
    try:
        from datetime import datetime
        from pathlib import Path

        from keyvault.export_util import build_classified_export, to_markdown

        store = _store()
        fmt = (format or "md").lower()
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        downloads = Path.home() / "Downloads"
        downloads.mkdir(parents=True, exist_ok=True)

        if fmt == "encrypted":
            dest = downloads / f"keyvault-backup-{stamp}.kvault"
            store.export_encrypted(dest)
            return _ok({"ok": True, "format": "encrypted", "path": str(dest)})

        payload = build_classified_export(store, include_secret=include_secret)
        if fmt == "json":
            dest = downloads / f"keyvault-分类导出-{stamp}.json"
            dest.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        else:
            dest = downloads / f"keyvault-分类导出-{stamp}.md"
            dest.write_text(to_markdown(payload), encoding="utf-8")
        return _ok(
            {
                "ok": True,
                "format": fmt,
                "path": str(dest),
                "entry_count": payload.get("entry_count"),
                "categories": list((payload.get("categories") or {}).keys()),
            }
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
