$inputFile = "./MultiFlow.xlsm"
$outputDir = "./output"

# Create a temporary input directory
$tempInputDir = "./input"
if (-Not (Test-Path -Path $tempInputDir)) {
    New-Item -ItemType Directory -Path $tempInputDir | Out-Null
}

# Copy the input file to the temporary input directory
Copy-Item -Path $inputFile -Destination $tempInputDir

# Remove and recreate the output directory
if (Test-Path -Path $outputDir) {
    Remove-Item -Recurse -Force -Path $outputDir
}
New-Item -ItemType Directory -Path $outputDir | Out-Null

# Build the Docker image
docker build -t xls2png-converter ./docker

# Run main.py with the input file as parameter
python main.py $inputFile