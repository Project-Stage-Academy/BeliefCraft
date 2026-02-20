import os

MAIN_PDF = "./data_source/dm.pdf"
FIGURES_PDF = "./data_source/dm-figures.pdf"
PADDLE_JSON_DIR = "./data_source/paddle_results"

SIDE_NOTES_THRESHOLD = 600  
GRAY_FILL_THRESHOLD = 0.9   
IMAGE_MATCH_THRESHOLD = 0.85 

MAX_TEXT_BLOCK_DISTANCE = 50 # Max distance in pixels to consider a text block part of a formula/table/figure caption

JSON_FILES = [
    "1-100.json", "101-200.json", "201-300.json", 
    "301-400.json", "401-500.json", "501-600.json", "601-700.json"
]