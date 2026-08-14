"""semver 解析与约束匹配(设计 002 §8:插件 depends_on 用 ^ / ~ 约束)。

不引入第三方依赖:packaging 不支持 npm 的 ^(caret)语义,实现 MVP 所需的
^ / ~ / 精确 / >= 子集即可覆盖内置资源与插件依赖解析。
"""

import re
from dataclasses import dataclass

_SEMVER_RE = re.compile(
    r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)"
    r"(?:-(?P<pre>[0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$"
)


@dataclass(frozen=True)
class Version:
    """semver 版本号(major.minor.patch,可选 prerelease)。"""

    major: int
    minor: int
    patch: int
    prerelease: str | None = None

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        return f"{base}-{self.prerelease}" if self.prerelease else base

    def __lt__(self, other: "Version") -> bool:
        core = (self.major, self.minor, self.patch)
        other_core = (other.major, other.minor, other.patch)
        if core != other_core:
            return core < other_core
        # 同核心版本下:prerelease 优先于正式版
        if self.prerelease is None:
            return False  # 正式版 > 任何预发布
        if other.prerelease is None:
            return True  # 预发布 < 正式版
        return self.prerelease < other.prerelease


@dataclass(frozen=True)
class VersionRange:
    """左闭右开区间 [min, max);None 表示无边界。"""

    min: Version | None = None
    max: Version | None = None


def parse(version: str) -> Version:
    """解析完整 semver,非法输入抛 ValueError。"""
    m = _SEMVER_RE.match(version)
    if m is None:
        raise ValueError(f"非法 semver: {version!r}")
    return Version(
        major=int(m.group("major")),
        minor=int(m.group("minor")),
        patch=int(m.group("patch")),
        prerelease=m.group("pre"),
    )


def _bump(v: Version, *, major: bool = False, minor: bool = False) -> Version:
    """返回比 v 高一档的版本:major 加一 / minor 加一 / patch 加一。"""
    if major:
        return Version(v.major + 1, 0, 0)
    if minor:
        return Version(v.major, v.minor + 1, 0)
    return Version(v.major, v.minor, v.patch + 1)


def _partial_parse(body: str) -> tuple[Version, int]:
    """解析可缺省组件(1 / 1.2 / 1.2.3),缺省补 0;返回 (Version, 提供段数)。"""
    parts = body.split(".")
    if not 1 <= len(parts) <= 3 or not all(p.isdigit() for p in parts):
        raise ValueError(f"非法版本约束: {body!r}")
    nums = [int(p) for p in parts]
    v = Version(
        major=nums[0],
        minor=nums[1] if len(nums) > 1 else 0,
        patch=nums[2] if len(nums) > 2 else 0,
    )
    return v, len(nums)


def parse_constraint(constraint: str) -> VersionRange:
    """解析 ^ / ~ / 精确 / >= 约束为区间;空或 * 表示任意。"""
    c = constraint.strip()
    if not c or c == "*":
        return VersionRange()
    if c.startswith("^"):
        return _caret_range(c[1:])
    if c.startswith("~"):
        return _tilde_range(c[1:])
    if c.startswith(">="):
        return VersionRange(min=parse(c[2:].strip()))
    # 精确版本
    v = parse(c)
    return VersionRange(min=v, max=_bump(v))


def _caret_range(body: str) -> VersionRange:
    """npm caret:首个非零段决定上界;全零时按提供的最后一段抬升。

    ^1 -> <2.0.0;^0.2 -> <0.3.0;^0.0.3 -> <0.0.4;^0.0 -> <0.1.0;^0 -> <1.0.0。
    """
    v, comps = _partial_parse(body)
    if v.major > 0:
        return VersionRange(min=v, max=_bump(v, major=True))
    if v.minor > 0:
        return VersionRange(min=v, max=_bump(v, minor=True))
    if comps >= 3:  # ^0.0.x
        return VersionRange(min=v, max=_bump(v))
    if comps == 2:  # ^0.0
        return VersionRange(min=v, max=_bump(v, minor=True))
    return VersionRange(min=v, max=_bump(v, major=True))  # ^0


def _tilde_range(body: str) -> VersionRange:
    """npm tilde:提供 minor 就锁 minor,否则锁 major。~1.2 -> <1.3.0;~1 -> <2.0.0。"""
    v, comps = _partial_parse(body)
    if comps >= 2:
        return VersionRange(min=v, max=_bump(v, minor=True))
    return VersionRange(min=v, max=_bump(v, major=True))


def version_matches(version: Version, rng: VersionRange) -> bool:
    """版本是否落在约束区间内。"""
    if rng.min is not None and version < rng.min:
        return False
    return rng.max is None or version < rng.max


def resolve_highest(versions: list[str], constraint: str | None) -> str | None:
    """从版本列表取满足约束的最高版本;无约束取最高;无匹配返回 None。

    输入假定为合法 semver(注册表写入时已校验)。
    """
    if not versions:
        return None
    rng = parse_constraint(constraint or "")
    parsed = [parse(v) for v in versions]
    candidates = sorted(v for v in parsed if version_matches(v, rng))
    return str(candidates[-1]) if candidates else None
