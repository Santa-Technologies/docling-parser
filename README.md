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

### Local Development

1. Build the Docker image:

```bash
docker buildx build --platform linux/amd64 -t eu.gcr.io/wisebid/docling-inference:local -f Dockerfile.cpu .
```

2. Push the image to Google Container Registry:

```bash
docker push eu.gcr.io/wisebid/docling-inference:local
```

3. Deploy to Cloud Run:

```bash
gcloud run deploy docling-inference-dev \
  --image eu.gcr.io/wisebid/docling-inference:local \
  --platform managed \
  --region europe-west3 \
  --allow-unauthenticated \
  --vpc-connector dev-connector \
  --service-account wisebid-auth@wisebid.iam.gserviceaccount.com \
  --set-env-vars "DEV_MODE=1,AUTH_TOKEN=dev-key" \
  --update-labels=env=dev,project=docling-inference \
  --memory 4Gi
```

### Production Deployment

The service is automatically deployed to production using GitHub Actions when changes are pushed to the main branch.

## API Usage

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
