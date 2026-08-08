from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from keyvault.store import VaultStore


def build_classified_export(
    store: VaultStore,
    *,
    include_secret: bool = True,
) -> dict[str, Any]:
    """按分类汇总，供 JSON / Markdown 导出。"""
    store.load()
    by_cat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in store.list_all():
        by_cat[entry.category or "其他"].append(
            entry.public_view(include_secret=include_secret)
        )
    for cat in by_cat:
        by_cat[cat].sort(key=lambda x: x.get("name", ""))
    reminders = [r.public_view() for r in store.list_reminders(include_done=True)]
    return {
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "vault_path": str(store.path),
        "include_secret": include_secret,
        "entry_count": sum(len(v) for v in by_cat.values()),
        "categories": dict(sorted(by_cat.items(), key=lambda kv: kv[0])),
        "reminders": reminders,
    }


def to_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# KeyVault 分类导出")
    lines.append("")
    lines.append(f"- 导出时间：{payload.get('exported_at')}")
    lines.append(f"- 库路径：{payload.get('vault_path')}")
    lines.append(f"- 条目数：{payload.get('entry_count')}")
    lines.append(f"- 含明文敏感字段：{'是' if payload.get('include_secret') else '否（已打码）'}")
    lines.append("")

    cats: dict[str, list[dict[str, Any]]] = payload.get("categories") or {}
    for cat, items in cats.items():
        lines.append(f"## {cat}（{len(items)}）")
        lines.append("")
        for item in items:
            lines.append(f"### {item.get('name')}")
            if item.get("summary"):
                lines.append(f"- 用途：{item.get('summary')}")
            if item.get("kind"):
                lines.append(f"- 类型：{item.get('kind')}")
            if item.get("expires_at"):
                lines.append(f"- 过期：{item.get('expires_at')}（{item.get('expiry_status')}）")
            fields = item.get("fields") or []
            if fields:
                lines.append("- 字段：")
                for f in fields:
                    purpose = f" （{f.get('purpose')}）" if f.get("purpose") else ""
                    secret_mark = " [敏感]" if f.get("secret") else ""
                    lines.append(f"  - {f.get('key')}: {f.get('value')}{purpose}{secret_mark}")
            lines.append("")

    reminders = payload.get("reminders") or []
    lines.append(f"## 提醒待办（{len(reminders)}）")
    lines.append("")
    if not reminders:
        lines.append("（无）")
    for r in reminders:
        done = "已完成" if r.get("done") else "未完成"
        lines.append(
            f"- [{done}] {r.get('title')} | 到期 {r.get('due_at')} | "
            f"{r.get('repeat_label')} | 提前{r.get('remind_before_days')}天"
        )
        if r.get("notes"):
            lines.append(f"  - 备注：{r.get('notes')}")
    lines.append("")
    return "\n".join(lines)
