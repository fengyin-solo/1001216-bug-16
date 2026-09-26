"""出车检查业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "checkin"
REQUIRED_FIELDS = ["检查编号", "检查车辆", "检查日期"]
CONCLUSION_FIELDS = ["轮胎状况", "制冷运转", "厢体密封", "检查人员", "检查结论"]
STATUS_ORDER = ["待检查", "已检查", "整改中", "已通过"]
ACTION_TARGETS = {"执行检查": "已检查", "登记整改": "整改中", "复核通过": "已通过"}
# 每个动作允许的起始状态：列表、详情与检查弹窗共用这一份判断，保证各处口径一致。
ACTION_TRANSITIONS = {
    "执行检查": ["待检查"],
    "登记整改": ["已检查"],
    "复核通过": ["整改中"],
}


def _text(value: Any) -> str:
    return str(value or "").strip()


class CheckinService:
    def allowed_actions(self, entry: dict[str, Any]) -> list[str]:
        """按当前状态计算可执行动作，是列表、详情、检查弹窗共用的判断口径。"""
        status = _text(entry.get("status")) or STATUS_ORDER[0]
        return [action for action, sources in ACTION_TRANSITIONS.items() if status in sources]

    def present(self, entry: dict[str, Any]) -> dict[str, Any]:
        """统一对外视图：补齐检查状态与可执行动作，避免各页面各自推断。"""
        row = dict(entry)
        status = _text(entry.get("status")) or STATUS_ORDER[0]
        actions = self.allowed_actions(entry)
        row["检查状态"] = status
        row["可执行动作"] = actions
        row["可提交结论"] = "执行检查" in actions
        if not row["可提交结论"]:
            row["结论说明"] = f"当前状态为「{status}」，检查结论已生效，无需重复提交"
        return row

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        vehicle: str | None = None,
        date: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in _text(row.get("检查编号"))]
        if vehicle:
            rows = [row for row in rows if vehicle in _text(row.get("检查车辆"))]
        if date:
            rows = [row for row in rows if date in _text(row.get("检查日期"))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [self.present(row) for row in rows[start:start + size]], total

    def summary(self) -> dict[str, Any]:
        """按状态统计车辆数，给列表页统计卡片用，与列表共用同一份状态口径。"""
        rows = store.rows(MODULE)
        by_status: dict[str, int] = {status: 0 for status in STATUS_ORDER}
        for row in rows:
            status = _text(row.get("status")) or STATUS_ORDER[0]
            by_status[status] = by_status.get(status, 0) + 1
        return {"total": len(rows), "by_status": by_status}

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str], bool]:
        """登记检查记录；同一检查编号重复提交只生效一次，返回已存在的记录。"""
        missing = [field for field in REQUIRED_FIELDS if not _text(values.get(field))]
        if missing:
            return None, missing, False
        code = _text(values.get("检查编号"))
        rows = store.rows(MODULE)
        for row in rows:
            if _text(row.get("检查编号")) == code:
                return row, [], False
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, [], True

    def submit_conclusion(self, entry_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str, bool]:
        """提交检查结论：必填项缺失（含制冷运转为空）说明原因；重复提交幂等。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"检查记录 {entry_id} 不存在或已归档", False
        status = _text(entry.get("status")) or STATUS_ORDER[0]
        if status != STATUS_ORDER[0]:
            if _text(entry.get("检查结论")):
                # 幂等：结论已生效，失败后重试等重复提交直接返回已生效的记录
                return entry, f"检查编号 {_text(entry.get('检查编号'))} 的检查结论已提交过，本次重复提交未重复生效", True
            allowed = self.allowed_actions(entry)
            hint = f"可执行动作：{'、'.join(allowed)}" if allowed else "当前没有可执行动作"
            return None, f"当前状态为「{status}」，不能提交检查结论；{hint}", False
        missing = [field for field in CONCLUSION_FIELDS if not _text(values.get(field))]
        if "制冷运转" in missing:
            return None, "制冷运转结果不能为空：请填写制冷机组运转情况后再提交，否则无法判断冷链是否满足出车条件", False
        if missing:
            return None, f"检查结论未填写完整，缺少：{'、'.join(missing)}", False
        for field in CONCLUSION_FIELDS:
            entry[field] = values.get(field)
        entry["status"] = "已检查"
        entry["pending"] = True
        entry["abnormal"] = False
        return entry, f"检查编号 {_text(entry.get('检查编号'))} 的检查结论已提交，状态更新为「已检查」", True

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"检查记录 {entry_id} 不存在或已归档"
        if action not in ACTION_TRANSITIONS:
            return None, f"动作「{action}」不属于出车检查可执行范围"
        if action == "执行检查":
            return None, "执行检查需要填写检查结论，请在检查弹窗中填写完整后提交"
        status = _text(entry.get("status")) or STATUS_ORDER[0]
        if status not in ACTION_TRANSITIONS[action]:
            allowed = self.allowed_actions(entry)
            hint = f"可执行动作：{'、'.join(allowed)}" if allowed else "当前没有可执行动作"
            return None, f"当前状态为「{status}」，不能执行「{action}」；{hint}"
        target = ACTION_TARGETS[action]
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = False
        return entry, f"检查记录已{action}"
