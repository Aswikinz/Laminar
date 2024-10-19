#!/bin/bash

INPUT_FILE="./ProcessFlow.xlsx"
OUTPUT_DIR="./output"

# Create a temporary input directory
TEMP_INPUT_DIR="./input"
mkdir -p $TEMP_INPUT_DIR

# Copy the input file to the temporary input directory
cp $INPUT_FILE $TEMP_INPUT_DIR/

# Remove and recreate the output directory
if [ -d "$OUTPUT_DIR" ]; then
    rm -rf "$OUTPUT_DIR"
fi
mkdir -p "$OUTPUT_DIR"

# Build the Docker image
docker build -t xls2png-converter ./docker

# Run main.py with the input file as parameter
python3 main.py $INPUT_FILE