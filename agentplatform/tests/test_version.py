"""版本解析与约束匹配测试(设计 002 §8:depends_on 用 ^ / ~ 约束)。

覆盖:parse / 比较 / ^ / ~ / >= / 精确 / 空约束 / 最高版本解析。
"""

import pytest

from agentplatform.core.registry.version import (
    parse,
    parse_constraint,
    resolve_highest,
    version_matches,
)


class TestParse:
    def test_full_semver(self) -> None:
        assert str(parse("1.2.3")) == "1.2.3"

    def test_prerelease(self) -> None:
        assert str(parse("1.2.3-alpha")) == "1.2.3-alpha"

    def test_multi_digit(self) -> None:
        assert str(parse("10.20.30")) == "10.20.30"

    @pytest.mark.parametrize("bad", ["abc", "1.2", "1", "1.2.3.4", ""])
    def test_invalid_raises(self, bad: str) -> None:
        with pytest.raises(ValueError):
            parse(bad)


class TestCompare:
    def test_patch_order(self) -> None:
        assert parse("1.2.3") < parse("1.2.4")

    def test_major_order(self) -> None:
        assert parse("1.9.9") < parse("2.0.0")

    def test_numeric_not_lexicographic(self) -> None:
        assert parse("1.9.0") < parse("1.10.0")

    def test_prerelease_before_release(self) -> None:
        assert parse("1.2.3-alpha") < parse("1.2.3")


class TestConstraints:
    def test_exact_match(self) -> None:
        assert version_matches(parse("1.2.3"), parse_constraint("1.2.3"))
        assert not version_matches(parse("1.2.4"), parse_constraint("1.2.3"))

    @pytest.mark.parametrize(
        ("constraint", "ok", "bad"),
        [
            ("^1.0", "1.2.3", "2.0.0"),
            ("^1.0.0", "1.9.9", "2.0.0"),
            ("^0.2", "0.2.9", "0.3.0"),
            ("^0.2.3", "0.2.9", "0.3.0"),
            ("^0.0.3", "0.0.3", "0.0.4"),
            ("^0.0", "0.0.5", "0.1.0"),
        ],
    )
    def test_caret(self, constraint: str, ok: str, bad: str) -> None:
        rng = parse_constraint(constraint)
        assert version_matches(parse(ok), rng)
        assert not version_matches(parse(bad), rng)

    @pytest.mark.parametrize(
        ("constraint", "ok", "bad"),
        [
            ("~1.2", "1.2.9", "1.3.0"),
            ("~1.2.3", "1.2.9", "1.3.0"),
            ("~1", "1.9.0", "2.0.0"),
        ],
    )
    def test_tilde(self, constraint: str, ok: str, bad: str) -> None:
        rng = parse_constraint(constraint)
        assert version_matches(parse(ok), rng)
        assert not version_matches(parse(bad), rng)

    def test_gte(self) -> None:
        rng = parse_constraint(">=1.2.0")
        assert version_matches(parse("2.0.0"), rng)
        assert not version_matches(parse("1.1.9"), rng)

    def test_empty_is_any(self) -> None:
        rng = parse_constraint("")
        assert version_matches(parse("0.0.1"), rng)
        assert version_matches(parse("9.9.9"), rng)


class TestResolveHighest:
    def test_no_constraint_picks_latest(self) -> None:
        versions = ["1.0.0", "1.5.0", "2.0.0"]
        assert resolve_highest(versions, None) == "2.0.0"

    def test_caret_picks_highest_in_range(self) -> None:
        versions = ["1.0.0", "1.5.0", "2.0.0"]
        assert resolve_highest(versions, "^1.0") == "1.5.0"

    def test_returns_none_when_none_match(self) -> None:
        versions = ["2.0.0", "3.0.0"]
        assert resolve_highest(versions, "^1.0") is None

    def test_empty_versions(self) -> None:
        assert resolve_highest([], "^1.0") is None
