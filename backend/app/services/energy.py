"""能源计量台账业务规则。

设计口径：
- 计量点位（energy_points）有本点位的单次计量上限 upper_limit；
- 峰谷时段口径（energy_policy）带版本号，当前口径只有一份；调整口径时老口径转历史，
  已补录的原始用量按新口径重新归类并汇总（current 部分），调整当时算出的历史结果
  以快照（energy_snapshots）形式保留，仍按当时口径查看；
- 每条补录（energy_records）落库时按当前口径固化峰/平/谷归属；usage=None 表示
  采集器未回传，参与展示但不计入任何用量合计，绝不当作 0；
- 首页用电总量、点位详情、运营概览的用电总量都走 build_overview 这同一份聚合结果。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

POINTS = "energy_points"
POLICY = "energy_policy"
RECORDS = "energy_records"
SNAPSHOTS = "energy_snapshots"

# 与 app.store 保持同一份清单：能源内部表不参与通用模块统计
INTERNAL_TABLES = {POINTS, POLICY, RECORDS, SNAPSHOTS}

PERIOD_ORDER = ["峰", "平", "谷"]
DAY_MINUTES = 24 * 60
ROUND_DIGITS = 2
DATE_FMT = "%Y-%m-%d"
TIME_FMT = "%H:%M"


def _round(value: float) -> float:
    """金额/电量统一保留两位，避免浮点尾差让首页和详情对不上。"""
    return round(value + 1e-9, ROUND_DIGITS)


def parse_minutes(text: str) -> int | None:
    """把 HH:MM 解析成当天分钟数；24:00 视为一天终点（1440），其余非法写法返回 None。"""
    parts = str(text or "").strip().split(":")
    if len(parts) != 2:
        return None
    hour_text, minute_text = parts
    if not (hour_text.isdigit() and minute_text.isdigit()):
        return None
    hour, minute = int(hour_text), int(minute_text)
    if hour == 24 and minute == 0:
        return DAY_MINUTES
    if 0 <= hour < 24 and 0 <= minute < 60:
        return hour * 60 + minute
    return None


def _canonical_ranges(periods: list[dict[str, Any]]) -> list[tuple[str, list[list[int]]]]:
    """把入参时段归一成 [(时段名, [[起,止], ...])]；任何非法时间/区间直接抛 ValueError。"""
    result: list[tuple[str, list[list[int]]]] = []
    seen = set()
    for item in periods:
        name = str(item.get("period") or "").strip()
        if name not in ("峰", "谷"):
            raise ValueError("只允许登记「峰」「谷」两类时段，其余时间自动归为平段")
        if name in seen:
            raise ValueError(f"时段「{name}」重复填写，请合并到同一段里")
        seen.add(name)
        ranges: list[list[int]] = []
        raw_ranges = item.get("ranges") or []
        if not isinstance(raw_ranges, list) or not raw_ranges:
            raise ValueError(f"时段「{name}」至少需要填写一个时间区间")
        for raw in raw_ranges:
            if not isinstance(raw, (list, tuple)) or len(raw) != 2:
                raise ValueError(f"时段「{name}」的时间区间必须是 [开始, 结束] 形式")
            start = parse_minutes(str(raw[0]))
            end = parse_minutes(str(raw[1]))
            if start is None or end is None:
                raise ValueError(f"时段「{name}」存在无法识别的时间：{raw[0]} ~ {raw[1]}")
            if start >= end:
                raise ValueError(f"时段「{name}」的区间 {raw[0]} ~ {raw[1]} 开始时间必须早于结束时间")
            ranges.append([start, end])
        result.append((name, sorted(ranges)))
    return result


def validate_policy(periods: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """校验新口径：时间合法、峰谷区间互不交叠；返回规范化后的结构。"""
    canonical = _canonical_ranges(periods)
    occupied: list[tuple[int, int, str]] = []
    for name, ranges in canonical:
        for start, end in ranges:
            for prev_start, prev_end, prev_name in occupied:
                if start < prev_end and prev_start < end:
                    raise ValueError(f"「{prev_name}」与「{name}」的时间区间发生重叠，请重新划分")
            occupied.append((start, end, name))
    return [
        {"period": name, "ranges": [[_fmt_minutes(start), _fmt_minutes(end)] for start, end in ranges]}
        for name, ranges in canonical
    ]


def _fmt_minutes(value: int) -> str:
    if value == DAY_MINUTES:
        return "24:00"
    return f"{value // 60:02d}:{value % 60:02d}"


def classify_time(time_text: str, policy_row: dict[str, Any]) -> str | None:
    """按指定口径把一个时刻归到 峰/平/谷；时间写法非法返回 None。"""
    minute = parse_minutes(time_text)
    if minute is None:
        return None
    for item in policy_row.get("periods", []):
        for raw_start, raw_end in item.get("ranges", []):
            start = parse_minutes(str(raw_start))
            end = parse_minutes(str(raw_end))
            if start is not None and end is not None and start <= minute < end:
                return str(item["period"])
    return "平"


def _next_id(rows: list[dict[str, Any]]) -> int:
    return max((int(row.get("id", 0)) for row in rows), default=0) + 1


class EnergyService:
    # ---------- 口径管理 ----------
    def current_policy(self) -> dict[str, Any]:
        rows = store.rows(POLICY)
        current = [row for row in rows if row.get("is_current")]
        return current[-1] if current else rows[-1]

    def list_policies(self) -> list[dict[str, Any]]:
        return list(reversed(store.rows(POLICY)))

    def update_policy(self, periods: list[dict[str, Any]], *, now: str | None = None) -> tuple[dict[str, Any] | None, str]:
        """调整峰谷口径：先留存历史快照，再让全部已补录数据按新口径重算。"""
        try:
            normalized = validate_policy(periods)
        except ValueError as exc:
            return None, str(exc)

        old_policy = self.current_policy()
        # 口径与当前完全一致时不产生新版本，避免无意义重算
        if old_policy and old_policy.get("periods") == normalized:
            return None, "新口径与当前峰谷时段完全一致，无需调整"

        stamp = now or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        overview = self.build_overview(policy_row=old_policy)
        snapshot = {
            "id": _next_id(store.rows(SNAPSHOTS)),
            "policy_version": old_policy["version"],
            "periods": old_policy["periods"],
            "updated_at": old_policy.get("updated_at"),
            "archived_at": stamp,
            "remark": f"第 {old_policy['version']} 版口径调整前的历史用量结果",
            "point_summaries": overview["point_summaries"],
            "cards": overview["cards"],
        }
        store.rows(SNAPSHOTS).append(snapshot)
        old_policy["is_current"] = False

        new_version = max(int(row["version"]) for row in store.rows(POLICY)) + 1
        new_policy = {
            "version": new_version,
            "updated_at": stamp[:10],
            "periods": normalized,
            "is_current": True,
            "remark": "峰谷时段口径调整",
        }
        store.rows(POLICY).append(new_policy)

        # 已补录数据按新口径重算归属与总量（原始用量不变）
        for record in store.rows(RECORDS):
            record["policy_version"] = new_version
            record["period"] = classify_time(str(record.get("time") or ""), new_policy)

        return new_policy, f"峰谷时段已更新为第 {new_version} 版口径，历史用量已按新口径重算"

    # ---------- 点位 ----------
    def list_points(self) -> list[dict[str, Any]]:
        return store.rows(POINTS)

    def get_point(self, point_id: int) -> dict[str, Any] | None:
        return store.find(POINTS, point_id)

    # ---------- 补录 ----------
    def list_records(self, point_id: int | None = None, period: str | None = None) -> list[dict[str, Any]]:
        rows = store.rows(RECORDS)
        if point_id is not None:
            rows = [row for row in rows if int(row.get("point_id", 0)) == point_id]
        if period:
            rows = [row for row in rows if row.get("period") == period]
        return rows

    def backfill_record(
        self,
        values: dict[str, Any],
        *,
        now: str | None = None,
    ) -> tuple[dict[str, Any] | None, str, bool]:
        """登记一条补录。

        返回 (记录, 说明, 是否重复)：超计量上限、时段/时间非法、点位不存在一律拦下；
        同一点位同一日期同一时刻的补录重复送两遍只入一次。
        """
        code = str(values.get("point_code") or values.get("point_id") or "").strip()
        point = self._resolve_point(code)
        if point is None:
            return None, f"计量点位「{code}」不存在，请先建档", False

        date_text = str(values.get("date") or "").strip()
        time_text = str(values.get("time") or "").strip()
        try:
            datetime.strptime(date_text, DATE_FMT)
        except ValueError:
            return None, "补录日期无效，请按 年-月-日（如 2026-09-20）填写", False
        policy = self.current_policy()
        period = classify_time(time_text, policy)
        if period is None:
            return None, f"时段填写无效：「{time_text}」不是合法的 HH:MM 时间", False

        # usage 缺省/空串表示采集器没回传：允许登记，但不计入用量
        raw_usage = values.get("usage")
        if raw_usage is None or (isinstance(raw_usage, str) and not raw_usage.strip()):
            usage: float | None = None
        else:
            try:
                usage = float(raw_usage)
            except (TypeError, ValueError):
                return None, f"用电量「{raw_usage}」不是有效数值", False
            if not (usage == usage) or usage in (float("inf"), float("-inf")):
                return None, f"用电量「{raw_usage}」不是有效数值", False
            if usage < 0:
                return None, "用电量不能为负数", False
            upper = float(point.get("upper_limit") or 0)
            if upper > 0 and usage > upper:
                return None, f"用电量 {usage} 超出点位「{point['name']}」的计量上限 {upper:g}，记录已拦下", False
            usage = _round(usage)

        rows = store.rows(RECORDS)
        duplicate = next(
            (
                row
                for row in rows
                if int(row.get("point_id", 0)) == int(point["id"])
                and str(row.get("date")) == date_text
                and str(row.get("time")) == time_text
            ),
            None,
        )
        if duplicate is not None:
            # 同一条补录重复送两遍：幂等返回已存在的记录，不再入库
            return duplicate, "该点位同一日期同一时段的补录已存在，无需重复提交", True

        entry = {
            "id": _next_id(rows),
            "point_id": point["id"],
            "date": date_text,
            "time": time_text,
            "usage": usage,
            "policy_version": policy["version"],
            "period": period,
            "created_at": now or datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        }
        rows.append(entry)
        return entry, "补录已登记", False

    def _resolve_point(self, code: str) -> dict[str, Any] | None:
        if not code:
            return None
        if code.isdigit():
            point = store.find(POINTS, int(code))
            if point is not None:
                return point
        return next(
            (row for row in store.rows(POINTS) if str(row.get("code")) == code),
            None,
        )

    # ---------- 聚合：首页、点位详情、运营概览共用这一份 ----------
    def build_overview(self, *, policy_row: dict[str, Any] | None = None) -> dict[str, Any]:
        policy_row = policy_row or self.current_policy()
        records = store.rows(RECORDS)
        points = store.rows(POINTS)

        summaries: list[dict[str, Any]] = []
        totals = {name: 0.0 for name in PERIOD_ORDER}
        collected = 0
        missing = 0

        for point in points:
            point_records = [row for row in records if int(row.get("point_id", 0)) == int(point["id"])]
            usage_by_period = {name: 0.0 for name in PERIOD_ORDER}
            point_missing = 0
            for row in point_records:
                period = classify_time(str(row.get("time") or ""), policy_row) or "平"
                if row.get("usage") is None:
                    point_missing += 1
                    continue
                usage_by_period[period] = usage_by_period.get(period, 0.0) + float(row["usage"])
            usage_by_period = {name: _round(value) for name, value in usage_by_period.items()}
            total = _round(sum(usage_by_period.values()))
            for name, value in usage_by_period.items():
                totals[name] += value
            collected += sum(1 for row in point_records if row.get("usage") is not None)
            missing += point_missing
            summaries.append({
                "point_id": point["id"],
                "point_code": point.get("code"),
                "point_name": point.get("name"),
                "location": point.get("location"),
                "upper_limit": point.get("upper_limit"),
                "usage_by_period": usage_by_period,
                "total": total,
                "record_count": len(point_records),
                "missing_count": point_missing,
            })

        period_totals = {name: _round(totals[name]) for name in PERIOD_ORDER}
        grand_total = _round(sum(period_totals.values()))
        cards = [
            {"label": "用电总量(kWh)", "value": grand_total},
            {"label": "峰段用电(kWh)", "value": period_totals["峰"]},
            {"label": "平段用电(kWh)", "value": period_totals["平"]},
            {"label": "谷段用电(kWh)", "value": period_totals["谷"]},
            {"label": "台账条数", "value": len(records)},
            {"label": "未采集条数", "value": missing},
        ]
        return {
            "policy": self._policy_payload(policy_row),
            "cards": cards,
            "period_totals": period_totals,
            "total": grand_total,
            "record_count": len(records),
            "collected_count": collected,
            "missing_count": missing,
            "point_summaries": summaries,
        }

    def point_detail(self, point_id: int) -> dict[str, Any] | None:
        """点位详情直接取整表聚合里的同一份结果，再挂上分组后的明细。"""
        overview = self.build_overview()
        summary = next(
            (item for item in overview["point_summaries"] if int(item["point_id"]) == point_id),
            None,
        )
        if summary is None:
            return None
        point = self.get_point(point_id) or {}
        records = self.list_records(point_id=point_id)
        groups: list[dict[str, Any]] = []
        for period in PERIOD_ORDER:
            group_records = [row for row in records if row.get("period") == period]
            group_records.sort(key=lambda row: (str(row.get("date")), str(row.get("time"))))
            groups.append({
                "period": period,
                "count": len(group_records),
                "usage": summary["usage_by_period"].get(period, 0.0),
                "records": group_records,
            })
        return {
            "point_id": point_id,
            "point_code": point.get("code"),
            "point_name": point.get("name"),
            "location": point.get("location"),
            "upper_limit": point.get("upper_limit"),
            "policy": overview["policy"],
            "usage_by_period": summary["usage_by_period"],
            "total": summary["total"],
            "record_count": summary["record_count"],
            "missing_count": summary["missing_count"],
            "groups": groups,
        }

    def list_snapshots(self) -> list[dict[str, Any]]:
        return list(reversed(store.rows(SNAPSHOTS)))

    def _policy_payload(self, policy_row: dict[str, Any] | None) -> dict[str, Any] | None:
        if policy_row is None:
            return None
        return {
            "version": policy_row.get("version"),
            "updated_at": policy_row.get("updated_at"),
            "periods": policy_row.get("periods"),
            "is_current": policy_row.get("is_current", True),
        }


energy_service = EnergyService()
