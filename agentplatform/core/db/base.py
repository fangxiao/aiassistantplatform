"""SQLAlchemy 声明式基类。

004 数据模型所有 ORM 模型继承自 Base;业务表由各里程碑的迁移建立。
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """平台 ORM 基类。"""
