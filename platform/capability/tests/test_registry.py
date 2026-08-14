"""注册表与入参校验测试。"""

from dataclasses import dataclass

import pytest
from platform_capability import Registry, capability, coerce_input
from platform_contracts import ServiceError


@dataclass
class _EchoIn:
    text: str
    times: int = 1


@pytest.fixture()
def registry() -> Registry:
    reg = Registry("notes")

    @capability(reg, name="echo", description="回显文本", input_model=_EchoIn)
    def echo(data: _EchoIn) -> dict:
        return {"echo": data.text * data.times}

    return reg


class TestRegistry:
    def test_register_and_get(self, registry) -> None:
        assert "echo" in registry
        assert registry.get("echo").description == "回显文本"
        assert registry.names() == ["echo"]

    def test_duplicate_rejected(self, registry) -> None:
        with pytest.raises(ServiceError) as exc:
            registry.register(registry.get("echo"))
        assert exc.value.body.code == "NOTES.CONFLICT"
        assert exc.value.http_status == 409

    def test_unknown_get(self, registry) -> None:
        with pytest.raises(ServiceError) as exc:
            registry.get("nope")
        assert exc.value.body.code == "NOTES.NOT_FOUND"
        assert exc.value.http_status == 404

    def test_invalid_name_rejected(self, registry) -> None:
        with pytest.raises(ServiceError, match="snake_case"):
            capability(registry, name="Bad-Name", description="x")(lambda: None)

    def test_merge(self, registry) -> None:
        other = Registry("notes-books")

        @capability(other, name="add_book", description="加书")
        def add_book() -> dict:
            return {}

        registry.merge(other)
        assert registry.names() == ["add_book", "echo"]
        with pytest.raises(ServiceError):
            registry.merge(other)  # 再合一次 → 冲突


class TestCoerceInput:
    def test_ok_with_defaults(self) -> None:
        obj = coerce_input(_EchoIn, {"text": "hi"}, domain="notes")
        assert obj == _EchoIn(text="hi", times=1)

    def test_unknown_key_rejected(self) -> None:
        with pytest.raises(ServiceError) as exc:
            coerce_input(_EchoIn, {"text": "a", "evil": 1}, domain="notes")
        assert exc.value.body.code == "NOTES.INVALID_INPUT"
        assert exc.value.http_status == 400

    def test_missing_required(self) -> None:
        with pytest.raises(ServiceError, match="缺少必填入参: text"):
            coerce_input(_EchoIn, {}, domain="notes")

    def test_wrong_primitive_type(self) -> None:
        with pytest.raises(ServiceError, match="应为 str"):
            coerce_input(_EchoIn, {"text": 1}, domain="notes")
        with pytest.raises(ServiceError, match="应为 int"):
            coerce_input(_EchoIn, {"text": "a", "times": True}, domain="notes")

    def test_no_model_passthrough(self) -> None:
        assert coerce_input(None, {"a": 1}, domain="notes") == {"a": 1}

    def test_non_object_rejected(self) -> None:
        with pytest.raises(ServiceError, match="JSON 对象"):
            coerce_input(_EchoIn, ["x"], domain="notes")
