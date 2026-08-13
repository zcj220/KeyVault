from __future__ import annotations

import json
import os
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from keyvault.export_util import build_classified_export, to_excel_bytes, to_markdown
from keyvault.local_settings import (
    ROOT,
    apply_local_env,
    preferred_vault_path,
    save_local_env,
)
from keyvault.models import SUGGESTED_CATEGORIES, Entry, parse_expiry
from keyvault.store import VaultError, VaultStore

WEB_DIR = Path(__file__).resolve().parent / "web"
SECRET_FILE = ROOT / ".web_secret"


def _session_secret() -> str:
    if SECRET_FILE.is_file():
        return SECRET_FILE.read_text(encoding="utf-8").strip()
    value = secrets.token_hex(32)
    SECRET_FILE.write_text(value, encoding="utf-8")
    return value


def _json(data: Any, status: int = 200) -> JSONResponse:
    return JSONResponse(data, status_code=status)


def _store_from_session(request: Request) -> VaultStore:
    password = request.session.get("password")
    path = request.session.get("path") or str(preferred_vault_path())
    if not password:
        raise VaultError("未解锁，请先输入主密码")
    return VaultStore(Path(path), password)


async def index(_: Request) -> FileResponse:
    return FileResponse(WEB_DIR / "index.html", media_type="text/html; charset=utf-8")


async def api_bootstrap(_: Request) -> JSONResponse:
    apply_local_env()
    path = preferred_vault_path()
    return _json(
        {
            "vault_path": str(path),
            "vault_exists": path.is_file(),
            "suggested_categories": SUGGESTED_CATEGORIES,
            "project_root": str(ROOT),
            "sync_hint": (
                "默认建议把 vault.kvault 放在 OneDrive\\KeyVault。"
                "若要用坚果云：先安装客户端并登录，"
                "等 KeyVault 文件夹出现在本机后，在设置里改路径即可。"
            ),
        }
    )


async def api_init(request: Request) -> JSONResponse:
    body = await request.json()
    password = str(body.get("password") or "").strip()
    path = Path(str(body.get("path") or preferred_vault_path())).expanduser()
    if not password:
        return _json({"error": "主密码不能为空"}, 400)
    if len(password) < 6:
        return _json({"error": "主密码至少 6 位"}, 400)
    store = VaultStore(path, password)
    try:
        if store.exists():
            return _json({"error": "库已存在，请直接解锁"}, 400)
        store.init_new()
    except VaultError as exc:
        return _json({"error": str(exc)}, 400)
    save_local_env({"KEYVAULT_PATH": str(path), "KEYVAULT_PASSWORD": password})
    request.session["password"] = password
    request.session["path"] = str(path)
    return _json({"ok": True, "vault_path": str(path), "mcp": _mcp_snippet(path, password)})


async def api_unlock(request: Request) -> JSONResponse:
    body = await request.json()
    password = str(body.get("password") or "").strip()
    path = Path(str(body.get("path") or preferred_vault_path())).expanduser()
    if not password:
        return _json({"error": "请输入主密码"}, 400)
    store = VaultStore(path, password)
    try:
        if not store.exists():
            return _json({"error": "库不存在，请先创建", "need_init": True}, 404)
        store.load()
    except VaultError as exc:
        return _json({"error": str(exc)}, 400)
    save_local_env({"KEYVAULT_PATH": str(path), "KEYVAULT_PASSWORD": password})
    request.session["password"] = password
    request.session["path"] = str(path)
    due = store.due_reminders()
    return _json(
        {
            "ok": True,
            "vault_path": str(path),
            "count": len(store.list_all()),
            "reminders_due": [r.public_view() for r in due],
            "mcp": _mcp_snippet(path, password),
        }
    )


async def api_lock(request: Request) -> JSONResponse:
    request.session.clear()
    return _json({"ok": True})


async def api_status(request: Request) -> JSONResponse:
    try:
        store = _store_from_session(request)
        store.load()
        items = store.list_all()
        cats: dict[str, int] = {}
        for item in items:
            cats[item.category] = cats.get(item.category, 0) + 1
        due = store.due_reminders()
        return _json(
            {
                "unlocked": True,
                "vault_path": str(store.path),
                "count": len(items),
                "categories": cats,
                "reminders_due": [r.public_view() for r in due],
                "reminders_all": [r.public_view() for r in store.list_reminders(include_done=True)],
            }
        )
    except VaultError:
        return _json({"unlocked": False, "vault_path": str(preferred_vault_path())})


async def api_list(request: Request) -> JSONResponse:
    try:
        store = _store_from_session(request)
        q = request.query_params.get("q", "")
        category = request.query_params.get("category") or None
        items = store.search(query=q, category=category)
        return _json([i.public_view(include_secret=False) for i in items])
    except VaultError as exc:
        return _json({"error": str(exc)}, 401)


async def api_get(request: Request) -> JSONResponse:
    try:
        store = _store_from_session(request)
        show = request.query_params.get("show_secret", "0") in {"1", "true", "yes"}
        item = store.get(request.path_params["name_or_id"])
        return _json(item.public_view(include_secret=show))
    except VaultError as exc:
        return _json({"error": str(exc)}, 400)


async def api_create(request: Request) -> JSONResponse:
    try:
        store = _store_from_session(request)
        body = await request.json()
        fields = body.get("fields") or []
        entry = store.add_from_parts(
            name=str(body.get("name") or "").strip(),
            category=str(body.get("category") or "其他"),
            kind=str(body.get("kind") or "asset"),
            summary=str(body.get("summary") or ""),
            tags=body.get("tags") or [],
            expires_at=body.get("expires_at") or None,
            fields=fields,
        )
        return _json({"ok": True, "item": entry.public_view(include_secret=False)})
    except (VaultError, ValueError, KeyError) as exc:
        return _json({"error": str(exc)}, 400)


async def api_update(request: Request) -> JSONResponse:
    try:
        store = _store_from_session(request)
        body = await request.json()
        item = store.update(
            request.path_params["name_or_id"],
            name=body.get("name"),
            category=body.get("category"),
            kind=body.get("kind"),
            summary=body.get("summary"),
            tags=body.get("tags"),
            expires_at=body.get("expires_at"),
        )
        return _json({"ok": True, "item": item.public_view(include_secret=False)})
    except (VaultError, ValueError) as exc:
        return _json({"error": str(exc)}, 400)


async def api_delete(request: Request) -> JSONResponse:
    try:
        store = _store_from_session(request)
        item = store.delete(request.path_params["name_or_id"])
        return _json(
            {
                "ok": True,
                "deleted": item.name,
                "message": "已移入回收站，保留 30 天后自动彻底删除",
            }
        )
    except VaultError as exc:
        return _json({"error": str(exc)}, 400)


async def api_trash_list(request: Request) -> JSONResponse:
    try:
        store = _store_from_session(request)
        items = store.list_trash()
        return _json([i.public_view(include_secret=False) for i in items])
    except VaultError as exc:
        return _json({"error": str(exc)}, 401)


async def api_restore(request: Request) -> JSONResponse:
    try:
        store = _store_from_session(request)
        item = store.restore(request.path_params["name_or_id"])
        return _json({"ok": True, "item": item.public_view(include_secret=False)})
    except VaultError as exc:
        return _json({"error": str(exc)}, 400)


async def api_purge(request: Request) -> JSONResponse:
    try:
        store = _store_from_session(request)
        item = store.purge(request.path_params["name_or_id"])
        return _json({"ok": True, "purged": item.name})
    except VaultError as exc:
        return _json({"error": str(exc)}, 400)


async def api_upsert_field(request: Request) -> JSONResponse:
    try:
        store = _store_from_session(request)
        body = await request.json()
        item = store.upsert_field(
            request.path_params["name_or_id"],
            key=str(body.get("key") or ""),
            value=str(body.get("value") or ""),
            purpose=str(body.get("purpose") or ""),
            secret=body.get("secret"),
        )
        return _json({"ok": True, "item": item.public_view(include_secret=False)})
    except (VaultError, ValueError) as exc:
        return _json({"error": str(exc)}, 400)


async def api_remove_field(request: Request) -> JSONResponse:
    try:
        store = _store_from_session(request)
        item = store.remove_field(
            request.path_params["name_or_id"],
            request.path_params["field_key"],
        )
        return _json({"ok": True, "item": item.public_view(include_secret=False)})
    except VaultError as exc:
        return _json({"error": str(exc)}, 400)


async def api_mcp_config(request: Request) -> JSONResponse:
    path = Path(request.session.get("path") or preferred_vault_path())
    password = request.session.get("password") or os.environ.get("KEYVAULT_PASSWORD", "")
    if not password:
        return _json({"error": "请先解锁，才能生成 MCP 配置"}, 401)
    return _json(_mcp_snippet(path, password))


def _mcp_snippet(path: Path, password: str) -> dict[str, Any]:
    py = ROOT / ".venv" / "Scripts" / "python.exe"
    return {
        "mcpServers": {
            "keyvault": {
                "command": str(py),
                "args": ["-m", "keyvault.mcp_server"],
                "cwd": str(ROOT),
                "env": {
                    "KEYVAULT_PATH": str(path),
                    "KEYVAULT_PASSWORD": password,
                },
            }
        }
    }


async def api_reminders_list(request: Request) -> JSONResponse:
    try:
        store = _store_from_session(request)
        only_due = request.query_params.get("only_due", "0") in {"1", "true"}
        include_done = request.query_params.get("include_done", "1") in {"1", "true"}
        items = store.due_reminders() if only_due else store.list_reminders(include_done=include_done)
        return _json([r.public_view() for r in items])
    except VaultError as exc:
        return _json({"error": str(exc)}, 401)


async def api_reminders_create(request: Request) -> JSONResponse:
    try:
        store = _store_from_session(request)
        body = await request.json()
        item = store.add_reminder(
            title=str(body.get("title") or ""),
            due_at=str(body.get("due_at") or ""),
            notes=str(body.get("notes") or ""),
            remind_before_days=int(body.get("remind_before_days") or 3),
            repeat=str(body.get("repeat") or "once"),
        )
        return _json({"ok": True, "item": item.public_view()})
    except (VaultError, ValueError) as exc:
        return _json({"error": str(exc)}, 400)


async def api_reminders_complete(request: Request) -> JSONResponse:
    try:
        store = _store_from_session(request)
        body = await request.json()
        item = store.complete_reminder(
            request.path_params["id_or_title"],
            done=bool(body.get("done", True)),
        )
        return _json({"ok": True, "item": item.public_view()})
    except VaultError as exc:
        return _json({"error": str(exc)}, 400)


async def api_reminders_delete(request: Request) -> JSONResponse:
    try:
        store = _store_from_session(request)
        item = store.delete_reminder(request.path_params["id_or_title"])
        return _json({"ok": True, "deleted": item.title})
    except VaultError as exc:
        return _json({"error": str(exc)}, 400)


async def api_write_mcp(request: Request) -> JSONResponse:
    """写入用户 Cursor MCP 配置（合并 keyvault，不覆盖其它服务器）。"""
    try:
        store = _store_from_session(request)
    except VaultError as exc:
        return _json({"error": str(exc)}, 401)
    password = request.session["password"]
    snippet = _mcp_snippet(store.path, password)
    mcp_path = Path.home() / ".cursor" / "mcp.json"
    mcp_path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {}
    if mcp_path.is_file():
        try:
            existing = json.loads(mcp_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
    servers = existing.get("mcpServers") or {}
    if not isinstance(servers, dict):
        servers = {}
    servers["keyvault"] = snippet["mcpServers"]["keyvault"]
    existing["mcpServers"] = servers
    mcp_path.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return _json({"ok": True, "path": str(mcp_path), "config": existing})


async def api_export(request: Request) -> Response:
    """一键导出。
    query:
      format=md|json|xlsx|excel|encrypted
      include_secret=0|1  （仅 md/json/xlsx）
    """
    try:
        store = _store_from_session(request)
    except VaultError as exc:
        return _json({"error": str(exc)}, 401)

    fmt = (request.query_params.get("format") or "md").lower()
    if fmt == "excel":
        fmt = "xlsx"
    include_secret = request.query_params.get("include_secret", "1") in {"1", "true", "yes"}
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    downloads = Path.home() / "Downloads"
    downloads.mkdir(parents=True, exist_ok=True)

    if fmt == "encrypted":
        dest = downloads / f"keyvault-backup-{stamp}.kvault"
        store.export_encrypted(dest)
        return _json(
            {
                "ok": True,
                "format": "encrypted",
                "path": str(dest),
                "message": "已导出加密备份到下载文件夹（可用 import 恢复）",
            }
        )

    payload = build_classified_export(store, include_secret=include_secret)
    if fmt == "xlsx":
        filename = f"keyvault-分类导出-{stamp}.xlsx"
        body = to_excel_bytes(payload)
        saved = downloads / filename
        saved.write_bytes(body)
        return Response(
            content=body,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-Saved-Path": str(saved),
            },
        )

    if fmt == "json":
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        filename = f"keyvault-分类导出-{stamp}.json"
        media = "application/json; charset=utf-8"
    else:
        text = to_markdown(payload)
        filename = f"keyvault-分类导出-{stamp}.md"
        media = "text/markdown; charset=utf-8"

    saved = downloads / filename
    saved.write_text(text, encoding="utf-8")

    return Response(
        content=text.encode("utf-8"),
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Saved-Path": str(saved),
        },
    )


routes = [
    Route("/", index),
    Route("/api/bootstrap", api_bootstrap),
    Route("/api/init", api_init, methods=["POST"]),
    Route("/api/unlock", api_unlock, methods=["POST"]),
    Route("/api/lock", api_lock, methods=["POST"]),
    Route("/api/status", api_status),
    Route("/api/entries", api_list),
    Route("/api/entries", api_create, methods=["POST"]),
    Route("/api/entries/{name_or_id}", api_get),
    Route("/api/entries/{name_or_id}", api_update, methods=["PATCH"]),
    Route("/api/entries/{name_or_id}", api_delete, methods=["DELETE"]),
    Route("/api/entries/{name_or_id}/fields", api_upsert_field, methods=["POST"]),
    Route(
        "/api/entries/{name_or_id}/fields/{field_key}",
        api_remove_field,
        methods=["DELETE"],
    ),
    Route("/api/trash", api_trash_list),
    Route("/api/trash/{name_or_id}/restore", api_restore, methods=["POST"]),
    Route("/api/trash/{name_or_id}", api_purge, methods=["DELETE"]),
    Route("/api/mcp-config", api_mcp_config),
    Route("/api/write-mcp", api_write_mcp, methods=["POST"]),
    Route("/api/export", api_export),
    Route("/api/reminders", api_reminders_list),
    Route("/api/reminders", api_reminders_create, methods=["POST"]),
    Route("/api/reminders/{id_or_title}/complete", api_reminders_complete, methods=["POST"]),
    Route("/api/reminders/{id_or_title}", api_reminders_delete, methods=["DELETE"]),
    Mount("/static", app=StaticFiles(directory=str(WEB_DIR)), name="static"),
]

middleware = [
    Middleware(
        SessionMiddleware,
        secret_key=_session_secret(),
        session_cookie="keyvault_session",
        same_site="lax",
        https_only=False,
    )
]

app = Starlette(debug=False, routes=routes, middleware=middleware)


def main() -> None:
    apply_local_env()
    import uvicorn

    port = int(os.environ.get("KEYVAULT_UI_PORT", "8799"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
