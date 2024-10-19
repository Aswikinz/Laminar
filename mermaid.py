from business_process import Process

def strip_prefix(step_id):
    prefixes = ["CONDITION::", "SYSTEM::"]
    for prefix in prefixes:
        if step_id.startswith(prefix):
            return step_id.replace(prefix, "")
    return step_id

def sanitize_label(label):
    """
    Sanitize the label to remove invalid characters for mermaid syntax.
    """
    return label.replace('*', '')

def format_step_label(step):
    """
    Format the step label to include additional information from the JSON document.
    """
    label = f"**{sanitize_label(step.step_title)}**"
    if step.manual_system and step.manual_system.upper() == "MANUAL":
        label += f"<br/>*{sanitize_label(step.manual_system)}*"
    elif step.manual_system:
        label += f"<br/>SYSTEM *{sanitize_label(step.manual_system)}*"
    if step.user_role_code_user_id_user_name:
        label += f"<br/>LOGIN *{sanitize_label(step.user_role_code_user_id_user_name)}*"
    if step.password_in_test_system:
        label += f"<br/>PASSWORD *{sanitize_label(step.password_in_test_system)}*"
    if step.program_id_t_code_screen_name:
        label += f"<br/>LOCATION *{sanitize_label(step.program_id_t_code_screen_name)}*"
    return label

def generate_mermaid_from_process(process: Process) -> str:
    """
    Generate a Mermaid flowchart from a Process object.
    """
    mermaid = "flowchart TD\n"
    role_subgraphs = {}
    links = []
    link_styles = []  # Separate list for link styles
    link_counter = 0  # Global accumulator for link numbering
    descriptions = []  # List to hold step descriptions
    note_ids = []  # List to hold IDs of nodes with notes

    # Create subgraphs for each role
    for role in process.process_roles:
        role_subgraphs[role.role_id] = f"subgraph {role.role_id} [{role.role_title}]\n"

    # Add steps to the appropriate subgraph or main graph if no role
    for step in process.process_steps:
        step_id = step.step_id
        stripped_step_id = strip_prefix(step_id)
        step_line = ""
        if step_id.startswith("CONDITION::"):
            condition_id = step_id.replace("CONDITION::", "")
            formatted_label = format_step_label(step)
            step_line = f"    {condition_id}@{{ shape: hexagon, label: \"{formatted_label}\" }}\n"
        elif step_id.startswith("SYSTEM::START"):
            step_line = f"    START@{{ shape: circle, label: \"START\" }}\n"
        elif step_id.startswith("SYSTEM::END"):
            step_line = f"    END@{{ shape: double-circle, label: \"END\" }}\n"
        elif step_id.startswith("SYSTEM::ABORT"):
            step_line = f"    ABORT@{{ shape: double-circle, label: \"ABORT\" }}\n"
        else:
            formatted_label = format_step_label(step)
            step_line = f"    {step_id}({formatted_label})\n"

        if step.step_role:
            role_subgraphs[step.step_role] += step_line
        else:
            mermaid += step_line

        # Collect step descriptions to be added later
        if step.step_description or step.step_notes:
            description_id = f"{stripped_step_id}_desc"
            description_line = f"{description_id}@{{shape: braces, label: \"{sanitize_label(step.step_description or 'Notes')}\"}}\n"
            if step.step_role:
                role_subgraphs[step.step_role] += description_line
            else:
                descriptions.append(description_line)
            links.append(f"{stripped_step_id} -.-o {description_id}")
            link_styles.append(f"linkStyle {link_counter} stroke:#d3d3d3,stroke-width:2px;")  # Light gray link
            link_counter += 1

        # Add notes as separate blocks linked to descriptions
        if step.step_notes:
            for note in step.step_notes:
                note_id = f"{stripped_step_id}_note_{step.step_notes.index(note)}"
                descriptions.append(f"{note_id}@{{shape: comment, label: \"{sanitize_label(note)}\"}}\n")
                links.append(f"{description_id} -.-o {note_id}")
                link_styles.append(f"linkStyle {link_counter} stroke:#d3d3d3,stroke-width:2px;")  # Light gray link
                link_counter += 1
                note_ids.append(note_id)  # Add to note_ids list

        def add_link(source_id, target_id, condition_text="", style=""):
            nonlocal link_counter
            target_step = next((s for s in process.process_steps if strip_prefix(s.step_id) == target_id), None)
            if target_step:
                if condition_text:
                    links.append(f"{strip_prefix(source_id)} -- {condition_text} --> {target_id}")
                else:
                    links.append(f"{strip_prefix(source_id)} --> {target_id}")
                # Append style to link_styles list
                if style:
                    link_styles.append(f"linkStyle {link_counter} {style}")
                link_counter += 1

        if step.next_step:
            add_link(step_id, strip_prefix(step.next_step))
        if step.next_step_yes:
            condition_text = step.additional_attributes.get("yes_when", "yes")
            add_link(step_id, strip_prefix(step.next_step_yes), condition_text, "stroke:#0f0,stroke-width:2px;")
        if step.next_step_no:
            condition_text = step.additional_attributes.get("no_when", "no")
            add_link(step_id, strip_prefix(step.next_step_no), condition_text, "stroke:#f00,stroke-width:2px;")

    # Close each subgraph and add to the main mermaid string
    for subgraph in role_subgraphs.values():
        subgraph += "end\n"
        mermaid += subgraph

    # Add step descriptions at the end
    for description in descriptions:
        mermaid += description        

    # Add links outside of subgraphs
    for link in links:
        mermaid += f"{link}\n"

    # Append link styles at the bottom
    for style in link_styles:
        mermaid += f"{style}\n"

    # Define class for notes with dark gray text
    mermaid += "classDef noteClass fill:#fff,stroke:#333,color:#aaaaaa;\n"
    # Apply class to each note node individually
    for note_id in note_ids:
        mermaid += f"class {note_id} noteClass;\n"

    return mermaid

def save_mermaid_chart(mermaid_chart: str, output_file: str):
    """
    Save the Mermaid chart to a file.
    """
    with open(output_file, 'w') as file:
        file.write(mermaid_chart)