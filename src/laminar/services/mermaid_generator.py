"""Mermaid diagram generation service."""

import logging
from pathlib import Path

from laminar.core.constants import LinkStyle, MermaidShape, StepPrefix, SystemStep
from laminar.core.models import Process, Step

logger = logging.getLogger(__name__)


def _sanitize_label(label: str) -> str:
    """Sanitize a label for Mermaid syntax.

    Args:
        label: The label to sanitize.

    Returns:
        Sanitized label string.
    """
    return label.replace("*", "").replace('"', "'")


def _format_step_label(step: Step) -> str:
    """Format a step label with additional metadata.

    Args:
        step: The step to format.

    Returns:
        Formatted label string with HTML-like markup.
    """
    label = f"**{_sanitize_label(step.step_title)}**"

    if step.manual_system:
        if step.manual_system.upper() == "MANUAL":
            label += f"<br/>*{_sanitize_label(step.manual_system)}*"
        else:
            label += f"<br/>SYSTEM *{_sanitize_label(step.manual_system)}*"

    if step.user_credentials:
        label += f"<br/>LOGIN *{_sanitize_label(step.user_credentials)}*"

    if step.password_info:
        label += f"<br/>PASSWORD *{_sanitize_label(step.password_info)}*"

    if step.program_location:
        label += f"<br/>LOCATION *{_sanitize_label(step.program_location)}*"

    return label


class MermaidGenerator:
    """Generates Mermaid flowchart diagrams from Process objects."""

    def __init__(self) -> None:
        """Initialize the Mermaid generator."""
        self._link_counter = 0
        self._link_styles: list[str] = []
        self._note_ids: list[str] = []

    def generate(self, process: Process) -> str:
        """Generate a Mermaid flowchart from a Process object.

        Args:
            process: The process to convert.

        Returns:
            Mermaid flowchart definition string.
        """
        self._reset()

        lines: list[str] = ["flowchart TD"]
        role_subgraphs: dict[str, list[str]] = {}
        links: list[str] = []
        descriptions: list[str] = []

        # Initialize subgraphs for each role
        for role in process.process_roles:
            role_subgraphs[role.role_id] = []

        # Process each step
        for step in process.process_steps:
            step_line = self._format_step_node(step)
            desc_lines, desc_links = self._format_step_descriptions(step)
            step_links = self._format_step_links(step, process)

            # Add to appropriate subgraph or main graph
            if step.step_role and step.step_role in role_subgraphs:
                role_subgraphs[step.step_role].append(step_line)
                role_subgraphs[step.step_role].extend(desc_lines)
            else:
                lines.append(step_line)
                descriptions.extend(desc_lines)

            links.extend(desc_links)
            links.extend(step_links)

        # Add subgraphs
        for role in process.process_roles:
            if role.role_id in role_subgraphs:
                lines.append(f"subgraph {role.role_id} [{role.role_title}]")
                lines.extend(role_subgraphs[role.role_id])
                lines.append("end")

        # Add descriptions and links
        lines.extend(descriptions)
        lines.extend(links)

        # Add link styles
        lines.extend(self._link_styles)

        # Add note styling
        lines.append("classDef noteClass fill:#fff,stroke:#333,color:#aaaaaa;")
        for note_id in self._note_ids:
            lines.append(f"class {note_id} noteClass;")

        return "\n".join(lines)

    def _reset(self) -> None:
        """Reset internal state for a new generation."""
        self._link_counter = 0
        self._link_styles = []
        self._note_ids = []

    def _format_step_node(self, step: Step) -> str:
        """Format a step as a Mermaid node definition.

        Args:
            step: The step to format.

        Returns:
            Mermaid node definition string.
        """
        if step.step_id == SystemStep.START:
            return f"    START@{{ shape: {MermaidShape.CIRCLE}, label: \"START\" }}"

        if step.step_id == SystemStep.END:
            return f"    END@{{ shape: {MermaidShape.DOUBLE_CIRCLE}, label: \"END\" }}"

        if step.step_id == SystemStep.ABORT:
            return f"    ABORT@{{ shape: {MermaidShape.DOUBLE_CIRCLE}, label: \"ABORT\" }}"

        if step.is_condition:
            label = _format_step_label(step)
            return (
                f"    {step.stripped_id}@{{ shape: {MermaidShape.HEXAGON}, "
                f'label: "{label}" }}'
            )

        label = _format_step_label(step)
        return f"    {step.step_id}({label})"

    def _format_step_descriptions(
        self, step: Step
    ) -> tuple[list[str], list[str]]:
        """Format step descriptions and notes as Mermaid nodes.

        Args:
            step: The step to process.

        Returns:
            Tuple of (node definitions, link definitions).
        """
        nodes: list[str] = []
        links: list[str] = []

        if not (step.step_description or step.step_notes):
            return nodes, links

        stripped_id = step.stripped_id
        desc_id = f"{stripped_id}_desc"
        desc_label = _sanitize_label(step.step_description or "Notes")

        nodes.append(
            f'{desc_id}@{{shape: {MermaidShape.BRACES}, label: "{desc_label}"}}'
        )
        links.append(f"{stripped_id} -.-o {desc_id}")
        self._link_styles.append(
            f"linkStyle {self._link_counter} {LinkStyle.NOTE_LINK}"
        )
        self._link_counter += 1

        # Add individual notes
        if step.step_notes:
            for idx, note in enumerate(step.step_notes):
                note_id = f"{stripped_id}_note_{idx}"
                note_label = _sanitize_label(note)
                nodes.append(
                    f'{note_id}@{{shape: {MermaidShape.COMMENT}, label: "{note_label}"}}'
                )
                links.append(f"{desc_id} -.-o {note_id}")
                self._link_styles.append(
                    f"linkStyle {self._link_counter} {LinkStyle.NOTE_LINK}"
                )
                self._link_counter += 1
                self._note_ids.append(note_id)

        return nodes, links

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

        if step.next_step:
            target = self._get_target_id(step.next_step, process)
            if target:
                links.append(f"{source_id} --> {target}")
                self._link_counter += 1

        if step.next_step_yes:
            target = self._get_target_id(step.next_step_yes, process)
            if target:
                condition = step.yes_when or step.additional_attributes.get(
                    "yes_when", "yes"
                )
                links.append(f"{source_id} -- {condition} --> {target}")
                self._link_styles.append(
                    f"linkStyle {self._link_counter} {LinkStyle.YES_PATH}"
                )
                self._link_counter += 1

        if step.next_step_no:
            target = self._get_target_id(step.next_step_no, process)
            if target:
                condition = step.no_when or step.additional_attributes.get(
                    "no_when", "no"
                )
                links.append(f"{source_id} -- {condition} --> {target}")
                self._link_styles.append(
                    f"linkStyle {self._link_counter} {LinkStyle.NO_PATH}"
                )
                self._link_counter += 1

        return links

    def _get_target_id(self, step_id: str, process: Process) -> str | None:
        """Get the target step ID for a link.

        Args:
            step_id: The step ID to resolve.
            process: The process for step lookup.

        Returns:
            The target ID or None if not found.
        """
        # Strip prefix for the target
        for prefix in StepPrefix:
            if step_id.startswith(prefix):
                return step_id[len(prefix) :]

        # Verify step exists
        target_step = process.get_step_by_id(step_id)
        return step_id if target_step else None


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
