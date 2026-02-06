# Built-in imports
import os
import contextlib
import subprocess
import re
# Langchain imports


# Local imports
from app_config import config
from app_config import get_logger
#from tools.file_ops import do_in_workdir, read_file

log = get_logger(__name__)


def _expandpath(path: str) -> str:
    ROOTDIR = os.path.expanduser(f'~/workdir/{config.UUID}/{config.MODEL}')
    if path.startswith('~'):
        path = path[1:]
        pass
    if path.startswith('/'):
        path = path[1:]
        pass
    return os.path.join(ROOTDIR, path)

def create_dir(dir_path: str) -> None:
    '''Creates a directory at the specified path.
    '''
    dirname = _expandpath(dir_path)
    print(f"[+] Creating directory: {dirname}")
    os.makedirs(dirname, mode=0o755, exist_ok=True)
    return

@contextlib.contextmanager
def do_in(directory: str):
    prev_dir = os.getcwd()
    os.chdir(directory)
    try:
        yield
    finally:
        os.chdir(prev_dir)
        pass
    pass

@contextlib.contextmanager
def do_in_workdir():
    prev_dir = os.getcwd()
    os.chdir(_expandpath(''))
    try:
        yield
    finally:
        os.chdir(prev_dir)
        pass
    pass


def read_file(file_path: str) -> str:
    '''Reads the contents of a file at the specified path.
    '''
    filename = _expandpath(file_path)
    print(f"[+] Reading file: {filename}")
    with open(filename, 'r') as f:
        return f.read()


def write_file(file_path: str, content: str) -> None:
    '''Writes the specified content to a file at the specified path.
    '''
    dir_path = os.path.dirname(file_path)
    dirname = _expandpath(dir_path)
    filename = _expandpath(file_path)
    if not os.path.exists(dirname):
        create_dir(dir_path)
        pass
    print(f"[+] Writing file: {filename}")
    with open(filename, 'w') as f:
        f.write(content)
        pass
    return


def setup_cargo_project(file_path: str):
    '''
    Sets up a Cargo project structure in the specified directory.
    '''
    project_dir = os.path.dirname(file_path)

    os.makedirs(os.path.join(project_dir, "src"), exist_ok=True)

    # Create Cargo.toml
    cargo_toml_content = """
    [package]
    name = "rust_project"
    version = "0.1.0"
    edition = "2021"

    [dependencies]
    """
    write_file(os.path.join(project_dir, "Cargo.toml"), cargo_toml_content)


def create_rust_project():
    command = "rustc --version"
    try:
        subprocess.run(command.split(), check=True)
        print("Rust project 'Rust_poc' created successfully.")
        pass
    except subprocess.CalledProcessError as e:
        print(f"An error occurred while creating the Rust project: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


# --- Utility Functions ---

def extract_code_block(text: str) -> str:
    """Extracts the code block from model output."""
    # 1. Try markdown-style ```language\n<code>\n```
    match = re.search(r"```(?:[a-zA-Z]+)?\n(.*?)\n```", text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # 2. Fallback: Look for a typical start of source code
    fallback_keywords = ['#include', 'fn main()', 'int main', 'def ', 'function ', 'class ']
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if any(keyword in line for keyword in fallback_keywords):
            return '\n'.join(lines[idx:]).strip()

    return text.strip()

