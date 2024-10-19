class Process:
    def __init__(self, process_id, process_name, process_roles, process_steps):
        self.process_id = process_id
        self.process_name = process_name
        self.process_roles = process_roles
        self.process_steps = process_steps

class Role:
    def __init__(self, role_id, role_title, role_notes=None):
        self.role_id = role_id
        self.role_title = role_title
        self.role_notes = role_notes or []

class Step:
    def __init__(self, step_id, step_role=None, step_title="", step_description=None, next_step=None, next_step_yes=None, next_step_no=None, step_notes=None, manual_system=None, user_role_code_user_id_user_name=None, password_in_test_system=None, users_name=None, program_id_t_code_screen_name=None, **kwargs):
        self.step_id = step_id
        self.step_role = step_role
        self.step_title = step_title
        self.step_description = step_description
        self.next_step = next_step
        self.next_step_yes = next_step_yes
        self.next_step_no = next_step_no
        self.step_notes = step_notes or []
        self.manual_system = manual_system
        self.user_role_code_user_id_user_name = user_role_code_user_id_user_name
        self.password_in_test_system = password_in_test_system
        self.users_name = users_name
        self.program_id_t_code_screen_name = program_id_t_code_screen_name
        # Store any additional attributes
        self.additional_attributes = kwargs

def parse_json_to_process(json_data):
    process_id = json_data.get("process_id")
    process_name = json_data.get("process_name")
    process_roles = [Role(**role) for role in json_data.get("process_roles", [])]
    process_steps = [Step(**step) for step in json_data.get("process_steps", [])]
    return Process(process_id, process_name, process_roles, process_steps)