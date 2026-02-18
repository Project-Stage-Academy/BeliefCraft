import fitz
import cv2
import numpy as np
import os
import json
import re
from tqdm import tqdm

def pdf_page_to_img(doc, page_number, dpi=200):
    """Renders a PDF page to an image array."""
    page = doc.load_page(page_number)
    pix = page.get_pixmap(dpi=dpi)
    img = np.frombuffer(pix.samples, dtype=np.uint8)
    img = img.reshape(pix.height, pix.width, pix.n)
    img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR if pix.n == 4 else cv2.COLOR_RGB2BGR)
    return img

def get_advanced_caption(page, rect_coords, dpi=200):
    """Logic text analysis around image coordinates."""
    x, y, w, h = rect_coords
    scale = 72 / dpi
    img_rect = fitz.Rect(x * scale, y * scale, (x + w) * scale, (y + h) * scale)
    blocks = page.get_text("blocks")
    
    caption_area = fitz.Rect(img_rect.x0 - 5, img_rect.y1, img_rect.x1 + 100, img_rect.y1 + 60)
    side_area = fitz.Rect(img_rect.x1, img_rect.y0, img_rect.x1 + 200, img_rect.y1)

    for b in blocks:
        block_rect = fitz.Rect(b[:4])
        text = b[4].strip()
        if any(word in text.lower() for word in ["figure", "fig."]):
            if block_rect.intersects(caption_area) or block_rect.intersects(side_area):
                return f"FOUND CAPTION: {text.replace('\n', ' ')}"

    candidate_header = None
    header_type = ""
    for b in blocks:
        block_rect = fitz.Rect(b[:4])
        text = b[4].strip().lower()
        if "example" in text or "exercise" in text:
            if block_rect.y0 < img_rect.y1: 
                candidate_header = block_rect
                header_type = "EXAMPLE" if "example" in text else "EXERCISE"

    if candidate_header:
        content_rect = fitz.Rect(candidate_header.x0, candidate_header.y0, page.rect.width, img_rect.y1 + 20)
        full_content = page.get_text("text", clip=content_rect).strip()
        return f"[BLOCK {header_type} CONTENT]:\n{full_content}"

    return "Image without specific caption or block header"

def append_to_json(file_path, data):
    """Add one entry to a JSON file."""
    if not os.path.exists(file_path):
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump([data], f, indent=2, ensure_ascii=False)
    else:
        with open(file_path, 'r+', encoding='utf-8') as f:
            f.seek(0, os.SEEK_END)
            pos = f.tell() - 1
            while pos > 0:
                f.seek(pos)
                if f.read(1) == ']':
                    f.seek(pos)
                    f.write(f', {json.dumps(data, indent=2, ensure_ascii=False)}]')
                    break
                pos -= 1

def process_pdf(dm_pdf_path, figures_pdf_path, output_json="figures_metadata.json"):
    dm_doc = fitz.open(dm_pdf_path)
    figs_doc = fitz.open(figures_pdf_path)
    
    if os.path.exists(output_json):
        os.remove(output_json)

    already_found = set()
    total_figs = len(figs_doc)

    print(f"[*] Processing {len(dm_doc)} pages against {total_figs} templates...")

    for page_num in tqdm(range(len(dm_doc)), desc="Pages"):
        page_img = pdf_page_to_img(dm_doc, page_num)
        page_obj = dm_doc.load_page(page_num)

        for idx in range(total_figs):
            if idx in already_found:
                continue

            template = pdf_page_to_img(figs_doc, idx)
            
            t_h, t_w = template.shape[:2]
            p_h, p_w = page_img.shape[:2]
            
            if t_h <= p_h and t_w <= p_w:
                res = cv2.matchTemplate(cv2.cvtColor(page_img, cv2.COLOR_BGR2GRAY), 
                                        cv2.cvtColor(template, cv2.COLOR_BGR2GRAY), 
                                        cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(res)

                if max_val >= 0.8:
                    description = get_advanced_caption(page_obj, (max_loc[0], max_loc[1], t_w, t_h))
                    
                    img_type = "captioned_image"
                    if "[BLOCK EXAMPLE" in description: img_type = "example"
                    elif "[BLOCK EXERCISE" in description: img_type = "exercise"
                    
                    entry = {
                        "chunk_type": img_type,
                        "entity_id": (re.search(r"(\d+\.\d+)", description) or re.search(r"(\d+)", description) or [None, None])[0],
                        "page": page_num + 1,
                        "image_index": idx + 1,
                        "content": description,
                        "similarity": round(float(max_val), 4),
                        "bbox": [max_loc[0], max_loc[1], max_loc[0]+t_w, max_loc[1]+t_h]
                    }
                    
                    append_to_json(output_json, entry)
                    already_found.add(idx)
            
            del template

        del page_img

    dm_doc.close()
    figs_doc.close()
    print(f"\n[DONE] Results saved to {output_json}")

if __name__ == "__main__":
    process_pdf("dm.pdf", "dm-figures.pdf")