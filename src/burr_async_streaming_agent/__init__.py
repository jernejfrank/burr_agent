from pathlib import Path

ROOT_DIRECTORY = Path(__file__).parent
with open(ROOT_DIRECTORY / "VERSION") as f:
    __version__ = f.read()
