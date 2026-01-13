"""Domain models for business process representation."""

from dataclasses import dataclass, field
from typing import Any

from laminar.core.constants import StepPrefix


@dataclass(frozen=True, slots=True)
class Role:
    """Represents a role/actor in a business process.

    Attributes:
        role_id: Unique identifier for the role.
        role_title: Human-readable title for the role.
        role_notes: Optional notes about the role.
    """

    role_id: str
    role_title: str
    role_notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Step:
    """Represents a single step in a business process.

    Attributes:
        step_id: Unique identifier for the step.
        step_role: Role responsible for this step.
        step_title: Short title describing the step.
        step_description: Detailed description of the step.
        next_step: ID of the next step (unconditional flow).
        next_step_yes: ID of the next step when condition is true.
        next_step_no: ID of the next step when condition is false.
        step_notes: Notes associated with this step.
        manual_system: Whether step is manual or system-driven.
        user_credentials: User credentials information.
        password_info: Password information for test systems.
        users_name: Name of the user performing the step.
        program_location: Program ID, T-Code, or screen name.
        yes_when: Description of when the "yes" path is taken.
        no_when: Description of when the "no" path is taken.
        additional_attributes: Any extra attributes from JSON.
    """

    step_id: str
    step_role: str | None = None
    step_title: str = ""
    step_description: str | None = None
    next_step: str | None = None
    next_step_yes: str | None = None
    next_step_no: str | None = None
    step_notes: list[str] = field(default_factory=list)
    manual_system: str | None = None
    user_credentials: str | None = None
    password_info: str | None = None
    users_name: str | None = None
    program_location: str | None = None
    yes_when: str | None = None
    no_when: str | None = None
    additional_attributes: dict[str, Any] = field(default_factory=dict)

    @property
    def is_condition(self) -> bool:
        """Check if this step is a condition/decision point."""
        return self.step_id.startswith(StepPrefix.CONDITION)

    @property
    def is_system_step(self) -> bool:
        """Check if this step is a system step (START/END/ABORT)."""
        return self.step_id.startswith(StepPrefix.SYSTEM)

    @property
    def stripped_id(self) -> str:
        """Get the step ID without any prefix."""
        for prefix in StepPrefix:
            if self.step_id.startswith(prefix):
                return self.step_id[len(prefix) :]
        return self.step_id

    @property
    def has_conditional_flow(self) -> bool:
        """Check if this step has conditional branching."""
        return self.next_step_yes is not None or self.next_step_no is not None


@dataclass(slots=True)
class Process:
    """Represents a complete business process.

    Attributes:
        process_id: Unique identifier for the process.
        process_name: Human-readable name of the process.
        process_roles: List of roles involved in the process.
        process_steps: Ordered list of steps in the process.
    """

    process_id: str
    process_name: str
    process_roles: list[Role] = field(default_factory=list)
    process_steps: list[Step] = field(default_factory=list)

    def get_step_by_id(self, step_id: str) -> Step | None:
        """Find a step by its ID.

        Args:
            step_id: The step ID to search for.

        Returns:
            The Step if found, None otherwise.
        """
        # Strip prefix from search ID for comparison
        search_id = step_id
        for prefix in StepPrefix:
            if step_id.startswith(prefix):
                search_id = step_id[len(prefix) :]
                break

        for step in self.process_steps:
            if step.step_id == step_id or step.stripped_id == search_id:
                return step
        return None

    def get_role_by_id(self, role_id: str) -> Role | None:
        """Find a role by its ID.

        Args:
            role_id: The role ID to search for.

        Returns:
            The Role if found, None otherwise.
        """
        for role in self.process_roles:
            if role.role_id == role_id:
                return role
        return None


def parse_json_to_process(json_data: dict[str, Any]) -> Process:
    """Parse JSON data into a Process object.

    Args:
        json_data: Dictionary containing process definition.

    Returns:
        A Process object representing the business process.
    """
    roles = [
        Role(
            role_id=role.get("role_id", ""),
            role_title=role.get("role_title", ""),
            role_notes=role.get("role_notes", []),
        )
        for role in json_data.get("process_roles", [])
    ]

    steps = []
    for step_data in json_data.get("process_steps", []):
        # Extract known fields
        known_fields = {
            "step_id",
            "step_role",
            "step_title",
            "step_description",
            "next_step",
            "next_step_yes",
            "next_step_no",
            "step_notes",
            "manual_system",
            "user_role_code_user_id_user_name",
            "password_in_test_system",
            "users_name",
            "program_id_t_code_screen_name",
            "yes_when",
            "no_when",
        }

        # Collect additional attributes
        additional = {k: v for k, v in step_data.items() if k not in known_fields}

        step = Step(
            step_id=step_data.get("step_id", ""),
            step_role=step_data.get("step_role"),
            step_title=step_data.get("step_title", ""),
            step_description=step_data.get("step_description"),
            next_step=step_data.get("next_step"),
            next_step_yes=step_data.get("next_step_yes"),
            next_step_no=step_data.get("next_step_no"),
            step_notes=step_data.get("step_notes", []),
            manual_system=step_data.get("manual_system"),
            user_credentials=step_data.get("user_role_code_user_id_user_name"),
            password_info=step_data.get("password_in_test_system"),
            users_name=step_data.get("users_name"),
            program_location=step_data.get("program_id_t_code_screen_name"),
            yes_when=step_data.get("yes_when"),
            no_when=step_data.get("no_when"),
            additional_attributes=additional,
        )
        steps.append(step)

    return Process(
        process_id=json_data.get("process_id", ""),
        process_name=json_data.get("process_name", ""),
        process_roles=roles,
        process_steps=steps,
    )
