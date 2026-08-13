"""
SQLite 遗留 schema 同步 —— 已由 Alembic 接管。

保留本模块仅供手动迁移旧库参考；应用启动不再调用。
历史行为：create_all 不会给已有表加列，曾在此 ALTER + 启动时 UPDATE。
"""

# 故意留空：新部署走 alembic upgrade；旧库请执行 `alembic upgrade head`。
