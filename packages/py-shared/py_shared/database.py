"""共享数据库基类(api_backend / agent_core 共用)。"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
