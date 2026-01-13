# Laminar

**Business Process Analysis and Visualization Tool**

Laminar converts Excel spreadsheets containing business process descriptions into interactive Mermaid flowchart diagrams using Claude AI.

![Sample Output](sample.png)

## Features

- **AI-Powered Analysis**: Uses Claude (Anthropic) to intelligently parse business process data
- **Visual + Data Processing**: Analyzes both spreadsheet images and CSV data for comprehensive understanding
- **Professional Diagrams**: Generates Mermaid flowcharts with:
  - Role-based swimlanes
  - Color-coded decision paths (green/red for Yes/No)
  - Stadium-shaped Start/End nodes
  - Diamond-shaped decision points
  - Proper styling matching business standards
- **Batch Processing**: Process multiple Excel files or entire directories
- **GUI & CLI**: Desktop application and command-line interface

## Installation

### Prerequisites

- Python 3.10+
- Docker (for Excel-to-image conversion)
- Anthropic API key

### Install from source

```bash
# Clone the repository
git clone https://github.com/asemiya/laminar.git
cd laminar

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install the package
pip install -e .

# For development
pip install -e ".[dev]"
```

### Build Docker image

The Docker image is used to convert Excel files to PNG images:

```bash
docker build -t xls2png-converter ./docker
```

## Configuration

### Environment Variables

Create a `.env` file in the project root (copy from `.env.example`):

```bash
cp .env.example .env
```

Edit `.env` and set your Anthropic API key:

```env
LAMINAR_ANTHROPIC_API_KEY=your-api-key-here
```

### Available Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `LAMINAR_ANTHROPIC_API_KEY` | - | Your Anthropic API key (required) |
| `LAMINAR_CLAUDE_MODEL` | `claude-sonnet-4-20250514` | Claude model to use |
| `LAMINAR_CLAUDE_MAX_TOKENS` | `8192` | Maximum response tokens |
| `LAMINAR_CLAUDE_TEMPERATURE` | `0.0` | Response temperature (0-1) |
| `LAMINAR_EXCEL_MODE` | `both` | Processing mode: `image`, `csv`, or `both` |
| `LAMINAR_OUTPUT_DIR` | `output` | Default output directory |
| `LAMINAR_LOG_LEVEL` | `INFO` | Logging level |

## Usage

### Command Line Interface

```bash
# Process a single Excel file
laminar process.xlsx

# Specify output directory
laminar process.xlsx -o ./diagrams

# Verbose output
laminar process.xlsx -v

# Show help
laminar --help
```

### Graphical Interface

```bash
# Launch the GUI
laminar-gui

# Or run directly
python -m laminar.ui.app
```

### Development Script

```bash
# Linux/Mac
./run-dev.sh ProcessFlow.xlsx

# Windows PowerShell
./run-dev.ps1 -InputFile ProcessFlow.xlsx
```

## Input Format

Laminar expects Excel spreadsheets with business process descriptions. Each sheet should contain:

- **Process steps** with titles and descriptions
- **Roles/actors** responsible for each step
- **Conditions/decisions** with Yes/No outcomes
- **Notes** (referenced with [1], [2], etc.)

See `sample.json` for the expected JSON structure that Claude generates.

## Output

For each Excel sheet, Laminar generates:

1. **`{sheet}_description.json`** - Structured JSON representation of the process
2. **`{sheet}_flowchart.mmd`** - Mermaid diagram definition

### Viewing Mermaid Diagrams

Mermaid diagrams can be viewed using:

- [Mermaid Live Editor](https://mermaid.live/)
- VS Code with Mermaid extension
- GitHub/GitLab markdown rendering
- Any Mermaid-compatible viewer

## Project Structure

```
laminar/
├── src/laminar/
│   ├── __init__.py
│   ├── cli.py              # Command-line interface
│   ├── config.py           # Configuration management
│   ├── core/
│   │   ├── constants.py    # Enums and constants
│   │   └── models.py       # Data models (Process, Role, Step)
│   ├── services/
│   │   ├── ai_analyzer.py      # Claude AI integration
│   │   ├── excel_processor.py  # Excel/CSV processing
│   │   └── mermaid_generator.py # Diagram generation
│   ├── ui/
│   │   └── app.py          # Tkinter GUI
│   └── utils/
│       ├── docker.py       # Docker utilities
│       ├── image.py        # Image encoding
│       └── logging.py      # Logging setup
├── docker/                 # Docker image for XLSX conversion
├── tests/                  # Test suite
├── sample.json            # Sample process JSON
├── sample.png             # Sample diagram output
└── pyproject.toml         # Project configuration
```

## How It Works

1. **Excel Conversion**: Docker container converts XLSX to PNG images using LibreOffice and ImageMagick
2. **Data Extraction**: Pandas extracts sheet data as CSV
3. **AI Analysis**: Claude analyzes both the visual image and CSV data to understand the business process
4. **JSON Generation**: Structured JSON is created with process steps, roles, and conditions
5. **Diagram Creation**: Mermaid flowchart is generated with proper styling and swimlanes

## Claude AI Capabilities Used

- **Vision Analysis**: Examines spreadsheet layout and visual relationships
- **Structured Output**: Generates well-formed JSON matching the template
- **Process Understanding**: Identifies implicit conditions and process logic
- **Note Matching**: Links numbered references to their definitions

## Development

### Running Tests

```bash
pytest
```

### Type Checking

```bash
mypy src/laminar
```

### Linting

```bash
ruff check src/laminar
ruff format src/laminar
```

## License

MIT License - see [LICENSE](LICENSE) for details.

## Author

Aswin Semiya

## Acknowledgments

- [Anthropic](https://anthropic.com/) for Claude AI
- [Mermaid](https://mermaid.js.org/) for diagram rendering
