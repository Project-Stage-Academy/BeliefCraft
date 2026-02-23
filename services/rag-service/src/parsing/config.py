import os

# Data Paths
BASE_DATA_DIR = "./data_source"

# Input files
MAIN_PDF = os.path.join(BASE_DATA_DIR, "dm.pdf")
FIGURES_PDF = os.path.join(BASE_DATA_DIR, "dm-figures.pdf")
PADDLE_RESULTS_DIR = os.path.join(BASE_DATA_DIR, "paddle_results")

# Intermediate JSON metadata
OUTPUT_FIGURES_JSON = os.path.join(BASE_DATA_DIR, "figures_metadata.json")
OUTPUT_BLOCKS_JSON = os.path.join(BASE_DATA_DIR, "blocks_metadata.json")
TABLES_JSON = os.path.join(BASE_DATA_DIR, "extracted_tables.json")
FORMULAS_JSON = os.path.join(BASE_DATA_DIR, "formula_mapping.json")

# Final output
FINAL_BOOK_JSON = "ULTIMATE_BOOK_DATA.json"


# PARSING & SEMANTIC SETTINGS
PAGE_OFFSET = 18          # PDF page numbering offset
DPI_RENDER = 200          # Page rendering quality for CV
SCALE_FACTOR = 72 / DPI_RENDER

# Keywords for object detection
CAPTION_KEYWORDS = ["figure", "fig.", "table", "algorithm"]
BLOCK_KEYWORDS = ["example", "exercise"]


#  GEOMETRIC PARAMETERS (Computer Vision & Layout)
# Caption detection
SIMILARITY_THRESHOLD = 0.8        # Threshold for cv2.matchTemplate
CAPTION_OFFSET_X_MINUS = 5
CAPTION_OFFSET_X_PLUS = 100
CAPTION_HEIGHT = 60
SIDE_NOTE_WIDTH = 200

# Page layout analysis
COLUMNS_DIVIDER_X = 300           # Boundary between main text and side notes
SIDE_NOTES_THRESHOLD_X = 600      # Threshold for table captions
DISTANCE_BETWEEN_NOTES = 20       # Max distance between caption lines
DISTANCE_OFFSET_X = 100           # Offset for gray block verification
GRAY_FILL_THRESHOLD = 0.9         # Gray background intensity (0.0–1.0)
BBOX_PADDING = 35                 # Padding for nested block detection


# MATH ENGINE SETTINGS
MAX_FORMULA_DISTANCE = 600        # Max distance from number to formula
FORMULA_Y_OFFSET_BUFFER = 20      # Vertical tolerance for formulas
BLOCK_CONTENT_PADDING = 20        # Extra space to capture block content


# METADATA SETTINGS
ID_PREFIX_LIMIT = 100             # Character limit for ID detection in text
DEFAULT_PART = "I"
DEFAULT_PART_TITLE = "Part I — Probabilistic Reasoning"