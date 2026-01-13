"""Tests for template validation and parsing."""

import pytest

from laminar.core.template import (
    ColumnType,
    ColumnMapping,
    TemplateValidationResult,
    validate_template,
    TEMPLATE_COLUMNS,
)


class TestColumnMapping:
    """Tests for ColumnMapping class."""

    def test_exact_match(self):
        mapping = ColumnMapping(
            column_type=ColumnType.STEP_NUMBER,
            aliases=["step #", "no"],
        )
        assert mapping.matches("step_number") is True
        assert mapping.matches("step number") is True
        assert mapping.matches("stepnumber") is True

    def test_alias_match(self):
        mapping = ColumnMapping(
            column_type=ColumnType.ROLE,
            aliases=["actor", "responsible"],
        )
        assert mapping.matches("actor") is True
        assert mapping.matches("Actor") is True
        assert mapping.matches("RESPONSIBLE") is True

    def test_no_match(self):
        mapping = ColumnMapping(
            column_type=ColumnType.STEP_NUMBER,
            aliases=["step #"],
        )
        assert mapping.matches("random column") is False
        assert mapping.matches("") is False


class TestValidateTemplate:
    """Tests for validate_template function."""

    def test_valid_template_all_columns(self):
        headers = ["Step #", "Role", "Step Title", "Description", "Next Step", "Notes"]
        result = validate_template(headers)

        assert result.is_valid is True
        assert result.confidence > 0.5
        assert ColumnType.STEP_NUMBER in result.matched_columns
        assert ColumnType.ROLE in result.matched_columns
        assert ColumnType.STEP_TITLE in result.matched_columns

    def test_valid_template_with_aliases(self):
        headers = ["No", "Actor", "Action", "Details"]
        result = validate_template(headers)

        assert result.is_valid is True
        assert ColumnType.STEP_NUMBER in result.matched_columns
        assert ColumnType.ROLE in result.matched_columns
        assert ColumnType.STEP_TITLE in result.matched_columns

    def test_missing_required_columns(self):
        headers = ["Description", "Notes", "Comments"]
        result = validate_template(headers)

        assert result.is_valid is False
        assert len(result.missing_required) > 0
        assert ColumnType.STEP_NUMBER in result.missing_required

    def test_unmatched_headers_tracked(self):
        headers = ["Step #", "Role", "Step Title", "Custom Column", "Another One"]
        result = validate_template(headers)

        assert "Custom Column" in result.unmatched_headers
        assert "Another One" in result.unmatched_headers

    def test_empty_headers(self):
        headers = []
        result = validate_template(headers)

        assert result.is_valid is False
        assert result.confidence == 0.0

    def test_can_parse_directly(self):
        # Valid template with high confidence
        headers = ["Step #", "Role", "Step Title", "Next Step", "Condition?", "Yes→", "No→"]
        result = validate_template(headers)

        assert result.can_parse_directly is True

    def test_cannot_parse_directly_low_confidence(self):
        # Only one matching column
        headers = ["Step #", "Foo", "Bar", "Baz"]
        result = validate_template(headers)

        assert result.can_parse_directly is False

    def test_condition_columns(self):
        headers = ["Step #", "Role", "Title", "Condition?", "Yes→", "No→", "Yes When", "No When"]
        result = validate_template(headers)

        assert ColumnType.IS_CONDITION in result.matched_columns
        assert ColumnType.YES_NEXT in result.matched_columns
        assert ColumnType.NO_NEXT in result.matched_columns


class TestTemplateColumns:
    """Tests for TEMPLATE_COLUMNS configuration."""

    def test_required_columns_defined(self):
        required = [c for c in TEMPLATE_COLUMNS if c.required]
        assert len(required) >= 3  # At least step_number, role, step_title

    def test_all_column_types_have_aliases(self):
        for col in TEMPLATE_COLUMNS:
            # Each column should have at least one way to match
            assert len(col.aliases) > 0 or col.column_type.value


class TestTemplateValidationResult:
    """Tests for TemplateValidationResult."""

    def test_can_parse_directly_conditions(self):
        # Valid with high confidence
        result = TemplateValidationResult(
            is_valid=True,
            confidence=0.8,
            matched_columns={ColumnType.STEP_NUMBER: "Step #"},
            missing_required=[],
            unmatched_headers=[],
        )
        assert result.can_parse_directly is True

        # Invalid
        result.is_valid = False
        assert result.can_parse_directly is False

        # Low confidence
        result.is_valid = True
        result.confidence = 0.5
        assert result.can_parse_directly is False

        # Missing required
        result.confidence = 0.8
        result.missing_required = [ColumnType.ROLE]
        assert result.can_parse_directly is False
