import importlib
import sys
from types import ModuleType


def _install_fake_tiktoken() -> None:
    tiktoken_stub = ModuleType("tiktoken")

    class DummyEncoding:
        def encode(self, text: str):
            return text.split()

    def encoding_for_model(model: str) -> DummyEncoding:
        return DummyEncoding()

    tiktoken_stub.encoding_for_model = encoding_for_model
    sys.modules["tiktoken"] = tiktoken_stub


def test_count_tokens_in_folder_counts_all_files(tmp_path, monkeypatch):
    _install_fake_tiktoken()
    if "code_translation.count_tokens" in sys.modules:
        del sys.modules["code_translation.count_tokens"]

    count_tokens = importlib.import_module("code_translation.count_tokens")

    (tmp_path / "a.txt").write_text("one two three", encoding="utf-8")
    (tmp_path / "b.txt").write_text("four five", encoding="utf-8")

    total = count_tokens.count_tokens_in_folder(str(tmp_path))

    assert total == 5

