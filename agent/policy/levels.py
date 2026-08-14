"""行动分级(§9.9):L0 静默 / L1 提示 / L2 确认。配置只能更严,不能放宽。"""

from enum import IntEnum


class Level(IntEnum):
    L0_SILENT = 0  # 静默执行,只入审计
    L1_NOTIFY = 1  # 执行并提示用户
    L2_CONFIRM = 2  # 必须先经用户确认
