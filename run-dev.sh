#!/bin/bash
set -e

INPUT_FILE="${1:-./ProcessFlow.xlsx}"
OUTPUT_DIR="./output"

# Create directories
mkdir -p "$OUTPUT_DIR"

# Build the Docker image
echo "Building Docker image..."
docker build -t xls2png-converter ./docker

# Run the CLI with the input file
echo "Processing $INPUT_FILE..."
python -m laminar.cli "$INPUT_FILE" -o "$OUTPUT_DIR" -v
