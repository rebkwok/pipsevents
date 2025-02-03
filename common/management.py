from pathlib import Path

    
def write_command_name(command_instance, filepath):
    command_instance.stdout.write(f"Running {Path(filepath).stem}")
