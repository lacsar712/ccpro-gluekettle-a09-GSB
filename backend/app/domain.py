"""熬锅门槛：转熬煮中看最新未作废筛网牌（40/60 目）；已出胶只看峰值 ≥ 90℃。"""

from app.models import Kettle, SieveTag

MIN_PEAK = 90.0
ALLOWED_MESH = (40, 60)


class RuleError(ValueError):
    pass


def latest_peak(kettle: Kettle) -> float | None:
    if not kettle.cooks:
        return None
    latest = max(kettle.cooks, key=lambda c: c.taken_at)
    return latest.peak_temp_c


def latest_sieve_tag(kettle: Kettle) -> SieveTag | None:
    """挂出时刻最晚的一张未作废筛网牌；没有未作废牌则为 None。"""
    live = [t for t in (kettle.sieve_tags or []) if t.voided_at is None]
    if not live:
        return None
    return max(live, key=lambda t: t.hung_at)


def assert_can_set_status(kettle: Kettle, new_status: str) -> None:
    allowed = {Kettle.STATUS_COLD, Kettle.STATUS_BOILING, Kettle.STATUS_DRAWN}
    if new_status not in allowed:
        raise RuleError(f"无效状态：{new_status}")
    if new_status == Kettle.STATUS_BOILING:
        tag = latest_sieve_tag(kettle)
        if tag is None:
            raise RuleError("该锅没有未作废的筛网牌，不能转熬煮中")
        if tag.mesh not in ALLOWED_MESH:
            raise RuleError(
                f"最新未作废筛网牌为 {tag.mesh} 目，须为 40 或 60 目，不能转熬煮中"
            )
    if new_status == Kettle.STATUS_DRAWN:
        # 已出胶只认峰值门槛，筛网目数不掺进来。
        peak = latest_peak(kettle)
        if peak is None:
            raise RuleError("该锅尚无煮胶峰值，不能出胶")
        if peak < MIN_PEAK:
            raise RuleError(f"最近峰值 {peak}℃ 低于 {MIN_PEAK:.0f}℃，不能出胶")
