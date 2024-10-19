#!/bin/bash

echo Inside

INPUT_FILE=$1
OUTPUT_DIR=$2

mkdir -p $OUTPUT_DIR

echo Test

python3 /app/convert.py $INPUT_FILE $OUTPUT_DIR