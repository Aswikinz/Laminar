"""Tests for Mermaid diagram generation."""

import json
from pathlib import Path

import pytest

from laminar.core.models import Process, Role, Step, parse_json_to_process
from laminar.services.mermaid_generator import (
    MermaidGenerator,
    generate_mermaid_from_process,
    _sanitize_label,
    _format_step_label,
)


class TestSanitizeLabel:
    """Tests for label sanitization."""

    def test_removes_asterisks(self):
        assert _sanitize_label("**bold**") == "bold"

    def test_removes_hash(self):
        assert _sanitize_label("Step #1") == "Step 1"

    def test_replaces_ampersand(self):
        assert _sanitize_label("A & B") == "A and B"

    def test_removes_angle_brackets(self):
        assert _sanitize_label("<script>") == "script"

    def test_replaces_quotes(self):
        assert _sanitize_label('Say "hello"') == "Say 'hello'"


class TestFormatStepLabel:
    """Tests for step label formatting."""

    def test_basic_label(self):
        step = Step(step_id="s1", step_title="My Step")
        label = _format_step_label(step, include_metadata=False)
        assert label == "My Step"

    def test_label_with_manual_system(self):
        step = Step(step_id="s1", step_title="My Step", manual_system="MANUAL")
        label = _format_step_label(step, include_metadata=True)
        assert "My Step" in label
        assert "MANUAL" in label

    def test_label_with_program_location(self):
        step = Step(step_id="s1", step_title="My Step", program_location="SAP T-CODE")
        label = _format_step_label(step, include_metadata=True)
        assert "SAP T-CODE" in label


class TestMermaidGenerator:
    """Tests for MermaidGenerator class."""

    def test_basic_generation(self):
        process = Process(
            process_id="p1",
            process_name="Test Process",
            process_roles=[Role(role_id="r1", role_title="Actor")],
            process_steps=[
                Step(step_id="SYSTEM::START", step_title="Start", next_step="s1"),
                Step(step_id="s1", step_role="r1", step_title="Do Work", next_step="SYSTEM::END"),
                Step(step_id="SYSTEM::END", step_title="End"),
            ],
        )
        generator = MermaidGenerator()
        result = generator.generate(process)

        assert "flowchart TD" in result
        assert "START([Start])" in result
        assert "END([End])" in result
        assert 'subgraph r1[Actor]' in result

    def test_condition_shape(self):
        process = Process(
            process_id="p1",
            process_name="Test",
            process_roles=[],
            process_steps=[
                Step(
                    step_id="CONDITION::check",
                    step_title="Is Valid?",
                    next_step_yes="yes_step",
                    next_step_no="no_step",
                ),
            ],
        )
        generator = MermaidGenerator()
        result = generator.generate(process)

        # Should use diamond shape for conditions
        assert 'check{"Is Valid?"}' in result

    def test_conditional_paths_colored(self):
        process = Process(
            process_id="p1",
            process_name="Test",
            process_roles=[],
            process_steps=[
                Step(
                    step_id="CONDITION::check",
                    step_title="Check",
                    next_step_yes="s1",
                    next_step_no="s2",
                ),
                Step(step_id="s1", step_title="Yes Path"),
                Step(step_id="s2", step_title="No Path"),
            ],
        )
        generator = MermaidGenerator()
        result = generator.generate(process)

        # Should have green for yes, red for no
        assert "#2e7d32" in result  # Green
        assert "#c62828" in result  # Red

    def test_notes_collected(self):
        process = Process(
            process_id="p1",
            process_name="Test",
            process_roles=[],
            process_steps=[
                Step(step_id="s1", step_title="Step", step_notes=["Note 1", "Note 2"]),
            ],
        )
        generator = MermaidGenerator(include_notes=True)
        result = generator.generate(process)

        assert "Notes" in result or "Note 1" in result

    def test_convenience_function(self):
        process = Process(
            process_id="p1",
            process_name="Test",
            process_roles=[],
            process_steps=[
                Step(step_id="SYSTEM::START", step_title="Start"),
            ],
        )
        result = generate_mermaid_from_process(process)
        assert "flowchart TD" in result

    def test_sample_json_generation(self):
        """Test generating from actual sample.json."""
        sample_path = Path(__file__).parent.parent / "sample.json"
        if sample_path.exists():
            with open(sample_path) as f:
                data = json.load(f)
            process = parse_json_to_process(data)
            result = generate_mermaid_from_process(process)

            # Should have all subgraphs for roles
            assert "customer_support_chatbot" in result
            assert "customer_support_specialist" in result
            assert "Customer" in result

            # Should have start and end
            assert "START([Start])" in result
            assert "END([End])" in result

            # Should have styling
            assert "classDef" in result
