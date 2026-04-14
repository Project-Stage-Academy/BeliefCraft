# pragma: no cover
import argparse
import html
import io
import json
import re
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

import fitz  # type: ignore[import-untyped]
import requests  # type: ignore[import-untyped]
from PIL import Image as PILImage
from pydantic import BaseModel, Field
from reportlab.lib import colors  # type: ignore[import-untyped]
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # type: ignore[import-untyped]
from reportlab.lib.units import inch  # type: ignore[import-untyped]
from reportlab.platypus import (  # type: ignore[import-untyped]
    Flowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)
from tqdm import tqdm  # type: ignore[import-untyped]


class Chunk(BaseModel):
    chunk_id: str
    chunk_type: str
    entity_id: str | None = None
    content: str
    page: int
    part: str | None = None
    part_title: str | None = None
    section_title: str | None = None
    section_number: str | None = None
    subsection_title: str | None = None
    subsection_number: str | None = None
    subsubsection_title: str | None = None
    subsubsection_number: str | None = None
    image_links: list[str] = Field(default_factory=list)
    declarations: list[str] = Field(default_factory=list)
    used_functions: Any = Field(default_factory=list)
    used_structs: Any = Field(default_factory=list)
    referenced_algorithms: list[str] = Field(default_factory=list)
    referenced_figures: list[str] = Field(default_factory=list)
    referenced_formulas: list[str] = Field(default_factory=list)


class PDFRenderer:
    def __init__(
        self,
        output_path: str,
        pdf_with_figures: str = "dm-figures.pdf",
    ) -> None:
        self.output_path = output_path
        self.styles = getSampleStyleSheet()
        self._setup_styles()
        self.pdf_with_figures = pdf_with_figures

    def _setup_styles(self) -> None:
        self.meta_style = ParagraphStyle(
            "Metadata",
            parent=self.styles["Normal"],
            fontSize=7,
            textColor=colors.grey,
            leading=8,
            spaceAfter=2,
        )
        self.content_style = ParagraphStyle(
            "Content",
            parent=self.styles["Normal"],
            fontSize=9,
            leading=11,
            alignment=0,
            spaceBefore=4,
            spaceAfter=4,
        )
        self.header_style = ParagraphStyle(
            "Header",
            parent=self.styles["Heading2"],
            fontSize=11,
            textColor=colors.navy,
            spaceAfter=6,
        )

    def get_placeholder_image(self) -> bytes:
        img = PILImage.new("RGB", (200, 100), color="red")
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format="PNG")
        return img_byte_arr.getvalue()

    def get_image_bytes(self, link: str) -> bytes:
        """Get image bytes from a link.

        If it's an HTTP link, download it. If it's a local reference, try to extract the
        corresponding page from pdf with figures based on the number in the filename.
        If all else fails, return a placeholder image.
        """
        if link.startswith("http"):
            try:
                response = requests.get(link, timeout=10)
                response.raise_for_status()
                return response.content  # type: ignore[no-any-return]
            except Exception as e:
                print(f"Failed to download image from {link}: {e}")
                return self.get_placeholder_image()

        filename = Path(link).name
        page_num_match = re.search(r"(\d+)", filename)
        if page_num_match:
            page_num = int(page_num_match.group(1))
            try:
                with fitz.open(self.pdf_with_figures) as doc:
                    if page_num - 1 < len(doc):
                        page = doc.load_page(page_num - 1)
                        pix = page.get_pixmap()
                        return pix.tobytes()  # type: ignore[no-any-return]
            except Exception as e:
                print(f"Failed to extract image from {self.pdf_with_figures} for {link}: {e}")
        return self.get_placeholder_image()

    def parse_content_to_html(self, content: str) -> str:
        # Sanitize HTML tags but keep formatting
        content = re.sub(r"<(?!/?(b|i|u|br|code)\b)[^>]*>", "", content)

        def replace_latex(match: Any) -> str:
            latex_full = match.group(0)
            unescaped = html.unescape(latex_full)
            return f"<code>{html.escape(unescaped)}</code>"

        return re.sub(r"(\$\$.*?\$\$|\$.*?\$)", replace_latex, content, flags=re.DOTALL)

    def generate_page(self, page_num: int, chunks: list[Chunk], temp_dir: str) -> str:
        temp_file = str(Path(temp_dir) / f"page_{page_num}.pdf")
        doc = SimpleDocTemplate(
            temp_file,
            pagesize=(595, 842),
            leftMargin=30,
            rightMargin=30,
            topMargin=30,
            bottomMargin=30,
        )
        story: list[Flowable] = [Paragraph(f"Page {page_num}", self.header_style)]

        for chunk in chunks:
            raw_hierarchy = [
                chunk.part_title,
                chunk.section_title,
                chunk.subsection_title,
                chunk.subsubsection_title,
            ]
            hierarchy: list[str] = [h for h in raw_hierarchy if h is not None]
            chunk_type = chunk.chunk_type or "unknown"
            if chunk_type != "text":
                chunk_type += f":{chunk.entity_id}"
            meta = f"ID: {chunk.chunk_id} | Type: {chunk_type} | Hierarchy: {' > '.join(hierarchy)}"
            story.append(Paragraph(meta, self.meta_style))

            html_content = self.parse_content_to_html(chunk.content)
            try:
                story.append(Paragraph(html_content, self.content_style))
            except Exception as e:
                print(f"Paragraph error on page {page_num}: {e}")
                story.append(
                    Paragraph(
                        f"<font color='red'>ERROR: {html.escape(str(e))}</font>", self.content_style
                    )
                )
                story.append(Paragraph(html.escape(chunk.content), self.content_style))

            for img_link in chunk.image_links:
                img_data = self.get_image_bytes(img_link)
                story.append(Image(io.BytesIO(img_data), width=1.5 * inch, height=0.75 * inch))
            story.append(Spacer(1, 0.1 * inch))

        doc.build(story)
        return temp_file

    def generate(self, chunks: list[Chunk]) -> None:
        pages_map = defaultdict(list)
        for chunk in chunks:
            pages_map[chunk.page].append(chunk)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_files = []
            for p_num in tqdm(sorted(pages_map.keys())):
                try:
                    temp_files.append(self.generate_page(p_num, pages_map[p_num], temp_dir))
                except Exception as e:
                    print(f"CRITICAL failure on page {p_num}: {e}")

            print(f"\nMerging {len(temp_files)} pages into {self.output_path}...")
            final_doc = fitz.open()
            for f in temp_files:
                try:
                    with fitz.open(f) as p_doc:
                        final_doc.insert_pdf(p_doc)
                except Exception as e:
                    print(f"Failed to merge {f}: {e}")
            final_doc.save(self.output_path)
            final_doc.close()
            print("Done!")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_json", help="Path to the input JSON file containing chunks")
    parser.add_argument(
        "--figures_pdf",
        default="dm-figures.pdf",
        help=(
            "Path to the PDF containing figures from book. "
            "It is needed if the image chunks are not referencing S3"
        ),
    )
    args = parser.parse_args()

    with Path(args.input_json).open() as f:
        data = json.load(f)
    chunks = [Chunk(**c) for c in data]
    renderer = PDFRenderer(
        "ULTIMATE_BOOK_VERIFICATION.pdf",
        pdf_with_figures=args.figures_pdf,
    )
    renderer.generate(chunks)


if __name__ == "__main__":
    main()
