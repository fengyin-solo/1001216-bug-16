"""出车检查业务规则：状态流转、字段校验与筛选口径都收在这里。

列表、详情与检查弹窗看到的「是否可执行检查、为什么不能」都来自 ``_judge``，
避免各处口径不一致；重复提交由这里保证幂等，制冷运转等检查项缺失时
返回可读原因，而不是静默退回。
"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "checkin"
REQUIRED_FIELDS = ["检查编号", "检查车辆", "检查日期"]
CHECK_ITEMS = ["轮胎状况", "制冷运转", "厢体密封"]
STATUS_ORDER = ["待检查", "已检查", "整改中", "已通过"]
CONCLUSIONS = ["合格", "不合格"]
CONCLUSION_TARGET = {"合格": "已检查", "不合格": "整改中"}
# 登记整改 / 复核通过仍保留原流转，执行检查按检查结论走，统一从 ACTION_RULES 查
ACTION_RULES = {"登记整改": "整改中", "复核通过": "已通过"}
NEGATIVE_ACTIONS = []

# 每个动作允许从哪些状态触发，列表/详情/弹窗共用这份口径
ACTION_PERMISSION = {
    "执行检查": ["待检查"],
    "登记整改": ["已检查", "整改中"],
    "复核通过": ["整改中", "已检查"],
}


class CheckinService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        vehicle: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("检查编号", ""))]
        if vehicle:
            rows = [row for row in rows if vehicle in str(row.get("检查车辆", ""))]
        if status:
            rows = [row for row in rows if str(row.get("status") or "") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [self._serialize(row) for row in rows[start:start + size]], total

    def stats(self) -> dict[str, int]:
        rows = store.rows(MODULE)
        return {
            "待检查": sum(1 for row in rows if row.get("status") == "待检查"),
            "整改中": sum(1 for row in rows if row.get("status") == "整改中"),
            "已通过": sum(1 for row in rows if row.get("status") == "已通过"),
        }

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return self._serialize(entry) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str], bool]:
        """登记一条检查记录。

        返回 (记录, 缺失字段, 是否为重复提交)。同一检查编号重复提交只生效一次，
        直接返回已存在的记录，不再生成新记录。
        """
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing, False
        number = str(values.get("检查编号")).strip()
        rows = store.rows(MODULE)
        for row in rows:
            if str(row.get("检查编号") or "") == number:
                # 幂等：重试或重复提交拿到的是同一条记录，列表里不会多出一条
                return self._serialize(row), [], True
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in REQUIRED_FIELDS + CHECK_ITEMS + ["检查人员"]:
            value = values.get(field)
            if value is not None and str(value).strip():
                entry[field] = value
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return self._serialize(entry), [], False

    def run_action(self, entry_id: int, action: str, values: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, str, bool]:
        """执行检查 / 登记整改 / 复核通过。

        返回 (更新后的记录, 说明, 是否幂等命中)。重复提交只生效一次：状态已经
        处于该动作的目标结果时，返回当前记录与幂等说明，不重复落库。
        """
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"检查记录 {entry_id} 不存在或已归档", False
        if not action or action not in ACTION_PERMISSION:
            return None, f"动作「{action}」不属于出车检查可执行范围", False

        values = values or {}
        status = str(entry.get("status") or "")
        allowed = ACTION_PERMISSION[action]

        if action == "执行检查":
            conclusion = str(values.get("检查结论") or "").strip()
            if not conclusion:
                return None, "请先选择检查结论（合格/不合格）再提交", False
            if conclusion not in CONCLUSIONS:
                return None, f"检查结论「{conclusion}」无法识别，仅支持合格或不合格", False
            target = CONCLUSION_TARGET[conclusion]
            # 同结论重复提交（含首次已成功、网络失败后的重试）只生效一次
            if status == target and str(entry.get("检查结论") or "") == conclusion:
                return self._serialize(entry), f"检查编号 {entry.get('检查编号')} 的结论已提交，重复提交只生效一次", True
            # 再校验状态权限：非待检查的记录不能再次执行检查
            if status not in allowed:
                judge = self._judge(entry)
                return None, f"{judge['禁止原因']}；仅{'、'.join(allowed)}的记录可{action}", False
            # 检查项（轮胎/制冷/厢体）缺失时说明具体原因，而不是静默退回
            reason = self._missing_reason(entry)
            if reason:
                return None, reason, False
            entry["检查结论"] = conclusion
            self._switch_status(entry, target)
            return self._serialize(entry), f"检查记录已{action}，结论为{conclusion}", False

        target = ACTION_RULES[action]
        if status == target:
            return self._serialize(entry), f"检查记录当前已是「{target}」，{action}无需重复提交", True
        if status not in allowed:
            judge = self._judge(entry)
            detail = judge["禁止原因"] or f"当前状态为「{status}」"
            return None, f"{detail}；仅{'、'.join(allowed)}的记录可{action}", False
        self._switch_status(entry, target)
        return self._serialize(entry), f"检查记录已{action}", False

    # ---- 列表 / 详情 / 检查弹窗共用的判断口径 ----

    @staticmethod
    def _missing_items(entry: dict[str, Any]) -> list[str]:
        return [item for item in CHECK_ITEMS if not str(entry.get(item) or "").strip()]

    @staticmethod
    def _missing_reason(entry: dict[str, Any]) -> str:
        missing = CheckinService._missing_items(entry)
        if not missing:
            return ""
        return (
            f"{'、'.join(missing)}为空，无法完成执行检查；"
            "请先补录检查结果（制冷机组不运转也要填写具体原因，而不是留空）"
        )

    def _judge(self, entry: dict[str, Any]) -> dict[str, Any]:
        """返回单条记录在列表、详情、检查弹窗里统一使用的判断结果。"""
        status = str(entry.get("status") or "")
        missing = self._missing_items(entry)
        verdict: dict[str, Any] = {
            "当前状态": status,
            "缺失检查项": missing,
            "可执行动作": [],
            "不可执行动作": [],
            "禁止原因": "",
            "状态说明": "",
        }
        if status == "待检查":
            if missing:
                verdict["状态说明"] = self._missing_reason(entry)
                verdict["禁止原因"] = f"{'、'.join(missing)}为空，需先补录检查结果"
                verdict["不可执行动作"] = list(ACTION_PERMISSION.keys())
            else:
                verdict["状态说明"] = "检查项已齐全，可执行检查并填写检查结论"
                verdict["可执行动作"] = ["执行检查"]
                verdict["不可执行动作"] = ["登记整改", "复核通过"]
        elif status == "已检查":
            verdict["状态说明"] = f"已完成执行检查，结论：{entry.get('检查结论') or '未记录'}"
            verdict["可执行动作"] = ["登记整改", "复核通过"]
            verdict["不可执行动作"] = ["执行检查"]
            verdict["禁止原因"] = "该车辆已完成检查，执行检查无需重复提交"
        elif status == "整改中":
            verdict["状态说明"] = "检查不合格，整改完成后请复核通过"
            verdict["可执行动作"] = ["登记整改", "复核通过"]
            verdict["不可执行动作"] = ["执行检查"]
            verdict["禁止原因"] = "车辆整改中，需先复核通过才能结束本次检查"
        elif status == "已通过":
            verdict["状态说明"] = "检查与复核均已通过，本次出车检查已闭环"
            verdict["不可执行动作"] = list(ACTION_PERMISSION.keys())
            verdict["禁止原因"] = "检查已通过并闭环，无需再提交动作"
        else:
            verdict["状态说明"] = f"未知状态「{status}」，请联系管理员核对数据"
            verdict["不可执行动作"] = list(ACTION_PERMISSION.keys())
            verdict["禁止原因"] = verdict["状态说明"]
        return verdict

    def _serialize(self, entry: dict[str, Any]) -> dict[str, Any]:
        data = dict(entry)
        # 检查状态以流转状态为准，避免示例数据里的占位文本误导判断
        data["检查状态"] = str(entry.get("status") or "")
        data["判定"] = self._judge(entry)
        return data

    @staticmethod
    def _switch_status(entry: dict[str, Any], target: str) -> None:
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = target == "整改中"
