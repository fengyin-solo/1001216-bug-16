"""出车检查接口：维护检查记录，覆盖执行检查、登记整改、复核通过等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.checkin import CheckinService

router = APIRouter(prefix="/api/checkin", tags=["出车检查"])

service = CheckinService()


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按检查编号检索"),
    vehicle: str | None = Query(default=None, description="按检查车辆检索"),
    date: str | None = Query(default=None, description="按检查日期检索"),
    status: str | None = Query(default=None, description="待检查、已检查、整改中、已通过"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按过滤条件返回出车检查列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(
        keyword=keyword, vehicle=vehicle, date=date, status=status, page=page, size=size
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/summary")
def summary() -> dict[str, Any]:
    """状态统计：给列表页统计卡片用，与列表共用同一份状态口径。"""
    return service.summary()


@router.get("/export")
def export_entries(
    keyword: str | None = Query(default=None, description="按检查编号检索"),
    vehicle: str | None = Query(default=None, description="按检查车辆检索"),
    date: str | None = Query(default=None, description="按检查日期检索"),
    status: str | None = Query(default=None, description="待检查、已检查、整改中、已通过"),
) -> dict[str, Any]:
    """导出出车检查清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(
        keyword=keyword, vehicle=vehicle, date=date, status=status, page=1, size=10000
    )
    return {"module": "checkin", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条检查记录明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"检查记录 {entry_id} 不存在或已归档")
    return service.present(entry)


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记检查记录：缺字段说明原因；同一检查编号重复提交只生效一次。"""
    entry, missing, created = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    assert entry is not None
    if not created:
        return ActionResult(
            ok=True,
            message=f"检查编号 {entry.get('检查编号')} 已存在，本次重复提交未生成新记录",
            entry=service.present(entry),
        )
    return ActionResult(ok=True, message="检查记录已登记", entry=service.present(entry))


@router.post("/{entry_id}/conclusion", response_model=ActionResult)
def submit_conclusion(entry_id: int, payload: EntryPayload) -> ActionResult:
    """提交检查结论：必填项缺失（含制冷运转为空）时说明原因；重复提交幂等。"""
    entry, message, ok = service.submit_conclusion(entry_id, payload.values)
    if not ok:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=service.present(entry))


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条检查记录执行登记整改、复核通过；不满足前置状态的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=service.present(entry))
