import openai
import base64
import os
import credentials
import pandas as pd
from io import StringIO
from openai import OpenAI
import subprocess
import sys
import json
from business_process import parse_json_to_process
from mermaid import generate_mermaid_from_process, save_mermaid_chart

# Function to set OpenAI API key
def set_openai_api_key(api_key):
    openai.api_key = api_key
    global client
    client = OpenAI(api_key=api_key)

# Initialize OpenAI client
set_openai_api_key(credentials.OPENAI_API_KEY)

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def get_text_data_from_xlsx(xlsx_path, output_dir):
    # Read the Excel file
    xls = pd.ExcelFile(xlsx_path)
    csv_data = {}
    
    # Convert each sheet to CSV and store in memory
    for sheet_name in xls.sheet_names:
        df = pd.read_excel(xlsx_path, sheet_name=sheet_name)
        df = df.fillna('--')
        df.columns = [col if not col.startswith('Unnamed:') else '--' for col in df.columns]
        df = df.map(lambda x: str(x).replace(';', ',') if isinstance(x, str) else x)
        
        csv_buffer = StringIO()
        df.to_csv(csv_buffer, index=False, sep=';')
        csv_data[sheet_name] = csv_buffer.getvalue()
        
        # Save CSV to file for logging
        csv_log_path = os.path.join(output_dir, f"{sheet_name}.csv")
        with open(csv_log_path, 'w') as csv_file:
            csv_file.write(csv_buffer.getvalue())
    
    return csv_data

def generate_json_for_sheet(text_data, sheet_name, image_path, output_dir):
    # Encode the image
    encoded_image = encode_image(image_path)
    encoded_sample = encode_image('./sample.png')
    
    # Read the sample JSON file
    with open('sample.json', 'r') as file:
        sample_json_content = file.read()
    
    # Use OpenAI to generate a JSON description of the diagram
    messages = [
        {"role": "system", "content": "You are business process analyzer which is analyzing business process description in the form of spreadsheet based on visual representation of the spreadsheet and CSV-formatted extract. Based on this data you are producing a JSON document with description of the business process"},
        {"role": "user", "content": f"Here is the sample image which reflects what kind of diagram what we will build. This image is only for information purposes and not related to the particular business processes that we will handle."},
        {"role": "user", "content": [{"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded_sample}"}}]},
        {"role": "user", "content": f"Here is the image for analysis from sheet {sheet_name}:"},
        {"role": "user", "content": [{"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded_image}"}}]},
        {"role": "user", "content": f"Here is the data from sheet {sheet_name} in CSV format:\n{text_data}"},
        {"role": "user", "content": "Use the following JSON format as a template for generating the JSON description of the diagram. Remember that JSON sample has nothing in common with the business process we are working with, except the data format."},
        {"role": "user", "content": sample_json_content},
        {"role": "user", "content": """Generate a JSON description for a diagram based on the provided data and images, ensuring it matches the format of the sample JSON. Make sure that notes for each process step are appended to according notes array in JSON output. An important criteria is to make sure no single character of data from the Excel spreadsheet is lost when we generate the JSON representation of the business process. Make sure to analyze the logic of the process, linking between the steps and especially CONDITIONS and CYCLES which occur in the business process. Add CONDITION:: blocks as in sample.json. Pay attention: conditions may be implicitly present in the process description, understand the underlying logic and introduce necessary conditions. 
         
Remember that conditions may require additional explication. "yes_when" and "no_when" blocks must not be added for simple yes/no questions but make sure to add them in case the condition is requiring some details.
         
Determine process start and end. SYSTEM::START and SYSTEM::END are obligatory items. SYSTEM::START must be linked to the first actual step in the process, so it MUST have the next_step provided. Make sure to find all steps that lead to process finish and trace them to SYSTEM::END. Carefully analyze process descriptions. There can be implicitly multiple steps with their own steps and conditions hidden there. There can be notes referred in square brackets in notes section, so you should properly pick up notes from their row and assign to their rightful process steps.
         
For example, this description: "BU[1] Onboards the customer after cheeking CR[2],DSCR[3] income, Client Vehicle and Handles CIF[4] creation and support document[5] submission" must be matched with these notes [1]Business Unit.
[2]Credit Rating.
[3] Debt-service coverage Ratio.
[4]Client Information File.
[5]support documents include: salary slips, bank statements, documents relating to the vehicle and other documents depending on the requirement.  

and this would unfold into defining several independent process steps within the JSON file: check credit rating; check debt-service coverage ratio, check client income, with conditions to terminate the process in case any check fails
         
Make sure to properly distinguish between SYSTEM::END and SYSTEM::ABORT - while END is a successful completion of the business process, ABORT means abrupt termination due to certain condition
         
Make sure to have all roles and step identifiers unique. For example, step_identifier and CONDITION::step_identifier are the same. 
"""}
    ]
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0,
        max_tokens=4096,
        response_format={ "type": "json_object" }
    )
    
    json_description = response.choices[0].message.content
    
    # Save the JSON description to a file for logging
    json_log_path = os.path.join(output_dir, f"{sheet_name}_description.json")
    with open(json_log_path, 'w') as json_file:
        json_file.write(json_description)
    
    return json_description

def convert_xlsx_to_images(xlsx_path, output_dir):
    # Run the docker-based conversion
    subprocess.run([
        'docker', 'run', '--rm',
        '-v', f"{os.path.abspath(output_dir)}:/output",
        '-v', f"{os.path.abspath(os.path.dirname(xlsx_path))}:/input",
        'xls2png-converter',
        f"/input/{os.path.basename(xlsx_path)}", "/output"
    ], check=True)

def main():
    if len(sys.argv) != 2:
        print("Usage: python main.py <input_xlsx_file>")
        sys.exit(1)

    xlsx_path = sys.argv[1]
    output_dir = "output"
    
    # Convert XLSX to PDF and images
    convert_xlsx_to_images(xlsx_path, output_dir)
    
    csv_data = get_text_data_from_xlsx(xlsx_path, output_dir)
    
    image_paths = [os.path.join(output_dir, f"{idx}.png") for idx in range(len(csv_data))]
    existing_image_paths = [path for path in image_paths if os.path.exists(path)]
    
    for idx, (sheet_name, text_data) in enumerate(csv_data.items()):
        if idx < len(existing_image_paths):
            # Generate JSON description for each sheet
            json_description = generate_json_for_sheet(text_data, sheet_name, existing_image_paths[idx], output_dir)
            process = parse_json_to_process(json.loads(json_description))
            mermaid_chart = generate_mermaid_from_process(process)
            save_mermaid_chart(mermaid_chart, os.path.join(output_dir, f"{sheet_name}_flowchart.mmd"))

if __name__ == "__main__":
    main()