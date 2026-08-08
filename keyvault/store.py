from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from keyvault.crypto import VaultCryptoError, decrypt_payload, encrypt_payload
from keyvault.models import Entry, FieldItem, Reminder, VaultData, parse_expiry, utc_now_iso


class VaultError(Exception):
    pass


def _parse_fields_input(fields: Any) -> list[FieldItem]:
    """支持 list[dict] / JSON 字符串。"""
    if fields is None or fields == "":
        return []
    if isinstance(fields, str):
        text = fields.strip()
        if not text:
            return []
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise VaultError(
                "fields 需要是 JSON 数组，例如："
                '[{"key":"Token","value":"xxx","purpose":"API调用","secret":true}]'
            ) from exc
    else:
        data = fields
    if not isinstance(data, list):
        raise VaultError("fields 必须是数组")
    out: list[FieldItem] = []
    for item in data:
        if not isinstance(item, dict):
            raise VaultError("fields 每一项必须是对象")
        out.append(FieldItem.from_dict(item))
    return out


class VaultStore:
    def __init__(self, path: Path, password: str):
        self.path = Path(path)
        self.password = password
        self._data: VaultData | None = None
        # 用于发现网盘同步带来的外部更新（另一台电脑改过）
        self._file_mtime_ns: int | None = None
        self._file_size: int | None = None

    def exists(self) -> bool:
        return self.path.is_file()

    def _snapshot_file(self) -> tuple[int, int] | None:
        if not self.exists():
            return None
        st = self.path.stat()
        return (st.st_mtime_ns, st.st_size)

    def _file_changed_on_disk(self) -> bool:
        snap = self._snapshot_file()
        if snap is None:
            return False
        if self._file_mtime_ns is None:
            return True
        return snap != (self._file_mtime_ns, self._file_size)

    def _remember_file(self) -> None:
        snap = self._snapshot_file()
        if snap is None:
            self._file_mtime_ns = None
            self._file_size = None
            return
        self._file_mtime_ns, self._file_size = snap

    def init_new(self) -> None:
        if self.exists():
            raise VaultError(f"密钥库已存在：{self.path}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data = VaultData()
        self.save()

    def load(self) -> VaultData:
        # 网盘同步后文件变了：丢掉内存缓存，读最新库
        if self._data is not None and self._file_changed_on_disk():
            self._data = None
        if self._data is not None:
            return self._data
        if not self.exists():
            raise VaultError(
                f"密钥库不存在：{self.path}。请先运行 keyvault init 创建。"
            )
        try:
            payload = decrypt_payload(self.password, self.path.read_bytes())
        except VaultCryptoError as exc:
            raise VaultError(str(exc)) from exc
        self._data = VaultData.from_dict(payload)
        self._remember_file()
        # 超过 30 天的回收站条目物理清除
        if self._purge_trash_locked(days=30):
            self.save()
        return self._data

    def _purge_trash_locked(self, days: int = 30) -> bool:
        """调用方需已 load；返回是否有删除发生。"""
        from datetime import datetime, timedelta, timezone

        data = self._data
        if data is None:
            return False
        now = datetime.now(timezone.utc)
        keep: list = []
        changed = False
        for item in data.entries:
            if not item.deleted_at:
                keep.append(item)
                continue
            try:
                deleted = datetime.fromisoformat(item.deleted_at.replace("Z", "+00:00"))
                if deleted.tzinfo is None:
                    deleted = deleted.replace(tzinfo=timezone.utc)
            except ValueError:
                keep.append(item)
                continue
            if now - deleted <= timedelta(days=days):
                keep.append(item)
            else:
                changed = True
        if changed:
            data.entries = keep
        return changed

    def save(self) -> None:
        data = self.load() if self._data is None else self._data
        data.version = 3
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        blob = encrypt_payload(self.password, data.to_dict())
        tmp.write_bytes(blob)
        tmp.replace(self.path)
        self._data = data
        self._remember_file()

    def reload(self) -> VaultData:
        self._data = None
        self._file_mtime_ns = None
        self._file_size = None
        return self.load()

    def list_all(self, include_deleted: bool = False) -> list[Entry]:
        items = list(self.load().entries)
        if include_deleted:
            return items
        return [e for e in items if not e.deleted_at]

    def list_trash(self) -> list[Entry]:
        items = [e for e in self.load().entries if e.deleted_at]
        items.sort(key=lambda e: e.deleted_at or "", reverse=True)
        return items

    def search(
        self,
        query: str = "",
        category: str | None = None,
        tag: str | None = None,
        kind: str | None = None,
        include_expired: bool = True,
        include_deleted: bool = False,
    ) -> list[Entry]:
        q = query.strip().lower()
        results: list[Entry] = []
        for item in self.list_all(include_deleted=include_deleted):
            if category and item.category != category:
                continue
            if tag and tag not in item.tags:
                continue
            if kind and item.kind != kind:
                continue
            if not include_expired and item.expiry_status() == "expired":
                continue
            if q and q not in item.search_text():
                continue
            results.append(item)
        results.sort(key=lambda c: c.name.lower())
        return results

    def get(self, name_or_id: str, include_deleted: bool = False) -> Entry:
        key = name_or_id.strip()
        items = self.list_all(include_deleted=include_deleted)
        for item in items:
            if item.id == key or item.name == key:
                return item
        matches = [
            item
            for item in items
            if key.lower() in item.name.lower() or item.id.startswith(key)
        ]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise VaultError(f"未找到条目：{name_or_id}")
        names = ", ".join(m.name for m in matches[:8])
        raise VaultError(f"匹配到多条，请写更精确的名称：{names}")

    def add(self, entry: Entry) -> Entry:
        data = self.load()
        for item in data.entries:
            if item.name == entry.name and not item.deleted_at:
                raise VaultError(f"名称已存在：{entry.name}")
        data.entries.append(entry)
        self.save()
        return entry

    def add_from_parts(
        self,
        name: str,
        category: str = "其他",
        kind: str = "asset",
        summary: str = "",
        tags: str | list[str] | None = None,
        expires_at: str | None = None,
        fields: Any = None,
        # 旧参数兼容
        secret: str | None = None,
        username: str = "",
        host: str = "",
        notes: str = "",
    ) -> Entry:
        field_items = _parse_fields_input(fields)
        if username:
            field_items.append(FieldItem(key="账号", value=username, purpose="登录账号"))
        if host:
            field_items.append(FieldItem(key="主机", value=host, purpose="主机/地址/IP"))
        if secret:
            field_items.append(
                FieldItem(key="密码", value=secret, purpose="主密码/密钥", secret=True)
            )
        if isinstance(tags, str):
            tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        else:
            tag_list = list(tags or [])
        entry = Entry(
            name=name.strip(),
            category=(category or "其他").strip() or "其他",
            kind=(kind or "asset").strip() or "asset",
            summary=(summary or notes or "").strip(),
            tags=tag_list,
            fields=field_items,
            expires_at=parse_expiry(expires_at),
        )
        return self.add(entry)

    def update(self, name_or_id: str, **fields: object) -> Entry:
        entry = self.get(name_or_id)
        meta_keys = {"name", "category", "kind", "summary", "tags", "notes", "expires_at"}
        for key, value in fields.items():
            if key not in meta_keys or value is None:
                continue
            if key == "tags":
                if isinstance(value, str):
                    value = [t.strip() for t in value.split(",") if t.strip()]
                entry.tags = list(value)  # type: ignore[arg-type]
            elif key == "expires_at":
                entry.expires_at = parse_expiry(str(value) if value != "" else None)
            elif key == "notes":
                entry.summary = str(value)
            elif key == "name":
                new_name = str(value).strip()
                if not new_name:
                    raise VaultError("名称不能为空")
                for item in self.load().entries:
                    if item.id != entry.id and item.name == new_name:
                        raise VaultError(f"名称已存在：{new_name}")
                entry.name = new_name
            else:
                setattr(entry, key, value)
        # 旧字段兼容：直接改 账号/主机/密码
        if fields.get("username") is not None and fields.get("username") != "":
            entry.upsert_field("账号", str(fields["username"]), purpose="登录账号")
        if fields.get("host") is not None and fields.get("host") != "":
            entry.upsert_field("主机", str(fields["host"]), purpose="主机/地址/IP")
        if fields.get("secret") is not None and fields.get("secret") != "":
            entry.upsert_field("密码", str(fields["secret"]), purpose="主密码/密钥", secret=True)
        entry.updated_at = utc_now_iso()
        self.save()
        return entry

    def upsert_field(
        self,
        name_or_id: str,
        key: str,
        value: str,
        purpose: str = "",
        secret: bool | None = None,
    ) -> Entry:
        entry = self.get(name_or_id)
        try:
            entry.upsert_field(key, value, purpose=purpose, secret=secret)
        except ValueError as exc:
            raise VaultError(str(exc)) from exc
        self.save()
        return entry

    def remove_field(self, name_or_id: str, field_key_or_id: str) -> Entry:
        entry = self.get(name_or_id)
        try:
            entry.remove_field(field_key_or_id)
        except ValueError as exc:
            raise VaultError(str(exc)) from exc
        self.save()
        return entry

    def delete(self, name_or_id: str) -> Entry:
        """软删除：进入回收站，默认保留 30 天。"""
        entry = self.get(name_or_id, include_deleted=False)
        entry.deleted_at = utc_now_iso()
        entry.updated_at = utc_now_iso()
        self.save()
        return entry

    def restore(self, name_or_id: str) -> Entry:
        entry = self.get(name_or_id, include_deleted=True)
        if not entry.deleted_at:
            raise VaultError("该条目不在回收站中")
        # 恢复时若有同名未删除条目，自动改名
        active_names = {e.name for e in self.list_all(include_deleted=False) if e.id != entry.id}
        if entry.name in active_names:
            entry.name = f"{entry.name}-恢复"
        entry.deleted_at = None
        entry.updated_at = utc_now_iso()
        self.save()
        return entry

    def purge(self, name_or_id: str) -> Entry:
        """从回收站彻底删除。"""
        entry = self.get(name_or_id, include_deleted=True)
        if not entry.deleted_at:
            raise VaultError("只能彻底删除回收站中的条目；请先删除到回收站")
        data = self.load()
        data.entries = [c for c in data.entries if c.id != entry.id]
        self.save()
        return entry

    def expiring(self, within_days: int = 14) -> list[Entry]:
        out: list[Entry] = []
        for item in self.list_all(include_deleted=False):
            days = item.days_until_expiry()
            if days is None:
                continue
            if days <= within_days:
                out.append(item)
        out.sort(key=lambda c: c.expires_at or "9999-99-99")
        return out

    def list_reminders(self, include_done: bool = False) -> list[Reminder]:
        items = list(self.load().reminders)
        if not include_done:
            items = [r for r in items if not r.done]
        items.sort(key=lambda r: (r.done, r.due_at, r.title))
        return items

    def due_reminders(self) -> list[Reminder]:
        """需要提醒的：未完成，且已到提前天数窗口（含过期）。"""
        items = [r for r in self.list_reminders(include_done=False) if r.should_alert()]
        items.sort(key=lambda r: (r.days_until_due(), r.due_at))
        return items

    def get_reminder(self, id_or_title: str) -> Reminder:
        key = id_or_title.strip()
        for item in self.load().reminders:
            if item.id == key or item.title == key:
                return item
        matches = [r for r in self.load().reminders if key.lower() in r.title.lower()]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise VaultError(f"未找到提醒：{id_or_title}")
        raise VaultError("匹配到多条提醒，请用更精确的标题或 id")

    def add_reminder(
        self,
        title: str,
        due_at: str,
        notes: str = "",
        remind_before_days: int = 3,
        repeat: str = "once",
    ) -> Reminder:
        title = title.strip()
        if not title:
            raise VaultError("提醒标题不能为空")
        due = parse_expiry(due_at)
        if not due:
            raise VaultError("due_at 需要 YYYY-MM-DD")
        repeat = (repeat or "once").strip().lower()
        if repeat not in Reminder.REPEAT_LABELS:
            raise VaultError("周期仅支持：once/weekly/monthly/quarterly/yearly")
        reminder = Reminder(
            title=title,
            due_at=due,
            notes=notes.strip(),
            remind_before_days=max(0, int(remind_before_days)),
            repeat=repeat,
        )
        self.load().reminders.append(reminder)
        self.save()
        return reminder

    def update_reminder(self, id_or_title: str, **fields: object) -> Reminder:
        reminder = self.get_reminder(id_or_title)
        if fields.get("title") is not None and str(fields["title"]).strip():
            reminder.title = str(fields["title"]).strip()
        if fields.get("notes") is not None:
            reminder.notes = str(fields["notes"])
        if fields.get("due_at") is not None:
            due = parse_expiry(str(fields["due_at"]) if fields["due_at"] != "" else None)
            if not due:
                raise VaultError("due_at 需要 YYYY-MM-DD")
            reminder.due_at = due
        if fields.get("remind_before_days") is not None:
            reminder.remind_before_days = max(0, int(fields["remind_before_days"]))  # type: ignore[arg-type]
        if fields.get("repeat") is not None:
            repeat = str(fields["repeat"]).strip().lower()
            if repeat not in Reminder.REPEAT_LABELS:
                raise VaultError("周期仅支持：once/weekly/monthly/quarterly/yearly")
            reminder.repeat = repeat
        if fields.get("done") is not None:
            reminder.done = bool(fields["done"])
        reminder.updated_at = utc_now_iso()
        self.save()
        return reminder

    def complete_reminder(self, id_or_title: str, done: bool = True) -> Reminder:
        """完成提醒：仅一次则标记完成；周期性则自动滚到下一期。"""
        reminder = self.get_reminder(id_or_title)
        if not done:
            return self.update_reminder(id_or_title, done=False)
        if reminder.repeat != "once":
            nxt = reminder.next_due_after()
            if nxt:
                # 若已严重过期，可连跳多期直到未来
                from datetime import date as date_cls

                guard = 0
                while nxt and date_cls.fromisoformat(nxt) <= date_cls.today() and guard < 48:
                    reminder.due_at = nxt
                    nxt = reminder.next_due_after()
                    guard += 1
                if nxt:
                    reminder.due_at = nxt
                reminder.done = False
                reminder.updated_at = utc_now_iso()
                self.save()
                return reminder
        return self.update_reminder(id_or_title, done=True)

    def delete_reminder(self, id_or_title: str) -> Reminder:
        reminder = self.get_reminder(id_or_title)
        data = self.load()
        data.reminders = [r for r in data.reminders if r.id != reminder.id]
        self.save()
        return reminder

    def export_encrypted(self, dest: Path) -> Path:
        if not self.exists():
            raise VaultError("密钥库不存在，无法导出")
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.path, dest)
        return dest

    def import_encrypted(self, src: Path, overwrite: bool = False) -> None:
        src = Path(src)
        if not src.is_file():
            raise VaultError(f"导入文件不存在：{src}")
        try:
            decrypt_payload(self.password, src.read_bytes())
        except VaultCryptoError as exc:
            raise VaultError(
                f"无法用当前主密码打开导入文件：{exc}。"
                "多机同步时，各台电脑必须使用同一个主密码。"
            ) from exc
        if self.exists() and not overwrite:
            raise VaultError("本地已有密钥库。若确认覆盖，请加 --overwrite")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.exists():
            backup = self.path.with_suffix(self.path.suffix + ".bak")
            shutil.copy2(self.path, backup)
        shutil.copy2(src, self.path)
        self._data = None
        self.load()

    def change_password(self, new_password: str) -> None:
        if not new_password:
            raise VaultError("新主密码不能为空")
        data = self.load()
        self.password = new_password
        self._data = data
        self.save()


def summarize_expiry(items: Iterable[Entry], today: date | None = None) -> dict[str, int]:
    today = today or date.today()
    summary = {"total": 0, "expired": 0, "expiring_soon": 0, "ok": 0, "none": 0}
    for item in items:
        summary["total"] += 1
        status = item.expiry_status()
        summary[status] = summary.get(status, 0) + 1
        _ = today
    return summary
