#!/usr/bin/env bash

set -e

if [ -z "$1" ]; then
    echo "Error: specify path to PNG file."
    echo "Usage: $0 <file.png>"
    exit 1
fi

INPUT_FILE="$1"

if [ ! -f "$INPUT_FILE" ]; then
    echo "Error: file '$INPUT_FILE' not found."
    exit 1
fi

OUTPUT_FILE="${INPUT_FILE%.*}.webp"
echo "Convert: $INPUT_FILE -> $OUTPUT_FILE"

cwebp -near_lossless 80 -m 6 "$INPUT_FILE" -o "$OUTPUT_FILE"

if [ $? -eq 0 ] && [ -f "$OUTPUT_FILE" ]; then
    rm "$INPUT_FILE"
    echo "Success: created $OUTPUT_FILE, original PNG deleted."
else
    echo "Error: failed to convert file."
    exit 1
fi
