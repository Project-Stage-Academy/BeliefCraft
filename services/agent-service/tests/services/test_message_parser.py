from app.services.message_parser import MessageParser
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


class TestMessageParserExtractToolExecutions:
    def test_extracts_matching_tool_calls_and_messages(self) -> None:
        messages = [
            AIMessage(
                content="",
                tool_calls=[{"id": "call_1", "name": "get_weather", "args": {"loc": "Rivne"}}],
            ),
            ToolMessage(tool_call_id="call_1", content="Sunny", artifact={"temp": 20}),
        ]
        executions = MessageParser.extract_tool_executions(messages)

        assert len(executions) == 1
        assert executions[0]["tool_name"] == "get_weather"
        assert executions[0]["arguments"] == {"loc": "Rivne"}
        assert executions[0]["result"] == {"temp": 20}
        assert executions[0]["error"] is None

    def test_handles_missing_tool_message(self) -> None:
        messages = [
            AIMessage(
                content="",
                tool_calls=[{"id": "call_2", "name": "missing_tool", "args": {}}],
            )
        ]
        executions = MessageParser.extract_tool_executions(messages)

        assert len(executions) == 1
        assert executions[0]["result"] is None
        assert executions[0]["error"] is None

    def test_extracts_error_status(self) -> None:
        messages = [
            AIMessage(
                content="",
                tool_calls=[{"id": "call_3", "name": "failing_tool", "args": {}}],
            ),
            ToolMessage(tool_call_id="call_3", content="API timeout", status="error"),
        ]
        executions = MessageParser.extract_tool_executions(messages)

        assert executions[0]["result"] == "API timeout"
        assert executions[0]["error"] == "API timeout"


class TestMessageParserBuildIterationHistory:
    def test_builds_history_with_thoughts_and_actions(self) -> None:
        messages = [
            AIMessage(
                content="<thinking>I need weather</thinking>",
                tool_calls=[{"id": "c1", "name": "weather", "args": {}}],
            ),
            ToolMessage(tool_call_id="c1", content="Rain"),
            AIMessage(content="<thinking>It is raining</thinking>"),
        ]

        # Change `messages` to `{"messages": messages}`
        history = MessageParser.build_iteration_history({"messages": messages})

        assert len(history) == 2
        assert history[0]["iteration"] == 1
        assert history[0]["thought"] == "I need weather"
        assert len(history[0]["actions"]) == 1
        assert history[0]["actions"][0]["observation"] == "Rain"

        assert history[1]["iteration"] == 2
        assert history[1]["thought"] == "It is raining"
        assert len(history[1]["actions"]) == 0

    def test_respects_include_trace_meta_flag(self) -> None:
        messages = [
            AIMessage(
                content="",
                tool_calls=[{"id": "c1", "name": "db", "args": {}}],
            ),
            ToolMessage(tool_call_id="c1", content="", artifact={"data": "x", "meta": "y"}),
        ]

        history_without_meta = MessageParser.build_iteration_history(
            {"messages": messages}, include_trace_meta=False
        )
        assert history_without_meta[0]["actions"][0]["observation"] == "x"

        history_with_meta = MessageParser.build_iteration_history(
            {"messages": messages}, include_trace_meta=True
        )
        assert history_with_meta[0]["actions"][0]["observation"] == {"data": "x", "meta": "y"}

    def test_formats_error_observation_correctly(self) -> None:
        messages = [
            AIMessage(content="", tool_calls=[{"id": "c1", "name": "err_tool", "args": {}}]),
            ToolMessage(tool_call_id="c1", content="Failed", status="error"),
        ]
        history = MessageParser.build_iteration_history({"messages": messages})

        assert history[0]["actions"][0]["observation"] == {"error": "Failed"}

    def test_message_history_ignores_stale_recorded_tool_calls(self) -> None:
        messages = [
            AIMessage(
                content="<thinking>Use live tool history</thinking>",
                tool_calls=[{"id": "c1", "name": "weather", "args": {"loc": "Rivne"}}],
            ),
            ToolMessage(tool_call_id="c1", content="", artifact={"temp": 20}),
        ]
        stale_tool_calls = [
            {
                "tool_name": "stale_tool",
                "arguments": {"loc": "Kyiv"},
                "result": {"temp": -5},
            }
        ]

        history = MessageParser.build_iteration_history(
            {"messages": messages, "tool_calls": stale_tool_calls}
        )

        assert history[0]["actions"][0]["tool"] == "weather"
        assert history[0]["actions"][0]["arguments"] == {"loc": "Rivne"}
        assert history[0]["actions"][0]["observation"] == {"temp": 20}


class TestMessageParserHelpers:
    def test_find_tool_message(self) -> None:
        m1 = ToolMessage(tool_call_id="t1", content="a")
        m2 = ToolMessage(tool_call_id="t2", content="b")

        assert MessageParser._find_tool_message([m1, m2], "t2") == m2
        assert MessageParser._find_tool_message([m1], "t3") is None
        assert MessageParser._find_tool_message([HumanMessage(content="hi")], "t1") is None

    def test_extract_payload(self) -> None:
        # Artifact takes precedence
        tm1 = ToolMessage(tool_call_id="1", content="text", artifact="obj")
        assert MessageParser._extract_payload(tm1) == ("obj", None)

        # Fallback to content
        tm2 = ToolMessage(tool_call_id="2", content="text")
        assert MessageParser._extract_payload(tm2) == ("text", None)

        # Error extraction
        tm3 = ToolMessage(tool_call_id="3", content="err", status="error")
        assert MessageParser._extract_payload(tm3) == ("err", "err")

        # None input
        assert MessageParser._extract_payload(None) == (None, None)

    def test_format_thought_content(self) -> None:
        assert MessageParser._format_thought_content("<thinking>  plan  </thinking>") == "plan"
        assert MessageParser._format_thought_content("No tags here") == "No tags here"
        assert MessageParser._format_thought_content(None) == "None"
        assert (
            MessageParser._format_thought_content("<thinking>multi\nline</thinking>")
            == "multi\nline"
        )
