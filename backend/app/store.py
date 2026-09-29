"""内存数据仓库：给每个业务模块准备一份可筛选、可流转的示例数据。

真实项目里这里会换成数据库访问层；当前实现只依赖标准库，保证克隆下来就能起。
"""
from __future__ import annotations

from typing import Any

from app.seed import SEED_ROWS

# 能源计量台账自用的表，不参与通用业务模块的运营概览统计
INTERNAL_TABLES = {"energy_points", "energy_policy", "energy_records", "energy_snapshots"}


class Store:
    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {
            name: [dict(row) for row in rows] for name, rows in SEED_ROWS.items()
        }

    def module_names(self) -> list[str]:
        return sorted(self._tables)

    def rows(self, module: str) -> list[dict[str, Any]]:
        return self._tables.setdefault(module, [])

    def find(self, module: str, entry_id: int) -> dict[str, Any] | None:
        for row in self.rows(module):
            if int(row.get("id", 0)) == entry_id:
                return row
        return None

    def overview(self) -> dict[str, object]:
        modules: list[dict[str, object]] = []
        for name in self.module_names():
            if name in INTERNAL_TABLES:
                continue
            rows = self.rows(name)
            modules.append({
                "name": name,
                "created": len(rows),
                "pending": sum(1 for row in rows if row.get("pending")),
                "abnormal": sum(1 for row in rows if row.get("abnormal")),
            })
        cards = [
            {"label": "业务模块", "value": len(modules)},
            {"label": "今日新增", "value": sum(int(item["created"]) for item in modules)},
            {"label": "待处理", "value": sum(int(item["pending"]) for item in modules)},
            {"label": "异常量", "value": sum(int(item["abnormal"]) for item in modules)},
        ]
        # 能源用电总量与台账条数直接取自能源台账的统一聚合，
        # 补录后运营概览跟着重算，且与首页、点位详情永远是同一份结果
        from app.services.energy import energy_service

        energy_overview = energy_service.build_overview()
        cards.append({"label": "用电总量(kWh)", "value": energy_overview["total"]})
        cards.append({"label": "能源台账条数", "value": energy_overview["record_count"]})
        energy_modules = [
            {
                "name": summary["point_name"],
                "created": summary["record_count"],
                "pending": 0,
                "abnormal": summary["missing_count"],
            }
            for summary in energy_overview["point_summaries"]
        ]
        return {"cards": cards, "modules": modules, "energy": energy_overview, "energy_modules": energy_modules}


store = Store()
