"""Mermaid diagram generation service.

Generates flowcharts that resemble professional business process diagrams with:
- Horizontal swimlanes for roles
- Stadium-shaped Start/End nodes
- Diamond-shaped decision points
- Rounded rectangles for process steps
- Color-coded paths (green for Yes, red for No)
- System steps highlighted in blue/gray
"""

import logging
from pathlib import Path

from laminar.core.constants import StepPrefix, SystemStep
from laminar.core.models import Process, Step

logger = logging.getLogger(__name__)

# Color scheme matching sample.png
COLORS = {
    "header_bg": "#4a86c7",  # Blue header background
    "header_text": "#ffffff",  # White header text
    "swimlane_bg": "#e8f4fc",  # Light blue swimlane background
    "system_step_bg": "#b8d4e8",  # Highlighted system step background
    "step_bg": "#ffffff",  # White step background
    "step_border": "#333333",  # Dark border
    "yes_path": "#2e7d32",  # Green for Yes path
    "no_path": "#c62828",  # Red for No path
    "note_text": "#666666",  # Gray note text
}


def _sanitize_label(label: str) -> str:
    """Sanitize a label for Mermaid syntax.

    Args:
        label: The label to sanitize.

    Returns:
        Sanitized label string.
    """
    # Escape characters that break Mermaid syntax
    return (
        label.replace('"', "'")
        .replace("*", "")
        .replace("#", "")
        .replace("&", "and")
        .replace("<", "")
        .replace(">", "")
    )


def _format_step_label(step: Step, *, include_metadata: bool = True) -> str:
    """Format a step label with optional metadata.

    Args:
        step: The step to format.
        include_metadata: Whether to include system/login metadata.

    Returns:
        Formatted label string.
    """
    title = _sanitize_label(step.step_title)

    if not include_metadata:
        return title

    parts = [title]

    if step.manual_system:
        if step.manual_system.upper() == "MANUAL":
            parts.append(f"[{step.manual_system}]")
        else:
            parts.append(f"[System: {_sanitize_label(step.manual_system)}]")

    if step.program_location:
        parts.append(f"[{_sanitize_label(step.program_location)}]")

    return "<br>".join(parts)


class MermaidGenerator:
    """Generates Mermaid flowchart diagrams from Process objects.

    Creates professional-looking diagrams with:
    - Swimlanes organized by role
    - Proper shapes for different step types
    - Color-coded conditional paths
    - Notes section at the bottom
    """

    def __init__(self, *, include_notes: bool = True, include_metadata: bool = False) -> None:
        """Initialize the Mermaid generator.

        Args:
            include_notes: Whether to include step notes in the diagram.
            include_metadata: Whether to include system/login metadata in labels.
        """
        self.include_notes = include_notes
        self.include_metadata = include_metadata
        self._link_counter = 0
        self._link_styles: list[str] = []

    def generate(self, process: Process) -> str:
        """Generate a Mermaid flowchart from a Process object.

        Args:
            process: The process to convert.

        Returns:
            Mermaid flowchart definition string.
        """
        self._reset()

        lines: list[str] = []

        # Use top-down layout for swimlanes
        lines.append("flowchart TD")

        # Add title as a comment
        if process.process_name:
            lines.append(f"    %% {process.process_name}")
            lines.append("")

        # Build swimlanes (subgraphs) for each role
        role_steps: dict[str, list[Step]] = {role.role_id: [] for role in process.process_roles}
        system_steps: list[Step] = []
        orphan_steps: list[Step] = []  # Steps without roles (non-system)

        for step in process.process_steps:
            if step.is_system_step:
                system_steps.append(step)
            elif step.step_role and step.step_role in role_steps:
                role_steps[step.step_role].append(step)
            else:
                orphan_steps.append(step)

        # Add system start node first (outside subgraphs)
        for step in system_steps:
            if step.step_id == SystemStep.START:
                lines.append(self._format_step_node(step))

        # Add orphan steps (steps without roles) outside subgraphs
        for step in orphan_steps:
            lines.append(self._format_step_node(step))

        # Add role subgraphs
        for role in process.process_roles:
            steps = role_steps.get(role.role_id, [])
            if not steps:
                continue

            lines.append("")
            lines.append(f"    subgraph {role.role_id}[{role.role_title}]")

            for step in steps:
                lines.append("    " + self._format_step_node(step))

            lines.append("    end")

        # Add system end/abort nodes (outside subgraphs)
        lines.append("")
        for step in system_steps:
            if step.step_id in (SystemStep.END, SystemStep.ABORT):
                lines.append(self._format_step_node(step))

        # Add all links
        lines.append("")
        lines.append("    %% Connections")
        for step in process.process_steps:
            links = self._format_step_links(step, process)
            lines.extend(links)

        # Add link styles
        if self._link_styles:
            lines.append("")
            lines.append("    %% Link styles")
            lines.extend(self._link_styles)

        # Add node styles
        lines.append("")
        lines.append("    %% Styling")
        lines.extend(self._generate_styles(process))

        # Add notes section if enabled
        if self.include_notes:
            notes = self._collect_notes(process)
            if notes:
                lines.append("")
                lines.append("    %% Notes")
                for note in notes:
                    lines.append(f"    %% {note}")

        return "\n".join(lines)

    def _reset(self) -> None:
        """Reset internal state for a new generation."""
        self._link_counter = 0
        self._link_styles = []

    def _format_step_node(self, step: Step) -> str:
        """Format a step as a Mermaid node definition.

        Args:
            step: The step to format.

        Returns:
            Mermaid node definition string.
        """
        node_id = step.stripped_id

        # System START - stadium/pill shape
        if step.step_id == SystemStep.START:
            return f"    {node_id}([Start])"

        # System END - stadium/pill shape with double border effect
        if step.step_id == SystemStep.END:
            return f"    {node_id}([End])"

        # System ABORT - stadium/pill shape
        if step.step_id == SystemStep.ABORT:
            return f"    {node_id}([Abort])"

        label = _format_step_label(step, include_metadata=self.include_metadata)

        # Condition - diamond shape
        if step.is_condition:
            # Use rhombus shape for decisions
            return f'    {node_id}{{"{label}"}}'

        # Regular step - rounded rectangle
        return f'    {node_id}("{label}")'

    def _format_step_links(self, step: Step, process: Process) -> list[str]:
        """Format step transition links.

        Args:
            step: The step to process.
            process: The full process for step lookup.

        Returns:
            List of link definitions.
        """
        links: list[str] = []
        source_id = step.stripped_id

        # Unconditional next step
        if step.next_step:
            target_id = self._get_target_id(step.next_step)
            if target_id:
                links.append(f"    {source_id} --> {target_id}")
                self._link_counter += 1

        # Conditional Yes path
        if step.next_step_yes:
            target_id = self._get_target_id(step.next_step_yes)
            if target_id:
                label = "Yes"
                if step.yes_when:
                    # Truncate long conditions
                    condition = step.yes_when[:30] + "..." if len(step.yes_when) > 30 else step.yes_when
                    label = _sanitize_label(condition)
                links.append(f'    {source_id} -->|"{label}"| {target_id}')
                self._link_styles.append(
                    f"    linkStyle {self._link_counter} stroke:{COLORS['yes_path']},stroke-width:2px"
                )
                self._link_counter += 1

        # Conditional No path
        if step.next_step_no:
            target_id = self._get_target_id(step.next_step_no)
            if target_id:
                label = "No"
                if step.no_when:
                    condition = step.no_when[:30] + "..." if len(step.no_when) > 30 else step.no_when
                    label = _sanitize_label(condition)
                links.append(f'    {source_id} -->|"{label}"| {target_id}')
                self._link_styles.append(
                    f"    linkStyle {self._link_counter} stroke:{COLORS['no_path']},stroke-width:2px"
                )
                self._link_counter += 1

        return links

    def _get_target_id(self, step_id: str) -> str:
        """Get the target step ID for a link.

        Args:
            step_id: The step ID to resolve.

        Returns:
            The target ID with prefix stripped.
        """
        for prefix in StepPrefix:
            if step_id.startswith(prefix):
                return step_id[len(prefix):]
        return step_id

    def _generate_styles(self, process: Process) -> list[str]:
        """Generate Mermaid style definitions.

        Args:
            process: The process being rendered.

        Returns:
            List of style definition lines.
        """
        styles: list[str] = []

        # Collect node IDs by type
        start_nodes: list[str] = []
        end_nodes: list[str] = []
        condition_nodes: list[str] = []
        system_nodes: list[str] = []
        regular_nodes: list[str] = []

        for step in process.process_steps:
            node_id = step.stripped_id
            if step.step_id == SystemStep.START:
                start_nodes.append(node_id)
            elif step.step_id in (SystemStep.END, SystemStep.ABORT):
                end_nodes.append(node_id)
            elif step.is_condition:
                condition_nodes.append(node_id)
            elif step.is_system_step:
                system_nodes.append(node_id)
            elif step.manual_system and step.manual_system.upper() != "MANUAL":
                system_nodes.append(node_id)
            else:
                regular_nodes.append(node_id)

        # Define style classes
        styles.append(f"    classDef startEnd fill:#e8f4fc,stroke:#333,stroke-width:2px,color:#333")
        styles.append(f"    classDef condition fill:#fff,stroke:#333,stroke-width:1px,color:#333")
        styles.append(f"    classDef systemStep fill:{COLORS['system_step_bg']},stroke:#333,stroke-width:1px,color:#333")
        styles.append(f"    classDef default fill:#fff,stroke:#333,stroke-width:1px,color:#333")

        # Apply styles to nodes
        if start_nodes:
            styles.append(f"    class {','.join(start_nodes)} startEnd")
        if end_nodes:
            styles.append(f"    class {','.join(end_nodes)} startEnd")
        if condition_nodes:
            styles.append(f"    class {','.join(condition_nodes)} condition")
        if system_nodes:
            styles.append(f"    class {','.join(system_nodes)} systemStep")

        # Style subgraphs (swimlanes)
        for role in process.process_roles:
            styles.append(
                f"    style {role.role_id} fill:{COLORS['swimlane_bg']},stroke:{COLORS['header_bg']},stroke-width:2px"
            )

        return styles

    def _collect_notes(self, process: Process) -> list[str]:
        """Collect all notes from the process for the notes section.

        Args:
            process: The process to collect notes from.

        Returns:
            List of note strings.
        """
        notes: list[str] = []
        note_counter = 1

        for step in process.process_steps:
            if step.step_notes:
                for note in step.step_notes:
                    notes.append(f"N{note_counter} - {step.step_title}: {note}")
                    note_counter += 1

        return notes


def generate_mermaid_from_process(process: Process) -> str:
    """Generate a Mermaid flowchart from a Process object.

    This is a convenience function that creates a MermaidGenerator instance.

    Args:
        process: The process to convert.

    Returns:
        Mermaid flowchart definition string.
    """
    generator = MermaidGenerator()
    return generator.generate(process)


def save_mermaid_chart(mermaid_chart: str, output_path: Path | str) -> None:
    """Save a Mermaid chart to a file.

    Args:
        mermaid_chart: The Mermaid chart definition.
        output_path: Path to save the file.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(mermaid_chart)
    logger.info("Saved Mermaid chart to: %s", output_path)
