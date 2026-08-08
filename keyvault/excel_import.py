from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from keyvault.models import Entry, FieldItem
from keyvault.store import VaultError, VaultStore

SECRET_HINT = re.compile(
    r"(password|passwd|pwd|密码|secret|token|密钥|key|smtp|accesskey|private)",
    re.I,
)


def _s(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _is_secret_key(key: str) -> bool:
    return bool(SECRET_HINT.search(key or ""))


def _field(key: str, value: str, purpose: str = "", secret: bool | None = None) -> FieldItem | None:
    key = _s(key)
    value = _s(value)
    if not key or not value or value in {"—", "-", "/"}:
        return None
    return FieldItem(
        key=key[:80],
        value=value,
        purpose=_s(purpose),
        secret=_is_secret_key(key) if secret is None else secret,
    )


def _unique_name(store: VaultStore, base: str) -> str:
    name = re.sub(r"\s+", " ", base).strip(" -_") or "未命名"
    existing = {e.name for e in store.list_all()}
    if name not in existing:
        return name
    i = 2
    while f"{name}-{i}" in existing:
        i += 1
    return f"{name}-{i}"


def _add(store: VaultStore, entry: Entry) -> str:
    entry.name = _unique_name(store, entry.name)
    # 去重空字段
    cleaned: list[FieldItem] = []
    seen = set()
    for f in entry.fields:
        if not f.key or not f.value:
            continue
        k = f.key.lower()
        if k in seen:
            f.key = f"{f.key}-额外"
        seen.add(f.key.lower())
        cleaned.append(f)
    entry.fields = cleaned
    store.add(entry)
    return entry.name


def _looks_header(row: tuple[Any, ...], *keywords: str) -> bool:
    text = " ".join(_s(x) for x in row)
    return all(k in text for k in keywords)


def import_kv_sheet(store: VaultStore, ws, category: str, entry_name: str) -> list[str]:
    fields: list[FieldItem] = []
    for row in ws.iter_rows(values_only=True):
        a, b = _s(row[0] if len(row) > 0 else None), _s(row[1] if len(row) > 1 else None)
        c = _s(row[2] if len(row) > 2 else None)
        d = _s(row[3] if len(row) > 3 else None)
        # 杂记这类：第一列空，键在 B、值在 C
        if not a and b and c:
            a, b, c = b, c, d
        if not a and not b:
            continue
        # 分区标题
        if a and not b and ("、" in a or a.endswith("：") or a.endswith(":")):
            continue
        if a in {"项目", "平台", "邮箱", "服务", "客户端", "序号", "列1"}:
            continue
        key = a or "备注"
        if b:
            f = _field(key, b, purpose=c or category)
            if f:
                fields.append(f)
        if c and a and b and c not in {b, a}:
            # 英文/补充列
            f2 = _field(f"{key}-补充", c, purpose=category)
            if f2:
                fields.append(f2)
    if not fields:
        return []
    name = _add(
        store,
        Entry(name=entry_name, category=category, kind="note", summary=f"来自 Excel「{category}」", fields=fields),
    )
    return [name]


def import_platform_password_sheet(store: VaultStore, ws, category: str) -> list[str]:
    names: list[str] = []
    header_seen = False
    for row in ws.iter_rows(values_only=True):
        vals = [_s(x) for x in row]
        if not any(vals):
            continue
        if _looks_header(tuple(vals), "平台") and ("账号" in "".join(vals) or "密码" in "".join(vals)):
            header_seen = True
            continue
        if not header_seen and not vals[0]:
            continue
        platform = vals[0]
        if not platform or platform.startswith("五、") or platform.startswith("开发者"):
            if "开放平台" in platform or "开发者" in platform:
                header_seen = False
            continue
        if platform in {"平台"}:
            header_seen = True
            continue
        account = vals[1] if len(vals) > 1 else ""
        password = vals[2] if len(vals) > 2 else ""
        if not account and not password:
            continue
        fields = []
        f1 = _field("账号", account, "登录账号")
        f2 = _field("密码", password, "登录密码", secret=True)
        if f1:
            fields.append(f1)
        if f2:
            fields.append(f2)
        # 纯说明行（商户号等）
        if account and (not password or password in {"—", "-"}):
            fields = [_field(platform, account, category) or FieldItem(key=platform, value=account)]
            entry = Entry(
                name=f"{category}-{platform}"[:80],
                category=category,
                kind="note",
                summary=account,
                fields=fields,
            )
        else:
            entry = Entry(
                name=f"{category}-{platform.split()[0]}"[:80],
                category=category,
                kind="account",
                summary=platform,
                fields=fields,
            )
        names.append(_add(store, entry))
    return names


def import_site_table(store: VaultStore, ws, category: str, server_mode: bool = False) -> list[str]:
    names: list[str] = []
    headers: list[str] = []
    for row in ws.iter_rows(values_only=True):
        vals = [_s(x) for x in row]
        if not any(vals):
            continue
        joined = "".join(vals)
        if "站点" in joined and ("账号" in joined or "密码" in joined or "域名" in joined):
            headers = vals
            continue
        # 杂项链接行（无站点名，备注里是 vless://）
        if server_mode and (not vals[1] if len(vals) > 1 else True):
            note = " ".join(v for v in vals if v)
            if note.startswith("vless://") or note.startswith("hy2://") or "订阅" in note:
                fields = [_field("配置", note, "代理/订阅", secret=True)]
                if fields:
                    names.append(
                        _add(
                            store,
                            Entry(
                                name=_unique_name(store, f"{category}-代理配置"),
                                category=category,
                                kind="note",
                                summary="从服务器表附加行导入",
                                fields=fields,
                            ),
                        )
                    )
            continue
        if not headers:
            continue

        def col(name: str) -> str:
            for i, h in enumerate(headers):
                if name in h and i < len(vals):
                    return vals[i]
            return ""

        if server_mode:
            site = col("站点") or (vals[1] if len(vals) > 1 else "")
            remark = col("备注") or (vals[2] if len(vals) > 2 else "")
            if not site and not remark:
                continue
            title = f"{site}-{remark}" if remark else site
            fields = []
            for key, label in [
                ("IP", "IP"),
                ("账号", "账号"),
                ("密码", "密码"),
                ("记录1", "记录1"),
                ("记录2", "记录2"),
                ("记录3", "记录3"),
                ("记录4", "记录4"),
            ]:
                val = col(key)
                f = _field(label if label != "IP" else "主机", val, purpose=remark or site, secret=_is_secret_key(label) or "Secret" in val or "Key" in val)
                if f:
                    # 密码列强制敏感
                    if label == "密码":
                        f.secret = True
                    fields.append(f)
            names.append(
                _add(
                    store,
                    Entry(
                        name=title[:80],
                        category=category,
                        kind="server",
                        summary=remark or site,
                        fields=fields,
                        tags=[site] if site else [],
                    ),
                )
            )
            continue

        # 域名表
        if "域名" in "".join(headers):
            domain = col("域名") or (vals[1] if len(vals) > 1 else "")
            if not domain:
                continue
            fields = []
            for key in headers:
                if not key or key in {"序号"}:
                    continue
                val = col(key)
                if key == "域名":
                    continue
                f = _field(key, val, purpose=domain)
                if f:
                    fields.append(f)
            names.append(
                _add(
                    store,
                    Entry(
                        name=f"域名-{domain}"[:80],
                        category=category,
                        kind="asset",
                        summary=col("说明") or domain,
                        fields=fields + ([_field("域名", domain, "域名")] if domain else []),
                    ),
                )
            )
            continue

        # 普通网站表
        site = col("站点名称") or col("站点") or (vals[1] if len(vals) > 1 else "")
        if not site:
            continue
        remark = col("用户名/说明") or col("说明") or ""
        title = f"{site}-{remark}" if remark else site
        fields = []
        mapping = [
            ("账号", "账号", "登录账号"),
            ("密码", "密码", "登录密码"),
            ("记录1", "记录1", remark or "附加记录"),
            ("记录2", "记录2", remark or "附加记录"),
            ("记录3", "记录3", remark or "附加记录"),
            ("用户名/说明", "说明", "用途说明"),
        ]
        for h, key, purpose in mapping:
            val = col(h)
            if h == "用户名/说明" and remark:
                val = remark
            f = _field(key, val, purpose=purpose)
            if f:
                if key == "密码" or _is_secret_key(key) or _is_secret_key(val[:20] if val else ""):
                    if key == "密码" or "token" in val.lower() or "key:" in val.lower() or "密钥" in val:
                        f.secret = True
                if key == "密码":
                    f.secret = True
                fields.append(f)
        names.append(
            _add(
                store,
                Entry(
                    name=title[:80],
                    category=category,
                    kind="account",
                    summary=remark or site,
                    fields=fields,
                    tags=[site],
                ),
            )
        )
    return names


def import_workbook(store: VaultStore, path: Path) -> dict[str, list[str]]:
    wb = load_workbook(path, data_only=True)
    result: dict[str, list[str]] = {}
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        cat = sheet_name.replace("（轻语知交）", "").strip()
        if sheet_name.startswith("企业基础"):
            result[sheet_name] = import_kv_sheet(store, ws, "企业基础", "企业基础-总览")
        elif "开放平台" in sheet_name or "支付" in sheet_name:
            result[sheet_name] = import_platform_password_sheet(store, ws, cat)
        elif "服务器" in sheet_name:
            result[sheet_name] = import_site_table(store, ws, cat, server_mode=True)
        elif "域名" in sheet_name or "DNS" in sheet_name:
            result[sheet_name] = import_site_table(store, ws, cat, server_mode=False)
        elif "Whisperkin" in sheet_name:
            # 拆成几个逻辑条目更清晰
            result[sheet_name] = import_whisperkin(store, ws)
        elif "杂记" in sheet_name:
            result[sheet_name] = import_kv_sheet(store, ws, "杂记", "杂记-总览")
        elif "国外" in sheet_name or "国内" in sheet_name:
            result[sheet_name] = import_site_table(store, ws, cat, server_mode=False)
        else:
            result[sheet_name] = import_kv_sheet(store, ws, cat or "其他", f"{cat}-总览")
    return result


def import_whisperkin(store: VaultStore, ws) -> list[str]:
    names: list[str] = []
    buckets: dict[str, list[FieldItem]] = {
        "Whisperkin-Apple": [],
        "Whisperkin-GoogleOAuth": [],
        "Whisperkin-其他服务": [],
        "Whisperkin-业务邮箱": [],
    }
    mode = "Whisperkin-Apple"
    for row in ws.iter_rows(values_only=True):
        vals = [_s(x) for x in row]
        # openpyxl 该表常见空第一列
        a = vals[1] if len(vals) > 1 else vals[0]
        b = vals[2] if len(vals) > 2 else (vals[1] if len(vals) > 1 else "")
        if len(vals) > 1 and vals[0] and not vals[1]:
            a, b = vals[0], vals[1] if len(vals) > 1 else ""
        if not a and not b:
            continue
        if a in {"Google OAuth", "其他服务", "whisperkin.com 业务邮箱"} or "业务邮箱" in a:
            if "Google" in a:
                mode = "Whisperkin-GoogleOAuth"
            elif "其他" in a:
                mode = "Whisperkin-其他服务"
            elif "邮箱" in a:
                mode = "Whisperkin-业务邮箱"
            continue
        if a in {"客户端", "服务", "邮箱"}:
            continue
        f = _field(a, b, purpose=mode)
        if f:
            if "密钥" in a or "Secret" in a or "Key" in a:
                f.secret = True
            buckets[mode].append(f)
    for name, fields in buckets.items():
        if not fields:
            continue
        names.append(
            _add(
                store,
                Entry(
                    name=name,
                    category="Whisperkin",
                    kind="asset",
                    summary="来自 Excel Whisperkin 表",
                    fields=fields,
                ),
            )
        )
    return names


def main() -> None:
    import argparse
    import os

    from keyvault.local_settings import apply_local_env, preferred_vault_path

    apply_local_env()
    parser = argparse.ArgumentParser(description="从 Excel 导入 KeyVault")
    parser.add_argument("excel", type=Path)
    parser.add_argument("--password", default=os.environ.get("KEYVAULT_PASSWORD", ""))
    parser.add_argument("--path", default="")
    args = parser.parse_args()
    password = args.password
    if not password:
        raise SystemExit("请设置 KEYVAULT_PASSWORD 或 --password")
    vault = Path(args.path).expanduser() if args.path else preferred_vault_path()
    store = VaultStore(vault, password)
    if not store.exists():
        store.init_new()
    else:
        store.load()
    result = import_workbook(store, args.excel)
    total = sum(len(v) for v in result.values())
    print(f"导入完成：共 {total} 条 → {vault}")
    for sheet, names in result.items():
        print(f"- {sheet}: {len(names)} 条")
        for n in names[:12]:
            print(f"  · {n}")
        if len(names) > 12:
            print(f"  · ... 另有 {len(names) - 12} 条")


if __name__ == "__main__":
    main()
