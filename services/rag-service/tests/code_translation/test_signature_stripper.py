from code_translation.signature_stripper import strip_to_signatures


def test_strip_to_signatures_keeps_only_method_returns():
    code = """
class Foo:
    def a(self):
        x = 1
        return x

    def b(self):
        x = 2


def top_level():
    return 3
"""
    stripped = strip_to_signatures(code)

    assert "def a" in stripped
    assert "return x" in stripped
    assert "def b" in stripped
    assert "..." in stripped
    assert "def top_level" in stripped

