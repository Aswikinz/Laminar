"""Tkinter GUI application for Laminar."""

import json
import logging
import threading
import time
import tkinter as tk
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from laminar.config import Settings, get_settings, update_api_key
from laminar.core.constants import EXCEL_EXTENSIONS
from laminar.core.models import parse_json_to_process
from laminar.services.ai_analyzer import AIAnalyzer, AIAnalysisError
from laminar.services.excel_processor import ExcelProcessor, ExcelProcessingError
from laminar.services.mermaid_generator import generate_mermaid_from_process, save_mermaid_chart
from laminar.utils.docker import DockerConverter, DockerConversionError
from laminar.utils.logging import setup_logging

logger = logging.getLogger(__name__)


@dataclass
class ProcessingState:
    """Tracks the state of file processing."""

    is_running: bool = False
    should_terminate: bool = False
    has_errors: bool = False
    current_file: str = ""
    current_sheet: str = ""
    progress: float = 0.0
    log_messages: list[str] = field(default_factory=list)


class ProcessingWorker:
    """Background worker for processing Excel files."""

    def __init__(
        self,
        input_paths: list[Path],
        output_dir: Path,
        temp_dir: Path,
        *,
        on_progress: Callable[[float, str], None] | None = None,
        on_log: Callable[[str], None] | None = None,
        on_complete: Callable[[bool], None] | None = None,
    ) -> None:
        """Initialize the worker.

        Args:
            input_paths: List of input file/directory paths.
            output_dir: Directory for output files.
            temp_dir: Directory for temporary files.
            on_progress: Callback for progress updates.
            on_log: Callback for log messages.
            on_complete: Callback when processing completes.
        """
        self.input_paths = input_paths
        self.output_dir = output_dir
        self.temp_dir = temp_dir
        self.on_progress = on_progress
        self.on_log = on_log
        self.on_complete = on_complete

        self._terminate_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._has_errors = False

    def start(self) -> None:
        """Start processing in a background thread."""
        self._terminate_event.clear()
        self._has_errors = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Signal the worker to stop."""
        self._terminate_event.set()

    def is_alive(self) -> bool:
        """Check if the worker thread is running."""
        return self._thread is not None and self._thread.is_alive()

    def _log(self, message: str) -> None:
        """Log a message."""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        formatted = f"{timestamp} - {message}"
        logger.info(message)
        if self.on_log:
            self.on_log(formatted)

    def _update_progress(self, progress: float, message: str = "") -> None:
        """Update progress."""
        if self.on_progress:
            self.on_progress(progress, message)

    def _should_stop(self) -> bool:
        """Check if processing should stop."""
        return self._terminate_event.is_set()

    def _run(self) -> None:
        """Main processing loop."""
        try:
            # Collect all files to process
            files_to_process = self._collect_files()
            if not files_to_process:
                self._log("No Excel files found to process")
                return

            total_files = len(files_to_process)
            self._log(f"Found {total_files} file(s) to process")

            # Initialize services
            docker_converter = DockerConverter()
            excel_processor = ExcelProcessor()
            ai_analyzer = AIAnalyzer()

            # Process each file
            for file_idx, file_path in enumerate(files_to_process):
                if self._should_stop():
                    break

                base_progress = (file_idx / total_files) * 100
                self._process_file(
                    file_path,
                    docker_converter,
                    excel_processor,
                    ai_analyzer,
                    base_progress,
                    total_files,
                )

            self._update_progress(100, "Complete")

            if self._should_stop():
                self._log("Processing terminated by user")
            elif self._has_errors:
                self._log("Processing completed with errors")
            else:
                self._log("All files processed successfully")

        except Exception as e:
            logger.exception("Unexpected error during processing")
            self._log(f"Error: {e}")
            self._has_errors = True

        finally:
            if self.on_complete:
                self.on_complete(not self._has_errors and not self._should_stop())

    def _collect_files(self) -> list[Path]:
        """Collect all Excel files from input paths."""
        files: list[Path] = []

        for path in self.input_paths:
            if path.is_file():
                if path.suffix.lower() in EXCEL_EXTENSIONS:
                    files.append(path)
            elif path.is_dir():
                for ext in EXCEL_EXTENSIONS:
                    files.extend(path.rglob(f"*{ext}"))

        return sorted(set(files))

    def _process_file(
        self,
        file_path: Path,
        docker_converter: DockerConverter,
        excel_processor: ExcelProcessor,
        ai_analyzer: AIAnalyzer,
        base_progress: float,
        total_files: int,
    ) -> None:
        """Process a single Excel file."""
        self._log(f"Processing: {file_path.name}")

        try:
            # Create output directory for this file
            file_output_dir = self.output_dir / file_path.stem
            file_output_dir.mkdir(parents=True, exist_ok=True)

            # Convert to images
            self._log(f"Converting {file_path.name} to images...")
            png_files = docker_converter.convert_xlsx_to_images(
                file_path, self.temp_dir
            )

            # Extract CSV data
            csv_data = excel_processor.extract_sheets_as_csv(
                file_path, self.temp_dir
            )

            self._log(
                f"Found {len(csv_data)} sheet(s): {', '.join(csv_data.keys())}"
            )

            # Process each sheet
            sheet_count = len(csv_data)
            for sheet_idx, (sheet_name, csv_content) in enumerate(csv_data.items()):
                if self._should_stop():
                    return

                if sheet_idx >= len(png_files):
                    self._log(f"Warning: No image for sheet '{sheet_name}'")
                    continue

                self._log(f"Analyzing sheet: {sheet_name}")

                # Calculate progress
                file_progress = (1 / total_files) * 100
                sheet_progress = (sheet_idx / sheet_count) * file_progress
                self._update_progress(
                    base_progress + sheet_progress,
                    f"{file_path.name} - {sheet_name}",
                )

                # Analyze with AI
                json_result = ai_analyzer.analyze_sheet(
                    csv_data=csv_content,
                    sheet_name=sheet_name,
                    image_path=png_files[sheet_idx],
                )

                # Save JSON
                json_path = file_output_dir / f"{sheet_name}_description.json"
                json_path.write_text(json.dumps(json_result, indent=2))

                # Generate Mermaid diagram
                process = parse_json_to_process(json_result)
                mermaid_chart = generate_mermaid_from_process(process)

                mermaid_path = file_output_dir / f"{sheet_name}_flowchart.mmd"
                save_mermaid_chart(mermaid_chart, mermaid_path)

                self._log(f"Generated: {mermaid_path.name}")

        except (DockerConversionError, ExcelProcessingError, AIAnalysisError) as e:
            self._log(f"Error processing {file_path.name}: {e}")
            self._has_errors = True
        except Exception as e:
            logger.exception("Unexpected error processing %s", file_path)
            self._log(f"Error processing {file_path.name}: {e}")
            self._has_errors = True


class LaminarApp:
    """Main GUI application for Laminar."""

    def __init__(self, root: tk.Tk) -> None:
        """Initialize the application.

        Args:
            root: The Tk root window.
        """
        self.root = root
        self.root.title("Laminar - Excel to Mermaid")
        self.root.minsize(600, 400)

        self._settings = get_settings()
        self._worker: ProcessingWorker | None = None

        self._setup_ui()
        self._configure_grid()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        # Main frame
        self.main_frame = ttk.Frame(self.root, padding=10)
        self.main_frame.grid(sticky="nsew")

        # Input selection
        ttk.Label(self.main_frame, text="Input File(s) or Folder:").grid(
            row=0, column=0, sticky="w", pady=5
        )

        self.input_var = tk.StringVar()
        self.input_var.trace_add("write", self._validate_inputs)
        self.input_entry = ttk.Entry(
            self.main_frame, textvariable=self.input_var, width=50
        )
        self.input_entry.grid(row=0, column=1, sticky="ew", padx=5)

        self.browse_input_btn = ttk.Button(
            self.main_frame, text="Browse", command=self._browse_input
        )
        self.browse_input_btn.grid(row=0, column=2, padx=5)

        # Output directory
        ttk.Label(self.main_frame, text="Output Directory:").grid(
            row=1, column=0, sticky="w", pady=5
        )

        self.output_var = tk.StringVar()
        self.output_var.trace_add("write", self._validate_inputs)
        self.output_entry = ttk.Entry(
            self.main_frame, textvariable=self.output_var, width=50
        )
        self.output_entry.grid(row=1, column=1, sticky="ew", padx=5)

        self.browse_output_btn = ttk.Button(
            self.main_frame, text="Browse", command=self._browse_output
        )
        self.browse_output_btn.grid(row=1, column=2, padx=5)

        # Progress bar
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(
            self.main_frame, variable=self.progress_var, maximum=100
        )
        self.progress_bar.grid(
            row=2, column=0, columnspan=3, sticky="ew", pady=10
        )

        # Log display
        self.log_frame = ttk.Frame(self.main_frame)
        self.log_frame.grid(row=3, column=0, columnspan=3, sticky="nsew", pady=5)

        self.log_listbox = tk.Listbox(self.log_frame, height=10)
        self.log_listbox.pack(side="left", fill="both", expand=True)

        log_scrollbar = ttk.Scrollbar(
            self.log_frame, orient="vertical", command=self.log_listbox.yview
        )
        log_scrollbar.pack(side="right", fill="y")
        self.log_listbox.config(yscrollcommand=log_scrollbar.set)

        # Buttons
        self.button_frame = ttk.Frame(self.main_frame)
        self.button_frame.grid(row=4, column=0, columnspan=3, pady=10)

        self.run_btn = ttk.Button(
            self.button_frame, text="Run", command=self._toggle_processing
        )
        self.run_btn.pack(side="left", padx=5)
        self.run_btn.config(state="disabled")

        self.export_log_btn = ttk.Button(
            self.button_frame, text="Export Log", command=self._export_log
        )
        self.export_log_btn.pack(side="left", padx=5)
        self.export_log_btn.config(state="disabled")

        self.settings_btn = ttk.Button(
            self.button_frame, text="Settings", command=self._open_settings
        )
        self.settings_btn.pack(side="left", padx=5)

    def _configure_grid(self) -> None:
        """Configure grid weights for responsive layout."""
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        self.main_frame.columnconfigure(1, weight=1)
        self.main_frame.rowconfigure(3, weight=1)

    def _browse_input(self) -> None:
        """Open dialog to select input files or directory."""
        choice = messagebox.askyesno(
            "Select Input Type",
            "Do you want to select a directory?\n\n"
            "Yes: Select a directory\n"
            "No: Select individual files",
        )

        if choice:
            path = filedialog.askdirectory()
            if path:
                self.input_var.set(path)
        else:
            paths = filedialog.askopenfilenames(
                filetypes=[("Excel files", "*.xlsx *.xlsm *.xls")]
            )
            if paths:
                self.input_var.set(";".join(paths))

    def _browse_output(self) -> None:
        """Open dialog to select output directory."""
        path = filedialog.askdirectory()
        if path:
            self.output_var.set(path)

    def _validate_inputs(self, *_: object) -> None:
        """Validate input and output paths."""
        input_paths = self.input_var.get().split(";")
        output_dir = self.output_var.get()

        valid = all(Path(p).exists() for p in input_paths if p)
        valid = valid and bool(output_dir) and Path(output_dir).is_dir()

        state = "normal" if valid else "disabled"
        self.run_btn.config(state=state)

    def _toggle_processing(self) -> None:
        """Start or stop processing."""
        if self._worker and self._worker.is_alive():
            self._worker.stop()
            self.run_btn.config(text="Stopping...")
            self.run_btn.config(state="disabled")
        else:
            self._start_processing()

    def _start_processing(self) -> None:
        """Start the processing worker."""
        input_paths = [
            Path(p) for p in self.input_var.get().split(";") if p
        ]
        output_dir = Path(self.output_var.get())
        temp_dir = Path(__file__).parent.parent.parent.parent / "output" / "temp"

        self.log_listbox.delete(0, tk.END)
        self.progress_var.set(0)

        self._set_controls_enabled(False)
        self.run_btn.config(text="Terminate", state="normal")

        self._worker = ProcessingWorker(
            input_paths=input_paths,
            output_dir=output_dir,
            temp_dir=temp_dir,
            on_progress=self._on_progress,
            on_log=self._on_log,
            on_complete=self._on_complete,
        )
        self._worker.start()

    def _on_progress(self, progress: float, message: str) -> None:
        """Handle progress updates."""
        self.root.after(0, lambda: self.progress_var.set(progress))

    def _on_log(self, message: str) -> None:
        """Handle log messages."""
        def update() -> None:
            self.log_listbox.insert(tk.END, message)
            self.log_listbox.yview(tk.END)

        self.root.after(0, update)

    def _on_complete(self, success: bool) -> None:
        """Handle processing completion."""
        def update() -> None:
            self._set_controls_enabled(True)
            self.run_btn.config(text="Run")
            self.export_log_btn.config(state="normal")

            if success:
                messagebox.showinfo("Complete", "Processing completed successfully!")
            elif self._worker and not self._worker._terminate_event.is_set():
                messagebox.showwarning(
                    "Complete with Errors",
                    "Processing completed with some errors. Check the log for details.",
                )

        self.root.after(0, update)

    def _set_controls_enabled(self, enabled: bool) -> None:
        """Enable or disable input controls."""
        state = "normal" if enabled else "disabled"
        self.input_entry.config(state=state)
        self.output_entry.config(state=state)
        self.browse_input_btn.config(state=state)
        self.browse_output_btn.config(state=state)
        self.settings_btn.config(state=state)

    def _export_log(self) -> None:
        """Export the log to a file."""
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt")],
        )
        if path:
            messages = self.log_listbox.get(0, tk.END)
            Path(path).write_text("\n".join(messages))
            messagebox.showinfo("Export", f"Log exported to {path}")

    def _open_settings(self) -> None:
        """Open the settings dialog."""
        SettingsDialog(self.root, self._settings)


class SettingsDialog:
    """Settings dialog for API key configuration."""

    def __init__(self, parent: tk.Tk, settings: Settings) -> None:
        """Initialize the dialog.

        Args:
            parent: Parent window.
            settings: Current settings.
        """
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Settings")
        self.dialog.transient(parent)
        self.dialog.grab_set()

        self.settings = settings
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        frame = ttk.Frame(self.dialog, padding=10)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Anthropic API Key:").grid(
            row=0, column=0, sticky="w", pady=5
        )

        self.api_key_var = tk.StringVar(
            value=self.settings.anthropic_api_key.get_secret_value()
        )
        api_key_entry = ttk.Entry(
            frame, textvariable=self.api_key_var, width=50, show="*"
        )
        api_key_entry.grid(row=0, column=1, padx=5, pady=5)

        button_frame = ttk.Frame(frame)
        button_frame.grid(row=1, column=0, columnspan=2, pady=10)

        ttk.Button(button_frame, text="Save", command=self._save).pack(
            side="left", padx=5
        )
        ttk.Button(button_frame, text="Cancel", command=self.dialog.destroy).pack(
            side="left", padx=5
        )

    def _save(self) -> None:
        """Save the settings."""
        api_key = self.api_key_var.get().strip()
        if not api_key:
            messagebox.showerror("Error", "API Key cannot be empty")
            return

        try:
            update_api_key(api_key)
            messagebox.showinfo("Success", "Settings saved successfully")
            self.dialog.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save settings: {e}")


def main() -> None:
    """Main entry point for the GUI application."""
    setup_logging(level="INFO")

    root = tk.Tk()
    LaminarApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
