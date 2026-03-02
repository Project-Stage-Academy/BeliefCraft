from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


_ENV = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(enabled_extensions=("html", "xml")),
    variable_start_string="<<",
    variable_end_string=">>",
)


def _render_template(template_name: str, **context: str) -> str:
    return _ENV.get_template(template_name).render(**context)


class PromptTemplates:
    @staticmethod
    def update_descriptions_prompt(julia_fragments: str, available_python_code: str) -> str:
        return _render_template(
            "update_descriptions_prompt.j2",
            julia_fragments=julia_fragments,
            available_python_code=available_python_code,
        )

    @staticmethod
    def translate_julia_code_prompt(julia_fragments: str, available_python_code: str) -> str:
        return _render_template(
            "translate_julia_code_prompt.j2",
            julia_fragments=julia_fragments,
            available_python_code=available_python_code,
        )

    @staticmethod
    def translate_example_prompt(example_text: str, available_python_code: str) -> str:
        return _render_template(
            "translate_example_prompt.j2",
            example_text=example_text,
            available_python_code=available_python_code,
        )
