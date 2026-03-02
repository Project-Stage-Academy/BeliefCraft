import pytest
import numpy as np
from unittest.mock import MagicMock, patch
from pipeline.parsing import image_processor as ip

def test_get_scale_factor():
    assert ip.get_scale_factor(72) == 1.0
    assert ip.get_scale_factor(144) == 0.5

def test_create_entry_logic():
    description = "[BLOCK EXAMPLE CONTENT]:\nExample 1.2 Analysis"
    max_loc = (10, 20)
    t_w, t_h = 100, 50
    
    entry = ip._create_entry(description, page_num=0, idx=0, max_val=0.95, 
                             max_loc=max_loc, t_w=t_w, t_h=t_h)
    
    assert entry["chunk_type"] == "example"
    assert entry["entity_id"] == "1.2"
    assert entry["page"] == 1
    assert entry["bbox"] == [10.0, 20.0, 110.0, 70.0]

def test_create_entry_captioned_image():
    description = "Figure 4.5. Architecture diagram"
    entry = ip._create_entry(description, page_num=5, idx=2, max_val=0.88, 
                             max_loc=(0, 0), t_w=10, t_h=10)
    
    assert entry["chunk_type"] == "captioned_image"
    assert entry["entity_id"] == "4.5"

@patch("cv2.matchTemplate")
@patch("cv2.minMaxLoc")
def test_match_template_on_page_success(mock_min_max, mock_match):
    page_gray = np.zeros((500, 500), dtype=np.uint8)
    template_gray = np.zeros((50, 50), dtype=np.uint8)
    
    mock_min_max.return_value = (0.1, 0.9, (10, 10), (100, 150))
    mock_match.return_value = np.zeros((451, 451), dtype=np.float32)

    result = ip._match_template_on_page(page_gray, template_gray)
    
    assert result is not None
    similarity, location = result
    assert similarity == 0.9
    assert location == (100, 150)

def test_get_advanced_caption_no_blocks():
    mock_page = MagicMock()
    mock_page.get_text.return_value = [] 
    
    rect = (0, 0, 100, 100)
    result = ip.get_advanced_caption(mock_page, rect)
    
    assert result == "Image without specific caption or block header"

@patch("fitz.open")
@patch("pipeline.parsing.image_processor._save_to_json")
def test_process_pdf_orchestration(mock_save, mock_open):
    mock_doc = MagicMock()
    mock_doc.__len__.return_value = 1
    mock_open.return_value.__enter__.return_value = mock_doc

    ip.process_pdf("main.pdf", "figs.pdf", "out.json")
    
    mock_save.assert_called_once()