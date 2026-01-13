"""Tests for core modules."""

import json
from pathlib import Path

import pytest

from laminar.core.constants import StepPrefix, SystemStep, MermaidShape, EXCEL_EXTENSIONS
from laminar.core.models import Process, Role, Step, parse_json_to_process


class TestConstants:
    """Tests for constants module."""

    def test_step_prefix_values(self):
        assert StepPrefix.CONDITION == "CONDITION::"
        assert StepPrefix.SYSTEM == "SYSTEM::"

    def test_system_step_values(self):
        assert SystemStep.START == "SYSTEM::START"
        assert SystemStep.END == "SYSTEM::END"
        assert SystemStep.ABORT == "SYSTEM::ABORT"

    def test_excel_extensions(self):
        assert ".xlsx" in EXCEL_EXTENSIONS
        assert ".xlsm" in EXCEL_EXTENSIONS
        assert ".xls" in EXCEL_EXTENSIONS


class TestModels:
    """Tests for models module."""

    def test_role_creation(self):
        role = Role(role_id="test_role", role_title="Test Role")
        assert role.role_id == "test_role"
        assert role.role_title == "Test Role"
        assert role.role_notes == []

    def test_role_with_notes(self):
        role = Role(role_id="r1", role_title="Role 1", role_notes=["Note 1", "Note 2"])
        assert len(role.role_notes) == 2

    def test_step_creation(self):
        step = Step(step_id="step1", step_title="Test Step")
        assert step.step_id == "step1"
        assert step.step_title == "Test Step"
        assert step.is_condition is False
        assert step.is_system_step is False

    def test_step_is_condition(self):
        step = Step(step_id="CONDITION::check", step_title="Check Condition")
        assert step.is_condition is True
        assert step.stripped_id == "check"

    def test_step_is_system(self):
        step = Step(step_id="SYSTEM::START", step_title="Start")
        assert step.is_system_step is True
        assert step.stripped_id == "START"

    def test_step_has_conditional_flow(self):
        step1 = Step(step_id="s1", next_step_yes="s2", next_step_no="s3")
        step2 = Step(step_id="s2", next_step="s3")
        assert step1.has_conditional_flow is True
        assert step2.has_conditional_flow is False

    def test_process_creation(self):
        process = Process(
            process_id="p1",
            process_name="Test Process",
            process_roles=[Role(role_id="r1", role_title="Role 1")],
            process_steps=[Step(step_id="s1", step_title="Step 1")],
        )
        assert process.process_id == "p1"
        assert len(process.process_roles) == 1
        assert len(process.process_steps) == 1

    def test_process_get_step_by_id(self):
        step = Step(step_id="test_step", step_title="Test")
        process = Process(
            process_id="p1",
            process_name="Test",
            process_steps=[step],
        )
        found = process.get_step_by_id("test_step")
        assert found is not None
        assert found.step_id == "test_step"

    def test_process_get_role_by_id(self):
        role = Role(role_id="test_role", role_title="Test Role")
        process = Process(
            process_id="p1",
            process_name="Test",
            process_roles=[role],
        )
        found = process.get_role_by_id("test_role")
        assert found is not None
        assert found.role_id == "test_role"


class TestParseJson:
    """Tests for JSON parsing."""

    def test_parse_minimal_json(self):
        data = {
            "process_id": "p1",
            "process_name": "Test Process",
            "process_roles": [],
            "process_steps": [],
        }
        process = parse_json_to_process(data)
        assert process.process_id == "p1"
        assert process.process_name == "Test Process"

    def test_parse_with_roles(self):
        data = {
            "process_id": "p1",
            "process_name": "Test",
            "process_roles": [
                {"role_id": "r1", "role_title": "Role One"},
                {"role_id": "r2", "role_title": "Role Two"},
            ],
            "process_steps": [],
        }
        process = parse_json_to_process(data)
        assert len(process.process_roles) == 2

    def test_parse_with_steps(self):
        data = {
            "process_id": "p1",
            "process_name": "Test",
            "process_roles": [],
            "process_steps": [
                {
                    "step_id": "SYSTEM::START",
                    "step_title": "Start",
                    "next_step": "step1",
                },
                {
                    "step_id": "step1",
                    "step_role": "r1",
                    "step_title": "Do Something",
                    "next_step": "SYSTEM::END",
                },
                {
                    "step_id": "SYSTEM::END",
                    "step_title": "End",
                },
            ],
        }
        process = parse_json_to_process(data)
        assert len(process.process_steps) == 3

    def test_parse_sample_json(self):
        """Test parsing the actual sample.json file."""
        sample_path = Path(__file__).parent.parent / "sample.json"
        if sample_path.exists():
            with open(sample_path) as f:
                data = json.load(f)
            process = parse_json_to_process(data)
            assert process.process_id == "full_customer_support_process"
            assert len(process.process_roles) == 7
            assert len(process.process_steps) == 15
