from __future__ import annotations

import json
import os
from getpass import getpass
from pathlib import Path

import click

from keyvault.config import ENV_MASTER_PASSWORD, ENV_VAULT_PATH, get_master_password, get_vault_path
from keyvault.models import SUGGESTED_CATEGORIES
from keyvault.store import VaultError, VaultStore, summarize_expiry


def _resolve_password(prompt_create: bool = False) -> str:
    env = get_master_password()
    if env:
        return env
    if prompt_create:
        p1 = getpass("设置主密码：")
        p2 = getpass("再输入一次：")
        if not p1:
            raise click.ClickException("主密码不能为空")
        if p1 != p2:
            raise click.ClickException("两次主密码不一致")
        return p1
    password = getpass("主密码：")
    if not password:
        raise click.ClickException("主密码不能为空")
    return password


def _store(password: str | None = None, create: bool = False) -> VaultStore:
    pwd = password or _resolve_password(prompt_create=create)
    return VaultStore(get_vault_path(), pwd)


@click.group()
@click.version_option(package_name=None, version="0.2.0")
def main() -> None:
    """KeyVault：弹性字段记忆库（密码/Token/备注都能记，字段名可自由增减）。"""


@main.command("init")
@click.option("--path", "vault_path", type=click.Path(), default=None, help="库文件路径")
def init_cmd(vault_path: str | None) -> None:
    """创建空记忆库。"""
    if vault_path:
        os.environ[ENV_VAULT_PATH] = vault_path
    store = _store(create=True)
    try:
        store.init_new()
    except VaultError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"已创建记忆库：{store.path}")
    click.echo("建议分类：" + " / ".join(SUGGESTED_CATEGORIES))
    click.echo("字段是弹性的：Token、KEY、AccessKey、用途说明都可随时加。")


@main.command("add")
@click.option("--name", required=True, help="条目标题，需唯一，如 示例云-控制台")
@click.option("--category", default="其他", show_default=True, help="分类，可自定义")
@click.option("--kind", default="asset", show_default=True, help="asset/account/server/note/api/email...")
@click.option("--summary", default="", help="这条整体干什么用")
@click.option("--tags", default="", help="逗号分隔标签")
@click.option("--expires-at", default=None, help="过期日 YYYY-MM-DD")
@click.option(
    "--field",
    "fields",
    multiple=True,
    help='弹性字段，格式 key=value 或 key=value|用途 或 key=value|用途|secret',
)
@click.option("--fields-json", default=None, help="也可用 JSON 数组一次传入多个字段")
@click.option("--secret", default=None, help="快捷：写入名为「密码」的敏感字段")
@click.option("--username", default="", help="快捷：写入「账号」字段")
@click.option("--host", default="", help="快捷：写入「主机」字段")
def add_cmd(
    name: str,
    category: str,
    kind: str,
    summary: str,
    tags: str,
    expires_at: str | None,
    fields: tuple[str, ...],
    fields_json: str | None,
    secret: str | None,
    username: str,
    host: str,
) -> None:
    """新增一条资产（可带任意字段）。"""
    parsed = []
    if fields_json:
        try:
            parsed = json.loads(fields_json)
        except json.JSONDecodeError as exc:
            raise click.ClickException(f"fields-json 不是合法 JSON：{exc}") from exc
    for raw in fields:
        parsed.append(_parse_field_arg(raw))

    try:
        store = _store()
        store.load()
        entry = store.add_from_parts(
            name=name,
            category=category,
            kind=kind,
            summary=summary,
            tags=tags,
            expires_at=expires_at,
            fields=parsed,
            secret=secret,
            username=username,
            host=host,
        )
    except (VaultError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"已添加：{entry.name}（分类={entry.category}，字段数={len(entry.fields)}）")


def _parse_field_arg(raw: str) -> dict:
    """key=value | key=value|purpose | key=value|purpose|secret"""
    if "=" not in raw:
        raise click.ClickException(f"字段格式不对：{raw}，应为 key=value|用途|secret")
    key, rest = raw.split("=", 1)
    parts = rest.split("|")
    value = parts[0]
    purpose = parts[1] if len(parts) > 1 else ""
    secret_flag = False
    if len(parts) > 2:
        secret_flag = parts[2].strip().lower() in {"1", "true", "yes", "secret", "敏感"}
    return {"key": key.strip(), "value": value, "purpose": purpose, "secret": secret_flag}


@main.command("field-set")
@click.argument("name_or_id")
@click.option("--key", required=True, help="字段名，可任意：Token/KEY/桶名…")
@click.option("--value", required=True, help="字段值")
@click.option("--purpose", default="", help="这个字段干什么用")
@click.option("--secret", is_flag=True, help="标记为敏感（列表默认隐藏）")
def field_set_cmd(name_or_id: str, key: str, value: str, purpose: str, secret: bool) -> None:
    """给已有条目新增/更新一个弹性字段。"""
    try:
        entry = _store().upsert_field(
            name_or_id, key=key, value=value, purpose=purpose, secret=secret or None
        )
    except VaultError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"已写入字段 {key} → 条目 {entry.name}")


@main.command("field-rm")
@click.argument("name_or_id")
@click.argument("field_key")
def field_rm_cmd(name_or_id: str, field_key: str) -> None:
    """删除某个弹性字段。"""
    try:
        entry = _store().remove_field(name_or_id, field_key)
    except VaultError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"已删除字段 {field_key} ← 条目 {entry.name}")


@main.command("list")
@click.option("--query", default="", help="搜索名称/字段名/用途/值")
@click.option("--category", default=None)
@click.option("--tag", default=None)
@click.option("--json-out", is_flag=True)
def list_cmd(query: str, category: str | None, tag: str | None, json_out: bool) -> None:
    """列出条目（敏感值默认隐藏）。"""
    try:
        items = _store().search(query=query, category=category, tag=tag)
    except VaultError as exc:
        raise click.ClickException(str(exc)) from exc
    views = [i.public_view(include_secret=False) for i in items]
    if json_out:
        click.echo(json.dumps(views, ensure_ascii=False, indent=2))
        return
    if not views:
        click.echo("（空）")
        return
    for v in views:
        exp = v["expires_at"] or "无过期"
        status = v["expiry_status"]
        mark = {"expired": "[已过期]", "expiring_soon": "[即将过期]"}.get(status, "")
        keys = ", ".join(f["key"] for f in v["fields"]) or "无字段"
        click.echo(
            f"- {v['name']}  [{v['category']}/{v['kind']}]  "
            f"字段:{keys}  过期:{exp} {mark}"
        )
        if v.get("summary"):
            click.echo(f"  用途: {v['summary']}")


@main.command("get")
@click.argument("name_or_id")
@click.option("--show-secret", is_flag=True, help="显示敏感字段明文")
@click.option("--json-out", is_flag=True)
def get_cmd(name_or_id: str, show_secret: bool, json_out: bool) -> None:
    """查看一条详情。"""
    try:
        item = _store().get(name_or_id)
    except VaultError as exc:
        raise click.ClickException(str(exc)) from exc
    view = item.public_view(include_secret=show_secret)
    if json_out:
        click.echo(json.dumps(view, ensure_ascii=False, indent=2))
        return
    click.echo(f"name: {view['name']}")
    click.echo(f"category: {view['category']}")
    click.echo(f"kind: {view['kind']}")
    click.echo(f"summary: {view['summary']}")
    click.echo(f"tags: {view['tags']}")
    click.echo(f"expires_at: {view['expires_at']} ({view['expiry_status']})")
    click.echo("fields:")
    for f in view["fields"]:
        click.echo(
            f"  - {f['key']}: {f['value']}"
            + (f"  // {f['purpose']}" if f.get("purpose") else "")
            + ("  [敏感]" if f.get("secret") else "")
        )


@main.command("update")
@click.argument("name_or_id")
@click.option("--name", default=None)
@click.option("--category", default=None)
@click.option("--kind", default=None)
@click.option("--summary", default=None)
@click.option("--tags", default=None)
@click.option("--expires-at", default=None, help="YYYY-MM-DD；空字符串清除")
def update_cmd(
    name_or_id: str,
    name: str | None,
    category: str | None,
    kind: str | None,
    summary: str | None,
    tags: str | None,
    expires_at: str | None,
) -> None:
    """更新条目元信息。改具体字段请用 field-set。"""
    try:
        item = _store().update(
            name_or_id,
            name=name,
            category=category,
            kind=kind,
            summary=summary,
            tags=tags,
            expires_at=expires_at,
        )
    except (VaultError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"已更新：{item.name}")


@main.command("delete")
@click.argument("name_or_id")
@click.confirmation_option(prompt="确认删除该条目？")
def delete_cmd(name_or_id: str) -> None:
    """删除一整条。"""
    try:
        item = _store().delete(name_or_id)
    except VaultError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"已删除：{item.name}")


@main.command("expiring")
@click.option("--within-days", default=14, show_default=True, type=int)
@click.option("--json-out", is_flag=True)
def expiring_cmd(within_days: int, json_out: bool) -> None:
    """查看已过期 / 即将过期。"""
    try:
        store = _store()
        all_items = store.list_all()
        items = store.expiring(within_days=within_days)
        summary = summarize_expiry(all_items)
        due_soon = sum(
            1
            for i in all_items
            if (d := i.days_until_expiry()) is not None and 0 <= d <= within_days
        )
    except VaultError as exc:
        raise click.ClickException(str(exc)) from exc
    views = [i.public_view(include_secret=False) for i in items]
    if json_out:
        click.echo(
            json.dumps(
                {
                    "summary": summary,
                    "due_within_days": due_soon,
                    "within_days": within_days,
                    "items": views,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    click.echo(
        f"统计：共 {summary['total']}，已过期 {summary['expired']}，"
        f"{within_days} 天内到期 {due_soon}，无过期日 {summary['none']}"
    )
    for v in views:
        click.echo(
            f"- {v['name']}: {v['expires_at']} ({v['expiry_status']}, "
            f"剩余 {v['days_until_expiry']} 天)"
        )


@main.command("export")
@click.argument("dest", type=click.Path())
def export_cmd(dest: str) -> None:
    """导出加密库文件。"""
    try:
        path = _store().export_encrypted(Path(dest))
    except VaultError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"已导出：{path}")


@main.command("import")
@click.argument("src", type=click.Path(exists=True))
@click.option("--overwrite", is_flag=True)
def import_cmd(src: str, overwrite: bool) -> None:
    """导入加密库文件。"""
    try:
        store = _store()
        store.import_encrypted(Path(src), overwrite=overwrite)
    except VaultError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"已导入到：{store.path}")


@main.command("path")
def path_cmd() -> None:
    """显示当前库路径。"""
    click.echo(f"KEYVAULT_PATH = {os.environ.get(ENV_VAULT_PATH) or '(未设置，用默认)'}")
    click.echo(f"实际路径 = {get_vault_path()}")
    click.echo(
        f"KEYVAULT_PASSWORD = {'已设置' if get_master_password() else '未设置（命令行会提示输入）'}"
    )


@main.command("change-password")
def change_password_cmd() -> None:
    """修改主密码。"""
    old = _resolve_password(prompt_create=False)
    store = VaultStore(get_vault_path(), old)
    try:
        store.load()
    except VaultError as exc:
        raise click.ClickException(str(exc)) from exc
    new = _resolve_password(prompt_create=True)
    try:
        store.change_password(new)
    except VaultError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo("主密码已更新。")


@main.command("categories")
def categories_cmd() -> None:
    """显示建议分类（可自由新增，不强制）。"""
    for c in SUGGESTED_CATEGORIES:
        click.echo(f"- {c}")


if __name__ == "__main__":
    main()
