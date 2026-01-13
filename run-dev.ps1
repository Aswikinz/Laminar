# PowerShell development launcher script
param(
    [string]$InputFile = ".\ProcessFlow.xlsx",
    [string]$OutputDir = ".\output"
)

$ErrorActionPreference = "Stop"

# Create directories
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

# Build the Docker image
Write-Host "Building Docker image..."
docker build -t xls2png-converter .\docker

# Run the CLI with the input file
Write-Host "Processing $InputFile..."
python -m laminar.cli $InputFile -o $OutputDir -v
