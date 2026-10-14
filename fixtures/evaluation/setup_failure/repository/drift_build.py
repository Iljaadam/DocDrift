"""Deliberate missing-prerequisite backend; never execute on the controller."""

from pathlib import Path


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    required = Path(__file__).parent / "REQUIRED_BUILD_INPUT.json"
    if not required.is_file():
        raise FileNotFoundError("Missing declared prerequisite: REQUIRED_BUILD_INPUT.json")
    raise RuntimeError("This classifier fixture does not implement a successful wheel build")
