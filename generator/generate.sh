#!/bin/bash
# Interactive CV generation wrapper

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "==================================="
echo "      CV Generator Menu"
echo "==================================="
echo ""
echo "1) Generate French CV"
echo "2) Generate French CV (anonymized)"
echo "3) Generate French CV with PDF"
echo "4) Generate French CV (anonymized) with PDF"
echo "5) Generate English CV (requires GEMINI_API_KEY)"
echo "6) Generate English CV (anonymized)"
echo "7) Generate English CV with PDF"
echo "8) Generate English CV (anonymized) with PDF"
echo "9) Generate all versions (HTML only)"
echo "10) Generate all versions (HTML + PDF)"
echo "0) Exit"
echo ""
read -p "Select option [0-10]: " option

case $option in
  1)
    echo "Generating French CV..."
    python3 generate.py resume.json
    ;;
  2)
    echo "Generating anonymized French CV..."
    python3 generate.py resume.json --anonymize
    ;;
  3)
    echo "Generating French CV with PDF..."
    python3 generate.py resume.json --pdf
    ;;
  4)
    echo "Generating anonymized French CV with PDF..."
    python3 generate.py resume.json --anonymize --pdf
    ;;
  5)
    if [ -z "$GEMINI_API_KEY" ] && [ -z "$GOOGLE_API_KEY" ]; then
      echo "Error: GEMINI_API_KEY environment variable not set"
      echo "Usage: export GEMINI_API_KEY='your-key-here'"
      exit 1
    fi
    echo "Generating English CV (translating)..."
    python3 generate.py resume.json --translate
    ;;
  6)
    if [ -z "$GEMINI_API_KEY" ] && [ -z "$GOOGLE_API_KEY" ]; then
      echo "Error: GEMINI_API_KEY environment variable not set"
      echo "Usage: export GEMINI_API_KEY='your-key-here'"
      exit 1
    fi
    echo "Generating anonymized English CV (translating)..."
    python3 generate.py resume.json --translate --anonymize
    ;;
  7)
    if [ -z "$GEMINI_API_KEY" ] && [ -z "$GOOGLE_API_KEY" ]; then
      echo "Error: GEMINI_API_KEY environment variable not set"
      echo "Usage: export GEMINI_API_KEY='your-key-here'"
      exit 1
    fi
    echo "Generating English CV with PDF (translating)..."
    python3 generate.py resume.json --translate --pdf
    ;;
  8)
    if [ -z "$GEMINI_API_KEY" ] && [ -z "$GOOGLE_API_KEY" ]; then
      echo "Error: GEMINI_API_KEY environment variable not set"
      echo "Usage: export GEMINI_API_KEY='your-key-here'"
      exit 1
    fi
    echo "Generating anonymized English CV with PDF (translating)..."
    python3 generate.py resume.json --translate --anonymize --pdf
    ;;
  9)
    if [ -z "$GEMINI_API_KEY" ] && [ -z "$GOOGLE_API_KEY" ]; then
      echo "Warning: GEMINI_API_KEY not set. Skipping English versions."
      echo ""
      echo "Generating French versions..."
      python3 generate.py resume.json
      python3 generate.py resume.json --anonymize
    else
      echo "Generating all versions (HTML)..."
      echo ""
      echo "1/4: French CV..."
      python3 generate.py resume.json
      echo ""
      echo "2/4: French CV (anonymized)..."
      python3 generate.py resume.json --anonymize
      echo ""
      echo "3/4: English CV..."
      python3 generate.py resume.json --translate
      echo ""
      echo "4/4: English CV (anonymized)..."
      python3 generate.py resume.json --translate --anonymize
    fi
    echo ""
    echo "✓ All versions generated!"
    ;;
  10)
    if [ -z "$GEMINI_API_KEY" ] && [ -z "$GOOGLE_API_KEY" ]; then
      echo "Warning: GEMINI_API_KEY not set. Skipping English versions."
      echo ""
      echo "Generating French versions with PDF..."
      python3 generate.py resume.json --pdf
      python3 generate.py resume.json --anonymize --pdf
    else
      echo "Generating all versions (HTML + PDF)..."
      echo ""
      echo "1/4: French CV..."
      python3 generate.py resume.json --pdf
      echo ""
      echo "2/4: French CV (anonymized)..."
      python3 generate.py resume.json --anonymize --pdf
      echo ""
      echo "3/4: English CV..."
      python3 generate.py resume.json --translate --pdf
      echo ""
      echo "4/4: English CV (anonymized)..."
      python3 generate.py resume.json --translate --anonymize --pdf
    fi
    echo ""
    echo "✓ All versions generated!"
    ;;
  0)
    echo "Exiting..."
    exit 0
    ;;
  *)
    echo "Invalid option"
    exit 1
    ;;
esac

echo ""
echo "✓ Done! Output files are in: output_local/"
ls -lh output_local/
