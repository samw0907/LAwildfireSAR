# scripts/run_processing.py
from src.utils.config import load_config
from src.pipeline.download import run_download
from src.pipeline.process import run_processing

config = load_config()
inventory = run_download(config)
run_processing(inventory, config)