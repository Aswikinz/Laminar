import sys
import os
import subprocess

def convert_xlsx_to_pdf(xlsx_file, output_dir):
    # Convert XLSX to PDF using LibreOffice with each worksheet on a single page
    subprocess.run([
        'libreoffice', '--headless', '--convert-to', 'pdf:calc_pdf_Export:{"SinglePageSheets":{"type":"boolean","value":"true"}}', '--outdir', output_dir,
        xlsx_file
    ], check=True)

def convert_pdf_to_png(pdf_file, output_dir):
    # Convert PDF to PNG using ImageMagick
    if not os.path.exists(pdf_file):
        raise FileNotFoundError(f"PDF file {pdf_file} not found.")
    subprocess.run([
        'convert', '-density', '300', pdf_file, '-quality', '100', os.path.join(output_dir, '%d.png')
    ], check=True)

def main():
    if len(sys.argv) != 3:
        print("Usage: python convert.py <input_xlsx_file> <output_directory>")
        sys.exit(1)

    xlsx_file = sys.argv[1]
    output_dir = sys.argv[2]

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Convert XLSX to PDF
    convert_xlsx_to_pdf(xlsx_file, output_dir)

    # Get the PDF file name
    pdf_file = os.path.join(output_dir, os.path.splitext(os.path.basename(xlsx_file))[0] + '.pdf')

    # Check if PDF was created successfully
    if not os.path.exists(pdf_file):
        print(f"Error: PDF file {pdf_file} was not created.")
        sys.exit(1)

    # Convert PDF to PNG
    convert_pdf_to_png(pdf_file, output_dir)

if __name__ == "__main__":
    main()