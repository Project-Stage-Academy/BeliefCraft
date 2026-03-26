from common.schemas.common import Pagination, ToolResultMeta, build_tool_meta


def test_tool_result_meta_defaults_trace_count_to_count() -> None:
    meta = ToolResultMeta(count=4)

    assert meta.count == 4
    assert meta.trace_count == 4


def test_build_tool_meta_preserves_pagination_and_extra_fields() -> None:
    meta = build_tool_meta(
        count=2,
        pagination=Pagination(limit=50, offset=10),
        filters={"warehouse_id": "wh-1"},
    )

    dumped = meta.model_dump(mode="json")

    assert dumped["count"] == 2
    assert dumped["trace_count"] == 2
    assert dumped["pagination"] == {"limit": 50, "offset": 10}
    assert dumped["filters"] == {"warehouse_id": "wh-1"}
