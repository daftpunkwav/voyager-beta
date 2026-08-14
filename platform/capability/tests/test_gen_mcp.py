"""MCP 生成测试:JSON Schema 推导与工具描述(纯函数,不依赖 MCP SDK)。"""

from dataclasses import dataclass

from platform_capability import Registry, build_tool_specs, capability, dataclass_to_json_schema


@dataclass
class _In:
    text: str
    count: int = 3
    ratio: float = 0.5
    flag: bool = False
    tags: list | None = None
    meta: dict | None = None


class TestJsonSchema:
    def test_primitive_mapping(self) -> None:
        schema = dataclass_to_json_schema(_In)
        props = schema["properties"]
        assert props["text"] == {"type": "string"}
        assert props["count"] == {"type": "integer", "default": 3}
        assert props["ratio"]["type"] == "number"
        assert props["flag"]["type"] == "boolean"
        assert props["tags"]["type"] == "array"
        assert props["meta"]["type"] == "object"

    def test_required_only_for_no_default(self) -> None:
        assert dataclass_to_json_schema(_In)["required"] == ["text"]


class TestToolSpecs:
    def test_specs_shape(self) -> None:
        reg = Registry("notes")

        @capability(reg, name="echo", description="回显文本", input_model=_In)
        def echo(data: _In) -> dict:
            return {}

        @capability(reg, name="ping", description="无入参")
        def ping() -> dict:
            return {}

        specs = build_tool_specs(reg)
        assert [s["name"] for s in specs] == ["echo", "ping"]
        assert specs[0]["inputSchema"]["properties"]["text"] == {"type": "string"}
        assert specs[1]["inputSchema"] == {
            "type": "object",
            "properties": {},
            "required": [],
        }
