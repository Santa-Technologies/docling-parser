import os
import shutil
from pathlib import Path
import logging
from typing import Dict, Optional
from docling.datamodel.pipeline_options import EasyOcrOptions, PdfPipelineOptions
from docling.document_converter import DocumentConverter
from docling.datamodel.base_models import InputFormat

logger = logging.getLogger(__name__)

class ModelManager:
    def __init__(self, cache_bucket: Optional[str] = None):
        self.cache_bucket = cache_bucket
        self.converter = None
        self.loaded_models: Dict[str, bool] = {
            "layout": False,
            "table": False,
            "ocr": False,
            "code": False,
            "formula": False,
            "picture_classification": False,
            "picture_description": False
        }

        # Set up cache directories
        self.hf_cache = Path(os.getenv("TRANSFORMERS_CACHE", "/root/.cache/huggingface"))
        self.ocr_cache = Path(os.getenv("EASYOCR_CACHE", "/root/.EasyOCR"))

        # Create cache directories if they don't exist
        self.hf_cache.mkdir(parents=True, exist_ok=True)
        self.ocr_cache.mkdir(parents=True, exist_ok=True)

        # Initialize with core models
        self._initialize_core_models()

    def _initialize_core_models(self):
        """Initialize core models (layout analysis and table recognition)"""
        logger.info("Initializing core models")

        # Initialize converter first
        self.converter = DocumentConverter()

        # Set default pipeline options
        format_options = PdfPipelineOptions(
            ocr_options=EasyOcrOptions(lang=["en"]),  # Minimal OCR setup
            do_code_enrichment=False,
            do_formula_enrichment=False,
            do_picture_classification=False,
            do_picture_description=False,
        )

        # Set options after initialization
        self.converter.format_options = format_options
        self.loaded_models["layout"] = True
        self.loaded_models["table"] = True
        logger.info("Core models initialized")

    def load_ocr_models(self, languages: list[str]):
        """Load OCR models for specified languages"""
        if self.loaded_models["ocr"]:
            return

        logger.info(f"Loading OCR models for languages: {languages}")
        self.converter.format_options.ocr_options = EasyOcrOptions(lang=languages)
        self.loaded_models["ocr"] = True
        logger.info("OCR models loaded")

    def load_enrichment_models(self, model_type: str):
        """Load specific enrichment models on demand"""
        if self.loaded_models[model_type]:
            return

        logger.info(f"Loading {model_type} model")

        if model_type == "code":
            self.converter.format_options.do_code_enrichment = True
        elif model_type == "formula":
            self.converter.format_options.do_formula_enrichment = True
        elif model_type == "picture_classification":
            self.converter.format_options.do_picture_classification = True
        elif model_type == "picture_description":
            self.converter.format_options.do_picture_description = True

        self.loaded_models[model_type] = True
        logger.info(f"{model_type} model loaded")

    def unload_model(self, model_type: str):
        """Unload a specific model to free up memory"""
        if not self.loaded_models[model_type]:
            return

        logger.info(f"Unloading {model_type} model")

        if model_type == "ocr":
            self.converter.format_options.ocr_options = None
        elif model_type == "code":
            self.converter.format_options.do_code_enrichment = False
        elif model_type == "formula":
            self.converter.format_options.do_formula_enrichment = False
        elif model_type == "picture_classification":
            self.converter.format_options.do_picture_classification = False
        elif model_type == "picture_description":
            self.converter.format_options.do_picture_description = False

        self.loaded_models[model_type] = False
        logger.info(f"{model_type} model unloaded")

    def sync_with_bucket(self):
        """Sync model cache with GCP bucket if configured"""
        if not self.cache_bucket:
            return

        logger.info("Syncing model cache with GCP bucket")
        try:
            # Sync Hugging Face cache
            os.system(f"gsutil -m rsync -r gs://{self.cache_bucket}/huggingface {self.hf_cache}")
            # Sync EasyOCR cache
            os.system(f"gsutil -m rsync -r gs://{self.cache_bucket}/easyocr {self.ocr_cache}")
            logger.info("Model cache synced successfully")
        except Exception as e:
            logger.error(f"Failed to sync model cache: {e}")

    def upload_to_bucket(self):
        """Upload model cache to GCP bucket if configured"""
        if not self.cache_bucket:
            return

        logger.info("Uploading model cache to GCP bucket")
        try:
            # Upload Hugging Face cache
            os.system(f"gsutil -m rsync -r {self.hf_cache} gs://{self.cache_bucket}/huggingface")
            # Upload EasyOCR cache
            os.system(f"gsutil -m rsync -r {self.ocr_cache} gs://{self.cache_bucket}/easyocr")
            logger.info("Model cache uploaded successfully")
        except Exception as e:
            logger.error(f"Failed to upload model cache: {e}")
