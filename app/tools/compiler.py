# Built-in imports
import os
import subprocess
import logging
# Langchain imports
from langchain.tools import tool # type: ignore
from pydantic import BaseModel, Field # type: ignore
from typing import Dict, Any

# Local imports
from tools.file_ops import do_in, do_in_workdir, write_file
from app_config import get_logger

log = get_logger(__name__)

class CompileGCCInput(BaseModel):
    file_contents: str = Field(..., description="the contents of the file (source code) to compile")
    state: dict[str, Any] = Field(..., description="The state of the Agent")
    pass # end of CompileGCCInput


@tool("compile_C", args_schema=CompileGCCInput, return_direct=True)
def compile_C(file_contents: str, state: Dict[str, Any] | None = None) -> dict[str, str]:
    '''
    Compiles the file at the specified path with the given contents, compiler flags and linker flags.
    Useful to compile C source code files to a binary.

    Args:
        file_contents (str): The contents of the file (source code) to compile.
        state (dict): The state of the Agent which contains 'attack_vector' and 'target_file_extension'.
            state("attack_vector"): The attack vector name (e.g., "Spectre-v1").
            state("target_file_extension"): The expected file extension (e.g., "c", "rs").

    Returns:
        dict[str, str]: A dictionary containing the compiler output and error messages.
    '''

    attack_vector=state.get('attack_vector','Spectre-v1')
    target_file_extension=state.get('target_file_extension','c')
    file_path = f"PoC/{attack_vector}.{target_file_extension}"
    write_file(file_path, file_contents)
    folder_path=os.path.dirname(file_path)

    # For GPT
    # cmd = ["gcc", *cflags, file_path, *ldflags]

    # For Llama
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    output_file = os.path.join(folder_path, base_name)
    cmd = ["gcc", "-o", output_file, file_path]

    with do_in_workdir():
        log.info(f"[+] Running command: {' '.join(cmd)}")
        file_path = os.path.join(os.getcwd(), folder_path)
        log.info(f"File path: {folder_path}") 
        ret = subprocess.run(cmd, capture_output=True)
        pass

    output = f"""
    *** Compiler Output Start ***
    {ret.stdout.decode('utf-8')}
    ***Compiler Output End ***
    **************************
    *** Compiler Error Start ***
    {ret.stderr.decode('utf-8')}
    *** Compiler Error End ***
    """
    print(output)
    return ret.stdout.decode('utf-8', errors='replace'), ret.stderr.decode('utf-8', errors='replace')

@tool("compile_CPP", args_schema=CompileGCCInput, return_direct=True)
def compile_CPP(file_contents: str, state: Dict[str, Any] | None = None) -> dict[str, str]:
    '''
    Compiles the file at the specified path with the given contents, compiler flags and linker flags.
    Useful to compile C++ source code files to a binary.

    Args:
        file_contents (str): The contents of the file (source code) to compile.
        state (dict): The state of the Agent which contains 'attack_vector' and 'target_file_extension'.
            state("attack_vector"): The attack vector name (e.g., "Spectre-v1").
            state("target_file_extension"): The expected file extension (e.g., "c", "rs").

    Returns:
        dict[str, str]: A dictionary containing the compiler output and error messages.
    '''
    
    attack_vector=state.get('attack_vector','Spectre-v1')
    target_file_extension=state.get('target_file_extension','c')
    file_path = f"PoC/{attack_vector}.{target_file_extension}"
    write_file(file_path, file_contents)
    folder_path=os.path.dirname(file_path)

    # For GPT
    # cmd = ["gcc", *cflags, file_path, *ldflags]

    # For Llama
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    output_file = os.path.join(folder_path, base_name)
    cmd = ["g++", "-std=gnu++17","-o", output_file, file_path]

    with do_in_workdir():
        log.info(f"[+] Running command: {' '.join(cmd)}")
        file_path = os.path.join(os.getcwd(), folder_path)
        log.info(f"File path: {folder_path}") 
        ret = subprocess.run(cmd, capture_output=True)
        pass

    output = f"""
    *** Compiler Output Start ***
    {ret.stdout.decode('utf-8')}
    ***Compiler Output End ***
    **************************
    *** Compiler Error Start ***
    {ret.stderr.decode('utf-8')}
    *** Compiler Error End ***
    """
    print(output)
    return ret.stdout.decode('utf-8', errors='replace'), ret.stderr.decode('utf-8', errors='replace')



class CompileRustInput(BaseModel):
    file_path: str = Field(description="the path of the file to compile")
    file_contents: str = Field(description="the contents of the file to compile")
    flags: list[str] = Field(description="compiler flags to use")
    pass # end of CompileRustInput

@tool("compile_rust", args_schema=CompileRustInput, return_direct=True)
def compile_rust(file_path: str, file_contents: str, flags: list[str]) -> dict[str, str]:
    '''
    Compiles the file at the specified path with the given contents and compiler flags.
    Useful to compile Rust source code files to a binary.
    Compiler flags are used to specify options to the compiler.
    E.g., "-o <outputfile>" specifies the name of the binary output file.
    The function returns a tuple of the compiler output and the compiler error.
    rustc -C target-cpu=native file_name.rs
    '''
    write_file(file_path, file_contents)

    # Create cargo project
    cmd1 = ["cargo", "new", "PoC/rust_cargo"]
    cmd2 = ["mkdir", "PoC/rust_cargo/src/bin"]
    # replace src/main.rs with the spectre code
    cmd3 = ["cp",file_path,"PoC/rust_cargo/src/bin/"]
    # build and compile
    cmd4 = ["cargo","build"]
    binary_path="PoC/rust_cargo/target/debug/*"
    # update Cargo.toml
    cargo_toml_content = """
    [package]
    name = "main"
    version = "0.1.0"
    edition = "2021"
    
    [profile.dev]
    overflow-checks = false
    opt-level = 1

    [dependencies]
    rand = "0.8"

    # [[bin]]
    # name = "Cache-occupancy-side-channel"
    # path = "src/bin/Cache-occupancy-side-channel.rs"

    # [[bin]]
    # name = "victim-code"
    # path = "src/bin/victim-code.rs"

    """

    try:
        with do_in_workdir():
            log.info(f"[+] Running command: {' '.join(cmd1)}")
            subprocess.run(cmd1, capture_output=True)   # Creating cargo project inside PoC
            log.info(f"[+] Running command: {' '.join(cmd2)}")
            subprocess.run(cmd2, capture_output=True)   # Creating src/bin directory
            log.info(f"[+] Running command: {' '.join(cmd3)}")
            subprocess.run(cmd3, capture_output=True)   # Copy source code to the src directory
            write_file("PoC/rust_cargo/Cargo.toml", cargo_toml_content) # Update Cargo.toml file
            log.info(f"[+] Running command: {' '.join(cmd4)}")
            with do_in("PoC/rust_cargo"):
                ret = subprocess.run(cmd4, capture_output=True)  # Build cargo
            subprocess.run(f"cp {binary_path} PoC/", shell=True)
            pass

        output = f"""
      
        *** Compiler Output Start ***
        {ret.stdout.decode('utf-8')}
        ***Compiler Output End ***
        **************************
        *** Compiler Error Start ***
        {ret.stderr.decode('utf-8')}
        *** Compiler Error End ***
        """
        print(output)
        
        
    except FileNotFoundError:
        # Handle the case where the perf command is not found (e.g., not installed)
        print("Rust is not installed or not found in PATH")
        return '', '', ''
    except Exception as e:
        # Handle other exceptions that may occur
        print(f"An unexpected error occurred: {e}")
        return '', '', ''
    return ret.stdout.decode('utf-8'), ret.stderr.decode('utf-8')
