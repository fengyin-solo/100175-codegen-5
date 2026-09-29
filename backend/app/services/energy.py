"""能源计量台账业务规则：补录校验、峰谷口径重算、历史结果冻结与落盘持久化。

口径调整后，已补录数据按新口径重算总量；历史结果以快照形式按当时的时段口径保留。
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from app.seed import ENERGY_SEED

MODULE = "energy"

# 落盘文件：页面关掉重开、服务重启后仍能看到最新台账结果
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DATA_FILE = DATA_DIR / "energy_ledger.json"

HHMM_RE = re.compile(r"^(\d{1,2}):(\d{2})$")
DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")

PERIODS = ("峰", "谷", "平")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def parse_hhmm(value: str) -> int | None:
    """把 HH:MM 解析成分钟数；非法时间返回 None。"""
    if not isinstance(value, str):
        return None
    match = HHMM_RE.fullmatch(value.strip())
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 24 or minute > 59 or (hour == 24 and minute != 0):
        return None
    return hour * 60 + minute


def parse_range(value: str, *, allow_overnight: bool) -> tuple[int, int] | None:
    """把 HH:MM-HH:MM 解析成分钟区间 [start, end)；非法区间返回 None。

    allow_overnight 为 True 时允许跨日区间（如 22:00-06:00），用于峰谷口径时段。
    """
    if not isinstance(value, str) or "-" not in value:
        return None
    parts = value.split("-")
    if len(parts) != 2:
        return None
    start = parse_hhmm(parts[0])
    end = parse_hhmm(parts[1])
    if start is None or end is None or start == end:
        return None
    if not allow_overnight and start >= end:
        return None
    return start, end


def _minute_in_range(minute: int, start: int, end: int) -> bool:
    if start < end:
        return start <= minute < end
    return minute >= start or minute < end  # 跨日区间


def _ranges(standard: dict[str, Any], key: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for raw in standard.get(key, []):
        parsed = parse_range(str(raw), allow_overnight=True)
        if parsed is not None:
            ranges.append(parsed)
    return ranges


def classify_minute(minute: int, standard: dict[str, Any]) -> str:
    """按当前口径判断某一分钟属于峰、谷还是平段。"""
    for start, end in _ranges(standard, "峰时段"):
        if _minute_in_range(minute, start, end):
            return "峰"
    for start, end in _ranges(standard, "谷时段"):
        if _minute_in_range(minute, start, end):
            return "谷"
    return "平"


def split_record(电量: float, start: int, end: int, standard: dict[str, Any]) -> dict[str, Any]:
    """把一条补录电量按区间内落在峰/谷/平段的分钟数比例拆分。"""
    counts = {"峰": 0, "谷": 0, "平": 0}
    for minute in range(start, end):
        counts[classify_minute(minute, standard)] += 1
    total = end - start
    峰 = round(电量 * counts["峰"] / total, 2)
    谷 = round(电量 * counts["谷"] / total, 2)
    平 = round(电量 - 峰 - 谷, 2)
    return {
        "峰电量": 峰,
        "谷电量": 谷,
        "平电量": 平,
        "峰分钟": counts["峰"],
        "谷分钟": counts["谷"],
        "平分钟": counts["平"],
    }


def dominant_period(峰: int, 谷: int, 平: int) -> str:
    if 峰 >= 谷 and 峰 >= 平:
        return "峰"
    if 谷 >= 平:
        return "谷"
    return "平"


def idempotency_key(point_id: int, 采集日期: str, 时段: str, 电量: float) -> str:
    raw = f"{point_id}|{采集日期}|{时段}|{电量}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


class EnergyService:
    def __init__(self) -> None:
        self._data = self._load()

    # ---------- 持久化 ----------
    def _load(self) -> dict[str, Any]:
        if DATA_FILE.exists():
            try:
                data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
                if self._valid(data):
                    return data
            except (json.JSONDecodeError, OSError):
                pass
        return self._seed_data()

    @staticmethod
    def _valid(data: dict[str, Any]) -> bool:
        return all(k in data for k in ("points", "records", "standards", "snapshots"))

    @staticmethod
    def _seed_data() -> dict[str, Any]:
        data: dict[str, Any] = {
            "points": [dict(p) for p in ENERGY_SEED["points"]],
            "records": [dict(r) for r in ENERGY_SEED["records"]],
            "standards": [dict(s) for s in ENERGY_SEED["standards"]],
            "snapshots": [],
        }
        standard = data["standards"][-1]
        for record in data["records"]:
            start, end = parse_range(str(record["时段"]), allow_overnight=False)
            if start is None or end is None:
                continue
            split = split_record(float(record["电量"]), start, end, standard)
            record.update(split)
            record["时段分类"] = dominant_period(split["峰分钟"], split["谷分钟"], split["平分钟"])
            record["口径版本"] = standard["version"]
        snapshot = {
            "id": 1,
            "口径版本": standard["version"],
            "重算时间": str(standard.get("生效时间") or _now()),
            "触发": "初始口径",
            "结果": EnergyService._compute_results(data),
        }
        data["snapshots"].append(snapshot)
        return data

    def _save(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        DATA_FILE.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---------- 点位 ----------
    def list_points(self) -> list[dict[str, Any]]:
        return list(self._data["points"])

    def find_point(self, point_id: int) -> dict[str, Any] | None:
        for point in self._data["points"]:
            if int(point.get("id", 0)) == point_id:
                return point
        return None

    def create_point(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        编号 = str(values.get("点位编号") or "").strip()
        名称 = str(values.get("点位名称") or "").strip()
        if not 编号 or not 名称:
            return None, "点位编号与点位名称必填"
        try:
            上限 = float(values.get("计量上限"))
        except (TypeError, ValueError):
            return None, "计量上限必须是数字"
        if 上限 <= 0:
            return None, "计量上限必须为正数"
        if any(str(p.get("点位编号")) == 编号 for p in self._data["points"]):
            return None, f"点位编号 {编号} 已存在"
        point = {
            "id": max((int(p.get("id", 0)) for p in self._data["points"]), default=0) + 1,
            "点位编号": 编号,
            "点位名称": 名称,
            "计量上限": 上限,
            "倍率": float(values.get("倍率") or 1),
            "启用": True,
        }
        self._data["points"].append(point)
        self._save()
        return point, "计量点位已登记"

    # ---------- 补录 ----------
    def list_records(self, point_id: int | None = None, period: str | None = None) -> list[dict[str, Any]]:
        rows = list(self._data["records"])
        if point_id is not None:
            rows = [r for r in rows if int(r.get("point_id", 0)) == point_id]
        if period:
            rows = [r for r in rows if r.get("时段分类") == period]
        return rows

    def create_record(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str, bool]:
        try:
            point_id = int(values.get("point_id"))
        except (TypeError, ValueError):
            return None, "计量点位无效", False
        point = self.find_point(point_id)
        if point is None:
            return None, f"计量点位 {point_id} 不存在", False
        if not point.get("启用", True):
            return None, "该计量点位已停用，无法补录", False
        try:
            电量 = float(values.get("电量"))
        except (TypeError, ValueError):
            return None, "用电量必须是数字", False
        if 电量 <= 0:
            return None, "用电量必须为正数", False
        if 电量 > float(point["计量上限"]):
            return None, f"用电量 {电量:g} 超过该点位计量上限 {float(point['计量上限']):g}，记录已拦下", False
        采集日期 = str(values.get("采集日期") or "").strip()
        if not DATE_RE.fullmatch(采集日期):
            return None, "采集日期无效，应为 YYYY-MM-DD", False
        try:
            datetime.strptime(采集日期, "%Y-%m-%d")
        except ValueError:
            return None, "采集日期不是有效日期", False
        时段 = str(values.get("时段") or "").strip()
        parsed = parse_range(时段, allow_overnight=False)
        if parsed is None:
            return None, "时段填写无效，应为 HH:MM-HH:MM 且在当日范围内", False
        start, end = parsed
        key = idempotency_key(point_id, 采集日期, 时段, 电量)
        for record in self._data["records"]:
            if record.get("幂等键") == key:
                return record, "同一条补录已存在，未重复录入", True
        standard = self.current_standard()
        split = split_record(电量, start, end, standard)
        record = {
            "id": max((int(r.get("id", 0)) for r in self._data["records"]), default=0) + 1,
            "point_id": point_id,
            "电量": 电量,
            "采集日期": 采集日期,
            "时段": 时段,
            "幂等键": key,
            "登记时间": _now(),
            "口径版本": standard["version"],
            **split,
            "时段分类": dominant_period(split["峰分钟"], split["谷分钟"], split["平分钟"]),
        }
        self._data["records"].append(record)
        self._save()
        return record, "补录成功", False

    # ---------- 口径 ----------
    def current_standard(self) -> dict[str, Any]:
        return self._data["standards"][-1]

    def list_standards(self) -> list[dict[str, Any]]:
        return list(self._data["standards"])

    def adjust_standard(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        峰时段 = [str(x).strip() for x in values.get("峰时段", []) if str(x).strip()]
        谷时段 = [str(x).strip() for x in values.get("谷时段", []) if str(x).strip()]
        说明 = str(values.get("调整说明") or "").strip()
        for label, ranges in (("峰时段", 峰时段), ("谷时段", 谷时段)):
            for raw in ranges:
                if parse_range(raw, allow_overnight=True) is None:
                    return None, f"{label} {raw} 填写无效，应为 HH:MM-HH:MM"
        if not 峰时段 and not 谷时段:
            return None, "峰时段与谷时段不能同时为空"
        # 先把当前口径下的结果冻结为历史结果，再按新口径重算
        self._freeze_snapshot(self.current_standard(), "口径调整前结果")
        version = max(int(s.get("version", 0)) for s in self._data["standards"]) + 1
        standard = {
            "version": version,
            "峰时段": 峰时段,
            "谷时段": 谷时段,
            "生效时间": _now(),
            "调整说明": 说明 or f"口径调整至 v{version}",
        }
        self._data["standards"].append(standard)
        self._apply_standard(standard)
        self._save()
        return standard, f"峰谷时段口径已调整至 v{version}，总量已按新口径重算"

    def recompute(self) -> dict[str, Any]:
        standard = self.current_standard()
        self._apply_standard(standard)
        self._freeze_snapshot(standard, "手动重算")
        self._save()
        return standard

    def _apply_standard(self, standard: dict[str, Any]) -> None:
        for record in self._data["records"]:
            start, end = parse_range(str(record["时段"]), allow_overnight=False)
            if start is None or end is None:
                continue
            split = split_record(float(record["电量"]), start, end, standard)
            record.update(split)
            record["时段分类"] = dominant_period(split["峰分钟"], split["谷分钟"], split["平分钟"])
            record["口径版本"] = standard["version"]

    def _freeze_snapshot(self, standard: dict[str, Any], trigger: str) -> None:
        snapshot = {
            "id": max((int(s.get("id", 0)) for s in self._data["snapshots"]), default=0) + 1,
            "口径版本": standard["version"],
            "重算时间": _now(),
            "触发": trigger,
            "结果": self._compute_results(self._data),
        }
        self._data["snapshots"].append(snapshot)

    def list_snapshots(self) -> list[dict[str, Any]]:
        return sorted(self._data["snapshots"], key=lambda s: int(s.get("id", 0)), reverse=True)

    # ---------- 结果 ----------
    @staticmethod
    def _compute_results(data: dict[str, Any]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for point in data["points"]:
            rows = [r for r in data["records"] if int(r.get("point_id", 0)) == int(point["id"])]
            if not rows:
                results.append({
                    "point_id": point["id"],
                    "点位编号": point.get("点位编号"),
                    "点位名称": point.get("点位名称"),
                    "计量上限": point.get("计量上限"),
                    "有数据": False,
                    "峰电量": None,
                    "谷电量": None,
                    "平电量": None,
                    "总电量": None,
                    "记录数": 0,
                })
                continue
            峰 = round(sum(float(r.get("峰电量", 0)) for r in rows), 2)
            谷 = round(sum(float(r.get("谷电量", 0)) for r in rows), 2)
            平 = round(sum(float(r.get("平电量", 0)) for r in rows), 2)
            results.append({
                "point_id": point["id"],
                "点位编号": point.get("点位编号"),
                "点位名称": point.get("点位名称"),
                "计量上限": point.get("计量上限"),
                "有数据": True,
                "峰电量": 峰,
                "谷电量": 谷,
                "平电量": 平,
                "总电量": round(峰 + 谷 + 平, 2),
                "记录数": len(rows),
            })
        return results

    def results(self) -> dict[str, Any]:
        point_results = self._compute_results(self._data)
        有数据 = [r for r in point_results if r["有数据"]]
        峰 = round(sum(r["峰电量"] for r in 有数据), 2)
        谷 = round(sum(r["谷电量"] for r in 有数据), 2)
        平 = round(sum(r["平电量"] for r in 有数据), 2)
        return {
            "点位结果": point_results,
            "汇总": {
                "峰电量": 峰,
                "谷电量": 谷,
                "平电量": 平,
                "总电量": round(峰 + 谷 + 平, 2),
                "台账条数": len(self._data["records"]),
                "点位数": len(self._data["points"]),
                "采集点位数": len(有数据),
                "口径版本": int(self.current_standard()["version"]),
            },
            "当前口径": self.current_standard(),
        }
