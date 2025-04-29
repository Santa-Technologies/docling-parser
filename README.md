# Docling Parser

A document parsing service that extracts text, tables, and other elements from various document formats.

## Features

- Supports multiple input formats (PDF, DOCX, etc.)
- OCR capabilities with multi-language support
- Table extraction and recognition
- Layout analysis
- Optional enrichment features (code, formulas, picture classification/description)

## Model Management

The service uses a sophisticated model management system that:

1. Automatically downloads models on first use
2. Caches models in Google Cloud Storage for faster subsequent loads
3. Only loads models that are needed for the current request
4. Automatically uploads used models to the cache after processing

### Model Caching Behavior

- Models are downloaded from their original sources on first use
- After successful processing, used models are automatically uploaded to the configured GCP bucket
- Subsequent requests will use the cached models from the bucket
- The system maintains the exact directory structure required by each model library

### Environment Variables

Configure model caching and language support:

```bash
# GCP bucket for model caching
CACHE_BUCKET=docling-models

# Prioritize specific languages for OCR (comma-separated)
OCR_LANGUAGES=de,en
```

## Building and Deployment

### Production Deployment

The service is automatically deployed to production using GitHub Actions when changes are pushed to the main branch.

## API Usage

### Load and Chunk Document

This endpoint implements the DoclingLoader functionality, allowing you to load and chunk documents from either a local file path or a URL:

```bash
# Using a URL
curl -X POST "https://your-service-url/load-document" \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "https://example.com/document.pdf",
    "export_type": "DOC_CHUNKS",
    "chunker_kwargs": {
      "chunk_size": 1000,
      "chunk_overlap": 200
    },
    "pipeline_options": {
      "extract_text": true,
      "extract_images": true,
      "extract_tables": true,
      "ocr_options": {
        "lang": ["de", "en"]
      }
    }
  }'

# Using a local file path
curl -X POST "https://your-service-url/load-document" \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "/path/to/document.pdf",
    "export_type": "DOC_CHUNKS",
    "chunker_kwargs": {
      "chunk_size": 1000,
      "chunk_overlap": 200
    },
    "pipeline_options": {
      "extract_text": true,
      "extract_images": true,
      "extract_tables": true
    }
  }'
```

Response format:

```json
{
  "chunks": [
    {
      "page_content": "Chunk content...",
      "metadata": {
        "headings": [...],
        "captions": [...],
        "origin": "..."
      }
    }
  ],
  "status": "success",
  "message": "Document loaded successfully"
}
```

### Parse Document from URL

```bash
curl -X POST "https://your-service-url/parse-url" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/document.pdf",
    "options": {
      "ocr_languages": ["de", "en"],
      "do_code_enrichment": true,
      "do_formula_enrichment": true
    }
  }'
```

### Parse Document from Stream

```bash
curl -X POST "https://your-service-url/parse-stream" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@document.pdf" \
  -F 'options={"ocr_languages": ["de", "en"], "do_code_enrichment": true}'
```

## Response Format

The API returns a JSON response with the following structure:

```json
{
  "success": true,
  "result": {
    "text": "Extracted text content",
    "tables": [...],
    "layout": [...],
    "code_blocks": [...],
    "formulas": [...],
    "pictures": [...]
  }
}
```

## Error Handling

The API returns appropriate HTTP status codes and error messages:

- 400: Invalid input or options
- 500: Internal server error
- 503: Service unavailable (e.g., during model loading)

## Development

### Prerequisites

- Python 3.8+
- Docker
- Google Cloud SDK
- Access to Google Cloud Storage bucket for model caching

### Local Setup

1. Clone the repository
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Set up environment variables:

```bash
export CACHE_BUCKET=docling-models
export OCR_LANGUAGES=de,en
```

4. Run the service locally:

```bash
python src/main.py
```

## License
