from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from keyvault.store import VaultStore


def build_classified_export(
    store: VaultStore,
    *,
    include_secret: bool = True,
) -> dict[str, Any]:
    """按分类汇总，供 JSON / Markdown / Excel 导出。"""
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


def _sheet_title(name: str, used: set[str]) -> str:
    """Excel 工作表名：最多 31 字符，不能含 \\ / ? * [ ]。"""
    cleaned = re.sub(r'[\\/?*\[\]:]', "_", (name or "其他").strip()) or "其他"
    cleaned = cleaned[:31]
    base = cleaned
    n = 2
    while cleaned in used:
        suffix = f"_{n}"
        cleaned = (base[: 31 - len(suffix)] + suffix)[:31]
        n += 1
    used.add(cleaned)
    return cleaned


def _autosize(ws) -> None:
    for col in ws.columns:
        letter = get_column_letter(col[0].column)
        width = 10
        for cell in col:
            val = "" if cell.value is None else str(cell.value)
            width = min(max(width, len(val) + 2), 48)
        ws.column_dimensions[letter].width = width


def to_excel_bytes(payload: dict[str, Any]) -> bytes:
    """按分类生成 xlsx 字节：总览 + 各分类表 + 提醒。"""
    wb = Workbook()
    used_titles: set[str] = set()
    header_font = Font(bold=True)
    wrap = Alignment(wrap_text=True, vertical="top")

    # --- 总览 ---
    ws_all = wb.active
    ws_all.title = _sheet_title("总览", used_titles)
    overview_headers = [
        "分类",
        "名称",
        "用途摘要",
        "类型",
        "标签",
        "创建时间",
        "修改时间",
        "过期日",
        "字段数",
    ]
    ws_all.append(overview_headers)
    for cell in ws_all[1]:
        cell.font = header_font

    cats: dict[str, list[dict[str, Any]]] = payload.get("categories") or {}
    field_headers = [
        "名称",
        "用途摘要",
        "类型",
        "标签",
        "创建时间",
        "修改时间",
        "过期日",
        "字段名",
        "字段值",
        "字段用途",
        "敏感",
    ]

    for cat, items in cats.items():
        for item in items:
            fields = item.get("fields") or []
            ws_all.append(
                [
                    cat,
                    item.get("name") or "",
                    item.get("summary") or "",
                    item.get("kind") or "",
                    ", ".join(item.get("tags") or []),
                    item.get("created_at") or "",
                    item.get("updated_at") or "",
                    item.get("expires_at") or "",
                    len(fields),
                ]
            )

        ws = wb.create_sheet(_sheet_title(cat, used_titles))
        ws.append(field_headers)
        for cell in ws[1]:
            cell.font = header_font
        for item in items:
            fields = item.get("fields") or []
            base = [
                item.get("name") or "",
                item.get("summary") or "",
                item.get("kind") or "",
                ", ".join(item.get("tags") or []),
                item.get("created_at") or "",
                item.get("updated_at") or "",
                item.get("expires_at") or "",
            ]
            if not fields:
                ws.append(base + ["", "", "", ""])
                continue
            for f in fields:
                row = base + [
                    f.get("key") or "",
                    f.get("value") if f.get("value") is not None else "",
                    f.get("purpose") or "",
                    "是" if f.get("secret") else "否",
                ]
                ws.append(row)
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = wrap
        _autosize(ws)

    for row in ws_all.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = wrap
    _autosize(ws_all)

    # --- 提醒 ---
    ws_r = wb.create_sheet(_sheet_title("提醒待办", used_titles))
    rem_headers = [
        "标题",
        "到期日",
        "状态",
        "周期",
        "提前提醒天数",
        "备注",
        "创建时间",
        "修改时间",
    ]
    ws_r.append(rem_headers)
    for cell in ws_r[1]:
        cell.font = header_font
    for r in payload.get("reminders") or []:
        ws_r.append(
            [
                r.get("title") or "",
                r.get("due_at") or "",
                "已完成" if r.get("done") else "未完成",
                r.get("repeat_label") or r.get("repeat") or "",
                r.get("remind_before_days"),
                r.get("notes") or "",
                r.get("created_at") or "",
                r.get("updated_at") or "",
            ]
        )
    _autosize(ws_r)

    # --- 导出说明 ---
    ws_meta = wb.create_sheet(_sheet_title("导出说明", used_titles))
    ws_meta.append(["项", "值"])
    for cell in ws_meta[1]:
        cell.font = header_font
    ws_meta.append(["导出时间", payload.get("exported_at") or ""])
    ws_meta.append(["库路径", payload.get("vault_path") or ""])
    ws_meta.append(["条目数", payload.get("entry_count")])
    ws_meta.append(
        [
            "含明文敏感字段",
            "是" if payload.get("include_secret") else "否（已打码）",
        ]
    )
    _autosize(ws_meta)

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def write_excel(payload: dict[str, Any], dest: Path) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(to_excel_bytes(payload))
    return dest


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
