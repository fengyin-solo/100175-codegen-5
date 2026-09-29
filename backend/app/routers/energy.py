"""能源计量台账接口：补录用电量、调整峰谷口径、查看点位峰谷用量与历史快照。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.schemas import ActionResult
from app.services.energy import EnergyService

router = APIRouter(prefix="/api/energy", tags=["能源计量台账"])

service = EnergyService()


class BackfillPayload(BaseModel):
    """补录一条计量点位用电量。"""

    point_code: str | None = None
    point_id: int | None = None
    date: str
    time: str
    usage: float | None = None


class PolicyPayload(BaseModel):
    """调整峰谷时段口径；未覆盖的时间自动归为平段。"""

    periods: list[dict[str, Any]] = Field(default_factory=list)
    remark: str | None = None


@router.get("/overview")
def energy_overview() -> dict[str, Any]:
    """同一份聚合结果：首页用电总量、点位详情、运营概览都取这里。"""
    return service.build_overview()


@router.get("/points")
def list_points() -> dict[str, Any]:
    """列出全部计量点位。"""
    return {"items": service.list_points()}


@router.get("/points/{point_id}")
def point_detail(point_id: int) -> dict[str, Any]:
    """点位详情：峰/平/谷用量、总量与按峰谷时段分组的补录明细，同源于 overview。"""
    detail = service.point_detail(point_id)
    if detail is None:
        return {"ok": False, "message": f"计量点位 {point_id} 不存在"}
    return detail


@router.get("/records")
def list_records(point_id: int | None = None, period: str | None = None) -> dict[str, Any]:
    """补录明细，可按点位与峰谷时段过滤。"""
    items = service.list_records(point_id=point_id, period=period)
    return {"items": items, "total": len(items)}


@router.post("/records", response_model=ActionResult)
def backfill_record(payload: BackfillPayload) -> ActionResult:
    """补录一条用电量；超计量上限、时段非法都会被拦下，重复补录只入一次。"""
    values = payload.model_dump(exclude_none=True)
    entry, message, duplicated = service.backfill_record(values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry | {"duplicated": duplicated})


@router.get("/policy")
def get_policy() -> dict[str, Any]:
    """当前峰谷时段口径与历次版本。"""
    return {"current": service.current_policy(), "history": service.list_policies()}


@router.put("/policy", response_model=ActionResult)
def update_policy(payload: PolicyPayload) -> ActionResult:
    """调整峰谷时段：已补录数据按新口径重算总量，调整前结果以快照留存。"""
    policy, message = service.update_policy(payload.periods)
    if policy is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=service._policy_payload(policy))


@router.get("/snapshots")
def list_snapshots() -> dict[str, Any]:
    """历次口径调整时留存的历史结果（按当时时段口径计算）。"""
    return {"items": service.list_snapshots()}
