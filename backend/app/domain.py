"""门槛规则：

- 改「熬煮中」：该锅须有未作废筛网牌，且最新一张目数为 40 或 60。
- 改「已出胶」：最近一次煮胶峰值须 ≥ 90℃，与筛网目数无关。
"""

from typing import Optional

from app.models import Kettle, ScreenTag

MIN_PEAK = 90.0
ALLOWED_MESH = (40, 60)


class RuleError(ValueError):
    pass


def latest_peak(kettle: Kettle) -> float | None:
    if not kettle.cooks:
        return None
    latest = max(kettle.cooks, key=lambda c: c.taken_at)
    return latest.peak_temp_c


def assert_can_set_status(
    kettle: Kettle,
    new_status: str,
    active_screen: Optional[ScreenTag] = None,
) -> None:
    allowed = {Kettle.STATUS_COLD, Kettle.STATUS_BOILING, Kettle.STATUS_DRAWN}
    if new_status not in allowed:
        raise RuleError(f"无效状态：{new_status}")
    if new_status == Kettle.STATUS_BOILING:
        if active_screen is None:
            raise RuleError("该锅没有未作废的筛网牌，须先挂 40 或 60 目牌才能改熬煮中")
        if active_screen.mesh not in ALLOWED_MESH:
            raise RuleError(
                f"最新筛网牌为 {active_screen.mesh} 目，只认 40 或 60 目，不能改熬煮中"
            )
        return
    if new_status == Kettle.STATUS_DRAWN:
        peak = latest_peak(kettle)
        if peak is None:
            raise RuleError("该锅尚无煮胶峰值，不能出胶")
        if peak < MIN_PEAK:
            raise RuleError(f"最近峰值 {peak}℃ 低于 {MIN_PEAK:.0f}℃，不能出胶")
