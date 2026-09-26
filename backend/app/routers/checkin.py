"""出车检查接口：维护检查记录，覆盖执行检查、登记整改、复核通过等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.checkin import CheckinService

router = APIRouter(prefix="/api/checkin", tags=["出车检查"])

service = CheckinService()

LIST_FIELDS = ["检查编号", "检查车辆", "检查日期", "轮胎状况", "制冷运转", "厢体密封", "检查人员", "检查结论", "检查状态"]
STATUSES = ["待检查", "已检查", "整改中", "已通过"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按检查编号检索"),
    vehicle: str | None = Query(default=None, description="按检查车辆检索"),
    status: str | None = Query(default=None, description="待检查、已检查、整改中、已通过"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按检查编号、检查车辆与状态过滤出车检查列表；没有数据时返回空页，不报错。"""
    if status and status not in STATUSES:
        raise HTTPException(status_code=400, detail=f"状态「{status}」不在可选范围：{'、'.join(STATUSES)}")
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, vehicle=vehicle, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/stats")
def stats() -> dict[str, int]:
    """各检查状态的车辆数量，供顶部统计卡片使用。"""
    return service.stats()


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出出车检查清单：返回当前全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "checkin", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条检查记录明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"检查记录 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条检查记录，缺字段时说明原因而不是静默丢弃；同检查编号重复提交只生效一次。"""
    entry, missing, duplicated = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    if duplicated:
        return ActionResult(ok=True, message=f"检查编号 {entry['检查编号']} 已存在，重复提交只生效一次", entry=entry)
    return ActionResult(ok=True, message="检查记录已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条检查记录执行执行检查、登记整改、复核通过；不允许的动作会被拦下并说明原因。

    业务失败（状态不符、检查项为空、结论缺失等）仍以 200 + ok=False 返回，
    message 里给出可读原因，前端据此展示失败原因与重试入口。
    """
    action = str(payload.values.get("action") or "").strip()
    entry, message, _idempotent = service.run_action(entry_id, action, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
