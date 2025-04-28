import os
import shutil
from pathlib import Path
import logging
from typing import Dict, List, Optional
from docling.datamodel.pipeline_options import EasyOcrOptions, PdfPipelineOptions
from docling.document_converter import DocumentConverter
from docling.datamodel.base_models import InputFormat
from google.cloud import storage
from google.cloud.exceptions import GoogleCloudError
import threading

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
        self.used_models: Dict[str, bool] = {
            "layout": False,
            "table": False,
            "ocr": False,
            "code": False,
            "formula": False,
            "picture_classification": False,
            "picture_description": False
        }
        self.used_languages: List[str] = []

        # Set up cache directories
        self.hf_cache = Path(os.getenv("TRANSFORMERS_CACHE", "/root/.cache/huggingface"))
        self.ocr_cache = Path(os.getenv("EASYOCR_CACHE", "/root/.EasyOCR"))

        # Create cache directories if they don't exist
        self.hf_cache.mkdir(parents=True, exist_ok=True)
        self.ocr_cache.mkdir(parents=True, exist_ok=True)

        # Initialize storage client if bucket is configured
        self.storage_client = storage.Client() if cache_bucket else None
        self.bucket = self.storage_client.bucket(cache_bucket) if self.storage_client and cache_bucket else None

        # Initialize with core models
        self._initialize_core_models()

        # Initialize a lock for thread safety
        self.lock = threading.Lock()

    def _sync_directory(self, source_prefix: str, destination: Path, download: bool = True):
        """Sync a directory between GCS bucket and local filesystem"""
        if not self.bucket:
            return

        try:
            if download:
                # Download from bucket to local
                blobs = self.bucket.list_blobs(prefix=source_prefix)
                for blob in blobs:
                    # Create local path
                    local_path = destination / blob.name[len(source_prefix):]
                    local_path.parent.mkdir(parents=True, exist_ok=True)

                    # Download file
                    blob.download_to_filename(str(local_path))
            else:
                # Upload from local to bucket
                for local_file in destination.rglob("*"):
                    if local_file.is_file():
                        blob_name = f"{source_prefix}{local_file.relative_to(destination)}"
                        blob = self.bucket.blob(blob_name)
                        blob.upload_from_filename(str(local_file))
        except GoogleCloudError as e:
            logger.error(f"Failed to sync directory: {e}")

    def _copy_matching_files(self, source_prefix: str, destination: Path, pattern: str):
        """Copy files matching a pattern from GCS bucket to local filesystem"""
        if not self.bucket:
            return

        try:
            blobs = self.bucket.list_blobs(prefix=source_prefix)
            for blob in blobs:
                if pattern in blob.name:
                    local_path = destination / blob.name[len(source_prefix):]
                    local_path.parent.mkdir(parents=True, exist_ok=True)
                    blob.download_to_filename(str(local_path))
        except GoogleCloudError as e:
            logger.error(f"Failed to copy matching files: {e}")

    def _initialize_core_models(self):
        """Initialize core models (layout analysis and table recognition)"""
        logger.info("Initializing core models")

        # Use lock to ensure thread safety during initialization
        with self.lock:
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

        # Use lock to ensure thread safety during model loading
        with self.lock:
            # First try to load from bucket cache
            found_in_cache = False
            if self.bucket:
                for lang in languages:
                    self._copy_matching_files("easyocr/", self.ocr_cache, lang)
                    # Check if we found the model in cache
                    if any(self.ocr_cache.glob(f"*{lang}*")):
                        found_in_cache = True
                        logger.info(f"Found OCR model for {lang} in cache")

            # If not found in cache, let the converter download from original source
            if not found_in_cache:
                logger.info("Models not found in cache, downloading from original source")

            self.converter.format_options.ocr_options = EasyOcrOptions(lang=languages)
            self.loaded_models["ocr"] = True
            self.used_models["ocr"] = True
            self.used_languages.extend(languages)
            logger.info("OCR models loaded")

    def load_enrichment_models(self, model_type: str):
        """Load specific enrichment models on demand"""
        if self.loaded_models[model_type]:
            return

        logger.info(f"Loading {model_type} model")

        # Use lock to ensure thread safety during model loading
        with self.lock:
            # First try to load from bucket cache
            found_in_cache = False
            if self.bucket:
                model_prefix = f"{model_type}-model"
                self._copy_matching_files("huggingface/", self.hf_cache, model_prefix)
                # Check if we found the model in cache
                if any(self.hf_cache.glob(f"{model_prefix}*")):
                    found_in_cache = True
                    logger.info(f"Found {model_type} model in cache")

            # If not found in cache, let the converter download from original source
            if not found_in_cache:
                logger.info(f"{model_type} model not found in cache, downloading from original source")

            if model_type == "code":
                self.converter.format_options.do_code_enrichment = True
            elif model_type == "formula":
                self.converter.format_options.do_formula_enrichment = True
            elif model_type == "picture_classification":
                self.converter.format_options.do_picture_classification = True
            elif model_type == "picture_description":
                self.converter.format_options.do_picture_description = True

            self.loaded_models[model_type] = True
            self.used_models[model_type] = True
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

    def upload_used_models(self):
        """Upload models that were used during processing"""
        if not self.bucket:
            return

        logger.info("Uploading used models to GCP bucket")
        try:
            # Upload core models if used
            if self.used_models["layout"] or self.used_models["table"]:
                for model_dir in self.hf_cache.glob("layout-model*"):
                    # Upload the entire directory structure
                    for root, _, files in os.walk(model_dir):
                        for file in files:
                            local_path = Path(root) / file
                            blob_path = f"huggingface/{model_dir.name}/{local_path.relative_to(model_dir)}"
                            blob = self.bucket.blob(blob_path)
                            blob.upload_from_filename(str(local_path))
                for model_dir in self.hf_cache.glob("table-model*"):
                    # Upload the entire directory structure
                    for root, _, files in os.walk(model_dir):
                        for file in files:
                            local_path = Path(root) / file
                            blob_path = f"huggingface/{model_dir.name}/{local_path.relative_to(model_dir)}"
                            blob = self.bucket.blob(blob_path)
                            blob.upload_from_filename(str(local_path))

            # Upload OCR models for used languages
            if self.used_models["ocr"] and self.used_languages:
                model_dir = self.ocr_cache / "model"
                if model_dir.exists():
                    # Upload the entire model directory structure
                    for root, _, files in os.walk(model_dir):
                        for file in files:
                            local_path = Path(root) / file
                            blob_path = f"easyocr/model/{local_path.relative_to(model_dir)}"
                            blob = self.bucket.blob(blob_path)
                            blob.upload_from_filename(str(local_path))

            # Upload enrichment models if used
            model_types = [
                ("code", "code-model"),
                ("formula", "formula-model"),
                ("picture_classification", "picture-classification-model"),
                ("picture_description", "picture-description-model")
            ]

            for model_type, model_prefix in model_types:
                if self.used_models[model_type]:
                    for model_dir in self.hf_cache.glob(f"{model_prefix}*"):
                        # Upload the entire directory structure
                        for root, _, files in os.walk(model_dir):
                            for file in files:
                                local_path = Path(root) / file
                                blob_path = f"huggingface/{model_dir.name}/{local_path.relative_to(model_dir)}"
                                blob = self.bucket.blob(blob_path)
                                blob.upload_from_filename(str(local_path))

            logger.info("Used models uploaded successfully")
        except Exception as e:
            logger.error(f"Failed to upload used models: {e}")

    def reset_usage_tracking(self):
        """Reset the tracking of which models were used"""
        self.used_models = {k: False for k in self.used_models}
        self.used_languages = []
