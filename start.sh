#!/bin/bash

# Install Python dependencies
pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install --no-cache-dir -e .[cpu]

# Convert LOG_LEVEL to lowercase for uvicorn
LOG_LEVEL_LOWER=$(echo "${LOG_LEVEL:-info}" | tr '[:upper:]' '[:lower:]')

# Start the application
uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1 --log-level ${LOG_LEVEL_LOWER}
