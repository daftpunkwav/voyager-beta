"""健康探测、错误构造助手、进程内监控。"""

from platform_health.errors import queue_full, unavailable
from platform_health.monitor import HealthMonitor, Probe

__all__ = ["HealthMonitor", "Probe", "queue_full", "unavailable"]
