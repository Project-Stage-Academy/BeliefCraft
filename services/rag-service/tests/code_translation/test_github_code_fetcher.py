import code_translation.github_code_fetcher as github_code_fetcher
from code_translation.github_code_fetcher import GitHubCodeFetcher


def test_github_code_fetcher_collects_dependencies(monkeypatch):
    main_source = """
from ch02 import helper

def main():
    return helper()
"""
    dep_source = """
def helper():
    return 42
"""

    def fake_fetch(self, raw_url: str) -> str:
        if raw_url.endswith("/ch01.py"):
            return main_source
        if raw_url.endswith("/ch02.py"):
            return dep_source
        raise ValueError("unexpected url")

    monkeypatch.setattr(github_code_fetcher.GitHubSourceFetcher, "fetch_source", fake_fetch)

    fetcher = GitHubCodeFetcher("https://github.com/user/repo")
    result = fetcher.get_translated_python_code("01")

    assert "# --- ch02.py :: helper ---" in result
    assert "def helper" in result
    assert "# --- main file ---" in result
    assert "def main" in result

