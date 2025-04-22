#!/bin/bash

echo "Starting application..."
echo "Current directory: $(pwd)"
echo "Environment variables:"
env | grep -E "PORT|CACHE|TRANSFORMERS|EASYOCR|PYTHON"

echo "Starting uvicorn..."
exec uvicorn src.main:app --host 0.0.0.0 --port 8080 --workers 1 --timeout-keep-alive 300 --log-level debug
