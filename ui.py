import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
import subprocess
import time
import threading
import credentials
import json
from main import get_text_data_from_xlsx, generate_json_for_sheet, parse_json_to_process, set_openai_api_key
from mermaid import generate_mermaid_from_process, save_mermaid_chart

API_KEY_FILE = "openai_key.txt"

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Excel to Mermaid")

        # Configure grid to make elements responsive
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        # Main Frame
        self.main_frame = tk.Frame(self.root)
        self.main_frame.grid(sticky="nsew", padx=10, pady=10)

        # Configure grid for main_frame
        for i in range(3):
            self.main_frame.columnconfigure(i, weight=1)
        for i in range(7):
            self.main_frame.rowconfigure(i, weight=1)

        # Excel File/Folder Upload
        self.upload_label = tk.Label(self.main_frame, text="Select Excel File(s) or Folder(s):")
        self.upload_label.grid(row=0, column=0, sticky="w")
        self.upload_button = tk.Button(self.main_frame, text="Browse", command=self.show_upload_options)
        self.upload_button.grid(row=0, column=1, padx=5, sticky="ew")
        self.file_paths_var = tk.StringVar()
        self.file_paths_var.trace("w", self.validate_paths)
        self.file_paths_entry = tk.Entry(self.main_frame, textvariable=self.file_paths_var, width=50)
        self.file_paths_entry.grid(row=0, column=2, padx=5, sticky="ew")

        # Output Directory
        self.output_label = tk.Label(self.main_frame, text="Output Directory:")
        self.output_label.grid(row=1, column=0, sticky="w")
        self.output_button = tk.Button(self.main_frame, text="Browse", command=self.select_output_dir)
        self.output_button.grid(row=1, column=1, padx=5, sticky="ew")
        self.output_dir_var = tk.StringVar()
        self.output_dir_var.trace("w", self.validate_paths)
        self.output_dir_entry = tk.Entry(self.main_frame, textvariable=self.output_dir_var, width=50)
        self.output_dir_entry.grid(row=1, column=2, padx=5, sticky="ew")

        # Progress Bar
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(self.main_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.grid(row=2, column=0, columnspan=3, pady=10, sticky="ew")

        # Log List
        self.log_listbox = tk.Listbox(self.main_frame, height=10, width=80)
        self.log_listbox.grid(row=3, column=0, columnspan=3, pady=5, sticky="nsew")

        # Run/Terminate Button
        self.run_terminate_button = tk.Button(self.main_frame, text="Run", command=self.toggle_process)
        self.run_terminate_button.grid(row=4, column=0, columnspan=3, pady=10, sticky="ew")
        self.run_terminate_button.config(state=tk.DISABLED)

        # Export Log Button
        self.export_log_button = tk.Button(self.main_frame, text="Export Log", command=self.export_log)
        self.export_log_button.grid(row=5, column=0, columnspan=3, pady=5, sticky="ew")
        self.export_log_button.config(state=tk.DISABLED)

        # Settings Tab
        self.settings_button = tk.Button(self.main_frame, text="Settings", command=self.open_settings)
        self.settings_button.grid(row=6, column=0, columnspan=3, pady=5, sticky="ew")

        self.processing_thread = None
        self.terminate_flag = threading.Event()
        self.error_occurred = False  # Track if an error occurred

    def show_upload_options(self):
        option = messagebox.askquestion("Select Option", "Do you want to process a whole directory?", icon='question', type='yesno', default='yes', detail="No: Single or multiple file(s)\nYes: Directory contents")
        if option == 'no':
            self.upload_files()
        elif option == 'yes':
            self.upload_directory()

    def upload_files(self):
        file_paths = filedialog.askopenfilenames(filetypes=[("Excel files", "*.xlsx *.xlsm *.xls")])
        self.file_paths_var.set(';'.join(file_paths))
        self.list_eligible_files(file_paths)

    def upload_directory(self):
        folder_path = filedialog.askdirectory()
        if folder_path:
            self.file_paths_var.set(folder_path)
            self.list_eligible_files([folder_path])

    def select_output_dir(self):
        output_dir = filedialog.askdirectory()
        if output_dir:
            self.output_dir_var.set(output_dir)

    def validate_paths(self, *args):
        input_paths = self.file_paths_var.get().split(';')
        output_dir = self.output_dir_var.get()
        if all(os.path.exists(path) for path in input_paths) and os.path.isdir(output_dir):
            self.run_terminate_button.config(state=tk.NORMAL)
        else:
            self.run_terminate_button.config(state=tk.DISABLED)

    def list_eligible_files(self, paths):
        self.log_listbox.delete(0, tk.END)
        for path in paths:
            if os.path.isfile(path):
                self.log(f"File: {path}")
            elif os.path.isdir(path):
                for root, dirs, files in os.walk(path):
                    for file in files:
                        if file.endswith(('.xlsx', '.xlsm', '.xls')):
                            self.log(f"File: {os.path.join(root, file)}")

    def toggle_process(self):
        if self.processing_thread and self.processing_thread.is_alive():
            self.terminate_process()
        else:
            self.start_process()

    def start_process(self):
        self.disable_controls()
        self.run_terminate_button.config(text="Terminate", state=tk.NORMAL)  # Enable the terminate button
        self.terminate_flag.clear()
        self.error_occurred = False  # Reset error flag
        self.processing_thread = threading.Thread(target=self.run_process)
        self.processing_thread.start()

    def terminate_process(self):
        self.terminate_flag.set()
        self.run_terminate_button.config(text="Terminating...", state=tk.DISABLED)

    def run_process(self):
        input_paths = self.file_paths_var.get().split(';')
        output_dir = self.output_dir_var.get()
        if not input_paths or not output_dir:
            messagebox.showerror("Error", "Please select both input files/folders and an output directory.")
            self.enable_controls()
            return

        total_steps = len(input_paths) * 5
        current_step = 0

        temp_dir = os.path.join(os.path.dirname(__file__), "output")
        os.makedirs(temp_dir, exist_ok=True)

        for path in input_paths:
            if self.terminate_flag.is_set():
                break
            if os.path.isfile(path):
                files_to_process = [path]
            else:
                files_to_process = [os.path.join(dp, f) for dp, dn, filenames in os.walk(path) for f in filenames if f.endswith(('.xlsx', '.xlsm', '.xls'))]

            for file in files_to_process:
                if self.terminate_flag.is_set():
                    break
                self.log(f"Processing {file}")
                self.update_progress(current_step, total_steps)
                try:
                    self.convert_xlsx_to_images(file, temp_dir)
                    self.log(f"Converted {file} to images and CSV")
                    current_step += 1
                    self.update_progress(current_step, total_steps)

                    csv_data = get_text_data_from_xlsx(file, temp_dir)
                    self.log(f"Found {len(csv_data)} worksheets in {file}: {', '.join(csv_data.keys())}")
                    image_paths = [os.path.join(temp_dir, f"{idx}.png") for idx in range(len(csv_data))]
                    existing_image_paths = [path for path in image_paths if os.path.exists(path)]
                    
                    file_output_dir = os.path.join(output_dir, os.path.splitext(os.path.basename(file))[0])
                    os.makedirs(file_output_dir, exist_ok=True)

                    for idx, (sheet_name, text_data) in enumerate(csv_data.items()):
                        if idx < len(existing_image_paths):
                            if self.terminate_flag.is_set():
                                break
                            self.log(f"Processing sheet: {sheet_name}")
                            json_description = generate_json_for_sheet(text_data, sheet_name, existing_image_paths[idx], temp_dir)
                            process = parse_json_to_process(json.loads(json_description))
                            mermaid_chart = generate_mermaid_from_process(process)
                            mermaid_file_path = os.path.join(file_output_dir, f"{sheet_name}_flowchart.mmd")
                            save_mermaid_chart(mermaid_chart, mermaid_file_path)
                            self.log(f"Generated mermaid diagram: {mermaid_file_path}")
                            current_step += 1
                            self.update_progress(current_step, total_steps)

                except Exception as e:
                    self.log(f"Error processing {file}: {e}")
                    messagebox.showerror("Error", f"An error occurred while processing {file}: {e}")
                    self.error_occurred = True  # Set error flag

        self.progress_var.set(100)
        if not self.terminate_flag.is_set():
            if not self.error_occurred:
                self.log("All files processed successfully.")
                messagebox.showinfo("Success", "All processes completed successfully.")
            else:
                self.log("Process completed with errors.")
                messagebox.showwarning("Warning", "Process completed with errors. Check the log for details.")
        else:
            self.log("Process terminated by user.")
        self.enable_controls()
        self.run_terminate_button.config(text="Run")
        self.export_log_button.config(state=tk.NORMAL)

    def convert_xlsx_to_images(self, xlsx_path, temp_dir):
        subprocess.run([
            'docker', 'run', '--rm',
            '-v', f"{os.path.abspath(temp_dir)}:/output",
            '-v', f"{os.path.abspath(os.path.dirname(xlsx_path))}:/input",
            'xls2png-converter',
            f"/input/{os.path.basename(xlsx_path)}", "/output"
        ], check=True)

    def update_progress(self, current_step, total_steps):
        progress = (current_step / total_steps) * 100
        self.progress_var.set(progress)
        self.root.update_idletasks()

    def log(self, message):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"{timestamp} - {message}"
        self.log_listbox.insert(tk.END, log_message)
        self.log_listbox.yview(tk.END)
        with open("log.txt", "a") as log_file:
            log_file.write(log_message + "\n")
        self.export_log_button.config(state=tk.NORMAL if self.log_listbox.size() > 0 and (self.processing_thread is None or not self.processing_thread.is_alive()) else tk.DISABLED        )

    def export_log(self):
        log_file_path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text files", "*.txt")])
        if log_file_path:
            with open(log_file_path, "w") as log_file:
                log_file.writelines("\n".join(self.log_listbox.get(0, tk.END)))
            messagebox.showinfo("Export Log", f"Log exported to {log_file_path}")

    def open_settings(self):
        settings_window = tk.Toplevel(self.root)
        settings_window.title("Settings")

        api_key_label = tk.Label(settings_window, text="OpenAI API Key:")
        api_key_label.grid(row=0, column=0, sticky="w", padx=10, pady=10)
        self.api_key_var = tk.StringVar(value=self.load_api_key())
        api_key_entry = tk.Entry(settings_window, textvariable=self.api_key_var, width=50)
        api_key_entry.grid(row=0, column=1, padx=10, pady=10)

        save_button = tk.Button(settings_window, text="Save", command=self.save_settings)
        save_button.grid(row=1, column=0, columnspan=2, pady=10)

    def save_settings(self):
        api_key = self.api_key_var.get()
        if api_key:
            with open(API_KEY_FILE, "w") as f:
                f.write(api_key)
            set_openai_api_key(api_key)  # Update the OpenAI API key dynamically
            messagebox.showinfo("Settings", "Settings saved successfully.")
        else:
            messagebox.showerror("Error", "API Key cannot be empty.")

    def load_api_key(self):
        if os.path.exists(API_KEY_FILE):
            with open(API_KEY_FILE, "r") as f:
                return f.read().strip()
        return credentials.OPENAI_API_KEY

    def disable_controls(self):
        self.upload_button.config(state=tk.DISABLED)
        self.output_button.config(state=tk.DISABLED)
        self.run_terminate_button.config(state=tk.DISABLED)
        self.settings_button.config(state=tk.DISABLED)
        self.file_paths_entry.config(state=tk.DISABLED)
        self.output_dir_entry.config(state=tk.DISABLED)

    def enable_controls(self):
        self.upload_button.config(state=tk.NORMAL)
        self.output_button.config(state=tk.NORMAL)
        self.run_terminate_button.config(state=tk.NORMAL)
        self.settings_button.config(state=tk.NORMAL)
        self.file_paths_entry.config(state=tk.NORMAL)
        self.output_dir_entry.config(state=tk.NORMAL)

if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()