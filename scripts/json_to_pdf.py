import os
import io
import json
import re
import html
import argparse
import shutil
import tempfile
from typing import List, Dict, Optional, Any, Tuple

import requests
from pydantic import BaseModel, Field
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Image,
    Table,
    PageBreak,
    Flowable,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from collections import defaultdict
from enum import Enum
from PIL import Image as PILImage
import ziamath as zm
from tqdm import tqdm
import fitz
from svglib.svglib import svg2rlg
from reportlab.graphics import renderPM

class RenderMode(str, Enum):
    RENDERED = "rendered"  # latex as rendered images
    TEXT = "text"  # latex as text

class Chunk(BaseModel):
    chunk_id: str
    chunk_type: str
    entity_id: Optional[str] = None
    content: str
    page: int
    part: Optional[str] = None
    part_title: Optional[str] = None
    section_title: Optional[str] = None
    section_number: Optional[str] = None
    subsection_title: Optional[str] = None
    subsection_number: Optional[str] = None
    subsubsection_title: Optional[str] = None
    subsubsection_number: Optional[str] = None
    image_links: List[str] = Field(default_factory=list)
    declarations: List[str] = Field(default_factory=list)
    used_functions: Any = Field(default_factory=list)
    used_structs: Any = Field(default_factory=list)
    referenced_algorithms: List[str] = Field(default_factory=list)
    referenced_figures: List[str] = Field(default_factory=list)
    referenced_formulas: List[str] = Field(default_factory=list)

class PDFRenderer:
    def __init__(self, output_path: str, mode: RenderMode = RenderMode.RENDERED, pdf_with_figures: str = "dm-figures.pdf"):
        self.output_path = output_path
        self.mode = mode
        self.styles = getSampleStyleSheet()
        self._setup_styles()
        self.pdf_with_figures = pdf_with_figures

    def _setup_styles(self):
        self.meta_style = ParagraphStyle(
            'Metadata', parent=self.styles['Normal'], fontSize=7,
            textColor=colors.grey, leading=8, spaceAfter=2
        )
        self.content_style = ParagraphStyle(
            'Content', parent=self.styles['Normal'], fontSize=9,
            leading=11, alignment=0, spaceBefore=4, spaceAfter=4
        )
        self.header_style = ParagraphStyle(
            'Header', parent=self.styles['Heading2'], fontSize=11,
            textColor=colors.navy, spaceAfter=6
        )

    def get_placeholder_image(self) -> bytes:
        img = PILImage.new('RGB', (200, 100), color='red')
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        return img_byte_arr.getvalue()

    def get_image_bytes(self, link: str) -> bytes:
        """Get image bytes from a link.

        If it's an HTTP link, download it. If it's a local reference, try to extract the corresponding page from
        pdf with figures based on the number in the filename. If all else fails, return a placeholder image.
        """
        if link.startswith("http"):
            try:
                response = requests.get(link)
                response.raise_for_status()
                return response.content
            except Exception as e:
                print(f"Failed to download image from {link}: {e}")
                return self.get_placeholder_image()
        filename = os.path.basename(link)
        page_num_match = re.search(r'(\d+)', filename)
        if page_num_match:
            page_num = int(page_num_match.group(1))
            try:
                with fitz.open(self.pdf_with_figures) as doc:
                    if page_num - 1 < len(doc):
                        page = doc.load_page(page_num - 1)
                        pix = page.get_pixmap()
                        return pix.tobytes()
            except Exception as e:
                print(f"Failed to extract image from {self.pdf_with_figures} for {link}: {e}")
        return self.get_placeholder_image()

    def rasterize_latex(self, latex_str: str, temp_dir: str) -> Tuple[str, float, float]:
        latex_str = html.unescape(latex_str).strip()
        while latex_str.startswith('$'):
            latex_str = latex_str[1:]
        while latex_str.endswith('$'):
            latex_str = latex_str[:-1]

        if not latex_str:
            return "", 0, 0

        try:
            latex_obj = zm.Latex(latex_str, size=14)
            svg_str = latex_obj.svg()
            drawing = svg2rlg(io.StringIO(svg_str))

            img_path = os.path.join(temp_dir, f"formula_{abs(hash(latex_str))}.png")
            renderPM.drawToFile(drawing, img_path, fmt='PNG', dpi=150)

            # Use drawing width/height directly
            return img_path, float(drawing.width), float(drawing.height)
        except Exception as e:
            print(f"Rasterization error for '{latex_str}': {e}")
            return "", 0, 0

    def parse_content_to_html(self, content: str, temp_dir: str) -> str:
        # Sanitize HTML tags but keep formatting
        content = re.sub(r'<(?!/?(b|i|u|br|code)\b)[^>]*>', '', content)

        def replace_latex(match):
            latex_full = match.group(0)
            is_block = latex_full.startswith('$$')
            unescaped = html.unescape(latex_full)

            if self.mode == RenderMode.TEXT:
                return f"<code>{html.escape(unescaped)}</code>"

            latex_inner = unescaped.strip('$')
            img_path, w, h = self.rasterize_latex(latex_inner, temp_dir)
            if not img_path:
                return f"<code>{html.escape(unescaped)}</code>"

            # Robust scaling to prevent 'list index out of range' crashes
            max_w = 480
            if w > max_w:
                scale = max_w / w
                w = max_w
                h *= scale

            img_tag = f'<img src="{img_path}" width="{w}" height="{h}" valign="middle"/>'
            # Avoid nesting <para> tags. Just use <br/> for block separation.
            if is_block:
                return f'<br/>&nbsp;&nbsp;&nbsp;&nbsp;{img_tag}<br/>'
            return img_tag

        return re.sub(r'(\$\$.*?\$\$|\$.*?\$)', replace_latex, content, flags=re.DOTALL)

    def generate_page(self, page_num: int, chunks: List[Chunk], temp_dir: str) -> str:
        temp_file = os.path.join(temp_dir, f"page_{page_num}.pdf")
        doc = SimpleDocTemplate(temp_file, pagesize=(595, 842),
                                leftMargin=30, rightMargin=30, topMargin=30, bottomMargin=30)
        story: list[Flowable] = [Paragraph(f"Page {page_num}", self.header_style)]

        for chunk in chunks:
            hierarchy = [chunk.part_title, chunk.section_title, chunk.subsection_title, chunk.subsubsection_title]
            hierarchy = [h for h in hierarchy if h]
            chunk_type = chunk.chunk_type or "unknown"
            if chunk_type != "text":
                chunk_type += f":{chunk.entity_id}"
            meta = f"ID: {chunk.chunk_id} | Type: {chunk_type} | Hierarchy: {" > ".join(hierarchy)}"
            story.append(Paragraph(meta, self.meta_style))

            html_content = self.parse_content_to_html(chunk.content, temp_dir)
            try:
                story.append(Paragraph(html_content, self.content_style))
            except Exception as e:
                print(f"Paragraph error on page {page_num}: {e}")
                story.append(Paragraph(f"<font color='red'>ERROR: {html.escape(str(e))}</font>", self.content_style))
                story.append(Paragraph(html.escape(chunk.content), self.content_style))

            for img_link in chunk.image_links:
                img_data = self.get_image_bytes(img_link)
                story.append(Image(io.BytesIO(img_data), width=1.5*inch, height=0.75*inch))
            story.append(Spacer(1, 0.1 * inch))

        doc.build(story)
        return temp_file

    def generate(self, chunks: List[Chunk]):
        pages_map = defaultdict(list)
        for chunk in chunks:
            pages_map[chunk.page].append(chunk)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_files = []
            for p_num in tqdm(sorted(pages_map.keys()), desc=f"Mode: {self.mode}"):
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

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_json", help="Path to the input JSON file containing chunks")
    parser.add_argument("--mode", choices=["rendered", "text"], default="text", help="Rendering mode for LaTeX content")
    parser.add_argument("--figures_pdf", default="dm-figures.pdf", help="Path to the PDF containing figures from book. It is needed if the image chunks are not referencing S3")
    args = parser.parse_args()

    with open(args.input_json, 'r') as f:
        data = json.load(f)
    chunks = [Chunk(**c) for c in data]
    renderer = PDFRenderer("ULTIMATE_BOOK_VERIFICATION.pdf", mode=RenderMode(args.mode), pdf_with_figures=args.figures_pdf)
    renderer.generate(chunks)

if __name__ == "__main__":
    main()
