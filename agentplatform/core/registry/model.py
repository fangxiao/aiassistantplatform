"""skill/tool 注册表 ORM 模型(设计 004 §skill_tools / 002 §3)。

版本化语义(002 §8):同一资源 id 可登记多个 semver 版本,插件 depends_on
用 ^ / ~ 约束解析,故主键为 (id, version) 复合主键。
owner_id 为开发者标识,buildin 为 null;M1 引入 users 表后改为外键。
"""

from enum import Enum

from sqlalchemy import JSON, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from agentplatform.core.db.base import Base


class SkillToolKind(str, Enum):
    """资源类型:tool 为确定性编程接口,skill 为能力/知识单元。"""

    tool = "tool"
    skill = "skill"


class SkillToolSource(str, Enum):
    """来源:builtin 平台内置 / shared 公共池 / private 插件私有。"""

    builtin = "builtin"
    shared = "shared"
    private = "private"


class SkillTool(Base):
    """注册表中的 skill/tool 资源(一个 id 可有多个版本)。"""

    __tablename__ = "skill_tools"

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # 如 tool:pdf_parse
    version: Mapped[str] = mapped_column(Text, primary_key=True)  # semver
    kind: Mapped[SkillToolKind] = mapped_column(
        SAEnum(SkillToolKind, name="skill_tool_kind"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[SkillToolSource] = mapped_column(
        SAEnum(SkillToolSource, name="skill_tool_source"), nullable=False
    )
    owner_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    schema_: Mapped[dict] = mapped_column(
        "schema", JSON().with_variant(JSONB, "postgresql"), nullable=False
    )
    impl_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
