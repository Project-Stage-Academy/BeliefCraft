from pipeline.julia_code_translation.signature_stripper import strip_to_signatures


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

    expected = """
class Foo:

    def a(self):
        return x

    def b(self):
        ...

def top_level():
    return 3
""".strip()

    assert stripped == expected
