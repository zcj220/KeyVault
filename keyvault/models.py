from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import uuid4
import calendar

# 建议分类（可自由新增，不强制）
SUGGESTED_CATEGORIES = [
    "企业基础",
    "开放平台支付",
    "国外网站",
    "国内网站",
    "服务器及数据库",
    "域名DNS邮件",
    "Whisperkin",
    "杂记",
    "其他",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_expiry(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) == 10:
        date.fromisoformat(text)
        return text
    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return dt.date().isoformat()


def _parse_tags(tags: Any) -> list[str]:
    if tags is None:
        return []
    if isinstance(tags, str):
        return [t.strip() for t in tags.split(",") if t.strip()]
    return [str(t).strip() for t in tags if str(t).strip()]


def _looks_secret_key(key: str) -> bool:
    k = key.lower()
    keywords = [
        "password",
        "passwd",
        "pwd",
        "密码",
        "secret",
        "token",
        "密钥",
        "key",
        "accesskey",
        "secretkey",
        "smtp",
        "private",
    ]
    return any(x in k for x in keywords)


@dataclass
class FieldItem:
    """弹性字段：名字随便起（Token / KEY / AccessKey…），可带用途说明。"""

    key: str
    value: str
    purpose: str = ""
    secret: bool = False
    id: str = field(default_factory=lambda: uuid4().hex)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FieldItem":
        key = str(data.get("key") or data.get("name") or "").strip()
        if not key:
            raise ValueError("字段名 key 不能为空")
        secret_raw = data.get("secret")
        if secret_raw is None:
            secret = _looks_secret_key(key)
        else:
            secret = bool(secret_raw)
        return cls(
            id=str(data.get("id") or uuid4().hex),
            key=key,
            value=str(data.get("value") if data.get("value") is not None else ""),
            purpose=str(data.get("purpose") or data.get("用途") or ""),
            secret=secret,
        )

    def public_view(self, include_secret: bool = False) -> dict[str, Any]:
        view = {
            "id": self.id,
            "key": self.key,
            "purpose": self.purpose,
            "secret": self.secret,
        }
        if self.secret and not include_secret:
            view["value"] = "***"
            view["value_hidden"] = True
        else:
            view["value"] = self.value
            view["value_hidden"] = False
        return view


@dataclass
class Entry:
    """一条资产/记忆：固定少量元数据 + 任意数量弹性字段。"""

    name: str
    id: str = field(default_factory=lambda: uuid4().hex)
    category: str = "其他"
    kind: str = "asset"  # asset / account / server / note / api / email ...
    summary: str = ""  # 这条整体干什么用
    tags: list[str] = field(default_factory=list)
    fields: list[FieldItem] = field(default_factory=list)
    expires_at: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "kind": self.kind,
            "summary": self.summary,
            "tags": self.tags,
            "fields": [f.to_dict() for f in self.fields],
            "expires_at": self.expires_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Entry":
        # 兼容旧版 Credential
        if "fields" not in data and ("secret" in data or "username" in data):
            return cls.from_legacy_credential(data)

        raw_fields = data.get("fields") or []
        fields = [FieldItem.from_dict(x) for x in raw_fields]
        return cls(
            id=str(data.get("id") or uuid4().hex),
            name=str(data["name"]).strip(),
            category=str(data.get("category") or "其他"),
            kind=str(data.get("kind") or "asset"),
            summary=str(data.get("summary") or data.get("notes") or ""),
            tags=_parse_tags(data.get("tags")),
            fields=fields,
            expires_at=parse_expiry(data.get("expires_at")),
            created_at=str(data.get("created_at") or utc_now_iso()),
            updated_at=str(data.get("updated_at") or utc_now_iso()),
        )

    @classmethod
    def from_legacy_credential(cls, data: dict[str, Any]) -> "Entry":
        fields: list[FieldItem] = []
        if data.get("username"):
            fields.append(
                FieldItem(key="账号", value=str(data.get("username") or ""), purpose="登录账号")
            )
        if data.get("host"):
            fields.append(
                FieldItem(key="主机", value=str(data.get("host") or ""), purpose="主机/地址/IP")
            )
        if data.get("secret") is not None and str(data.get("secret")) != "":
            fields.append(
                FieldItem(
                    key="密码",
                    value=str(data.get("secret")),
                    purpose="主密码/密钥",
                    secret=True,
                )
            )
        return cls(
            id=str(data.get("id") or uuid4().hex),
            name=str(data["name"]).strip(),
            category=str(data.get("category") or "其他"),
            kind="account",
            summary=str(data.get("notes") or data.get("summary") or ""),
            tags=_parse_tags(data.get("tags")),
            fields=fields,
            expires_at=parse_expiry(data.get("expires_at")),
            created_at=str(data.get("created_at") or utc_now_iso()),
            updated_at=str(data.get("updated_at") or utc_now_iso()),
        )

    def days_until_expiry(self, today: date | None = None) -> int | None:
        if not self.expires_at:
            return None
        today = today or date.today()
        return (date.fromisoformat(self.expires_at) - today).days

    def expiry_status(self, warn_days: int = 14) -> str:
        days = self.days_until_expiry()
        if days is None:
            return "none"
        if days < 0:
            return "expired"
        if days <= warn_days:
            return "expiring_soon"
        return "ok"

    def find_field(self, key_or_id: str) -> FieldItem | None:
        key = key_or_id.strip()
        for item in self.fields:
            if item.id == key or item.key == key:
                return item
        matches = [f for f in self.fields if key.lower() in f.key.lower()]
        if len(matches) == 1:
            return matches[0]
        return None

    def upsert_field(
        self,
        key: str,
        value: str,
        purpose: str = "",
        secret: bool | None = None,
    ) -> FieldItem:
        key = key.strip()
        if not key:
            raise ValueError("字段名不能为空")
        existing = None
        for item in self.fields:
            if item.key == key:
                existing = item
                break
        if existing is None:
            item = FieldItem(
                key=key,
                value=value,
                purpose=purpose,
                secret=_looks_secret_key(key) if secret is None else secret,
            )
            self.fields.append(item)
            self.updated_at = utc_now_iso()
            return item
        existing.value = value
        if purpose:
            existing.purpose = purpose
        if secret is not None:
            existing.secret = secret
        self.updated_at = utc_now_iso()
        return existing

    def remove_field(self, key_or_id: str) -> FieldItem:
        target = self.find_field(key_or_id)
        if target is None:
            raise ValueError(f"未找到字段：{key_or_id}")
        self.fields = [f for f in self.fields if f.id != target.id]
        self.updated_at = utc_now_iso()
        return target

    def search_text(self) -> str:
        parts = [
            self.name,
            self.category,
            self.kind,
            self.summary,
            " ".join(self.tags),
        ]
        for f in self.fields:
            parts.extend([f.key, f.purpose, f.value])
        return " ".join(parts).lower()

    def public_view(self, include_secret: bool = False) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "kind": self.kind,
            "summary": self.summary,
            "tags": self.tags,
            "expires_at": self.expires_at,
            "days_until_expiry": self.days_until_expiry(),
            "expiry_status": self.expiry_status(),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "fields": [f.public_view(include_secret=include_secret) for f in self.fields],
        }


# 兼容旧导入名
Credential = Entry


@dataclass
class Reminder:
    """待办提醒：到期前 N 天提醒；可设一次/每周/每月/每季度/每年。"""

    title: str
    due_at: str  # YYYY-MM-DD（下一次到期日）
    id: str = field(default_factory=lambda: uuid4().hex)
    notes: str = ""
    remind_before_days: int = 3
    # once | weekly | monthly | quarterly | yearly
    repeat: str = "once"
    done: bool = False
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    REPEAT_LABELS = {
        "once": "仅一次",
        "weekly": "每周",
        "monthly": "每月",
        "quarterly": "每季度",
        "yearly": "每年",
    }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Reminder":
        repeat = str(data.get("repeat") or "once").strip().lower()
        if repeat not in cls.REPEAT_LABELS:
            repeat = "once"
        return cls(
            id=str(data.get("id") or uuid4().hex),
            title=str(data.get("title") or "").strip(),
            due_at=parse_expiry(data.get("due_at")) or date.today().isoformat(),
            notes=str(data.get("notes") or ""),
            remind_before_days=int(data.get("remind_before_days") or 3),
            repeat=repeat,
            done=bool(data.get("done") or False),
            created_at=str(data.get("created_at") or utc_now_iso()),
            updated_at=str(data.get("updated_at") or utc_now_iso()),
        )

    def days_until_due(self, today: date | None = None) -> int:
        today = today or date.today()
        return (date.fromisoformat(self.due_at) - today).days

    def should_alert(self, today: date | None = None) -> bool:
        if self.done:
            return False
        days = self.days_until_due(today)
        return days <= self.remind_before_days

    def alert_level(self) -> str:
        if self.done:
            return "done"
        days = self.days_until_due()
        if days < 0:
            return "overdue"
        if days == 0:
            return "today"
        if days <= self.remind_before_days:
            return "soon"
        return "ok"

    def repeat_label(self) -> str:
        return self.REPEAT_LABELS.get(self.repeat, "仅一次")

    def next_due_after(self, from_due: date | None = None) -> str | None:
        """计算下一周期到期日；仅一次则返回 None。"""
        if self.repeat == "once":
            return None
        base = from_due or date.fromisoformat(self.due_at)
        if self.repeat == "weekly":
            return (base + timedelta(days=7)).isoformat()
        if self.repeat == "monthly":
            return _add_months(base, 1).isoformat()
        if self.repeat == "quarterly":
            return _add_months(base, 3).isoformat()
        if self.repeat == "yearly":
            return _add_months(base, 12).isoformat()
        return None

    def public_view(self) -> dict[str, Any]:
        days = self.days_until_due()
        return {
            "id": self.id,
            "title": self.title,
            "due_at": self.due_at,
            "notes": self.notes,
            "remind_before_days": self.remind_before_days,
            "repeat": self.repeat,
            "repeat_label": self.repeat_label(),
            "done": self.done,
            "days_until_due": days,
            "alert_level": self.alert_level(),
            "should_alert": self.should_alert(),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def _add_months(d: date, months: int) -> date:
    """按月推进，日期超出当月则落到月末。"""
    year = d.year + (d.month - 1 + months) // 12
    month = (d.month - 1 + months) % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last_day))


@dataclass
class VaultData:
    version: int = 3
    entries: list[Entry] = field(default_factory=list)
    reminders: list[Reminder] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "entries": [e.to_dict() for e in self.entries],
            "reminders": [r.to_dict() for r in self.reminders],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VaultData":
        raw_entries = data.get("entries")
        if raw_entries is None:
            raw_entries = data.get("credentials") or []
        entries = [Entry.from_dict(x) for x in raw_entries]
        reminders = [Reminder.from_dict(x) for x in data.get("reminders") or []]
        return cls(version=3, entries=entries, reminders=reminders)

    @property
    def credentials(self) -> list[Entry]:
        """旧代码兼容。"""
        return self.entries
