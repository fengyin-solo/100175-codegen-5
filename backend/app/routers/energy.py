"""能源计量台账接口：补录登记、峰谷口径调整、总量重算与历史结果。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.energy import EnergyService

router = APIRouter(prefix="/api/energy", tags=["能源计量台账"])

service = EnergyService()


@router.get("/overview")
def energy_overview() -> dict[str, Any]:
    """能源计量总览：各点位峰谷用量与总量；首页用电总量与点位详情取同一份结果。"""
    return service.results()


@router.get("/points", response_model=PageResult[dict])
def list_points(page: int = 1, size: int = 50) -> PageResult[dict]:
    """计量点位列表。"""
    items = service.list_points()
    return PageResult(items=items, total=len(items), page=page, size=size)


@router.post("/points", response_model=ActionResult)
def create_point(payload: EntryPayload) -> ActionResult:
    """登记一个计量点位，必填校验与上限规则在服务层处理。"""
    point, message = service.create_point(payload.values)
    if point is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=point)


@router.get("/records", response_model=PageResult[dict])
def list_records(
    point_id: int | None = Query(default=None, description="按计量点位过滤"),
    period: str | None = Query(default=None, description="按峰、谷、平时段过滤"),
    page: int = 1,
    size: int = 100,
) -> PageResult[dict]:
    """补录记录列表，可按点位与峰谷时段过滤。"""
    items = service.list_records(point_id=point_id, period=period)
    return PageResult(items=items, total=len(items), page=page, size=size)


@router.post("/records", response_model=ActionResult)
def create_record(payload: EntryPayload) -> ActionResult:
    """补录一条用电量；超计量上限或时段填写无效会被拦下，重复补录只入一次。"""
    record, message, duplicate = service.create_record(payload.values)
    if record is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=record)


@router.get("/standards")
def list_standards() -> dict[str, Any]:
    """峰谷时段口径版本列表，最新版本为当前口径。"""
    return {"items": service.list_standards()}


@router.post("/standards", response_model=ActionResult)
def adjust_standard(payload: EntryPayload) -> ActionResult:
    """调整峰谷时段口径：历史结果按当时口径冻结保留，补录数据按新口径重算总量。"""
    standard, message = service.adjust_standard(payload.values)
    if standard is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=standard)


@router.post("/recompute", response_model=ActionResult)
def recompute() -> ActionResult:
    """按当前口径重算全部补录数据的峰谷用量与总量，并冻结一份历史结果。"""
    standard = service.recompute()
    return ActionResult(ok=True, message=f"已按口径 v{standard['version']} 重算总量", entry=standard)


@router.get("/snapshots")
def list_snapshots() -> dict[str, Any]:
    """历史结果快照：每份快照按当时的时段口径保留。"""
    return {"items": service.list_snapshots()}


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出能源计量台账：返回当前全量补录记录。"""
    items = service.list_records()
    return {"module": "energy", "total": len(items), "items": items}
