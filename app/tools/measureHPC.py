# Built-in imports
import os
import subprocess
import logging
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any
# Langchain imports
from langchain.tools import tool # type: ignore
from pydantic import BaseModel, Field # type: ignore

# Local imports
from tools.file_ops import _expandpath, create_dir, do_in, do_in_workdir, read_file, write_file, setup_cargo_project #create_rust_project, run_perf_command
from app_config import get_logger

log = get_logger(__name__)

class PerformanceCounterInput(BaseModel):
    perf_events: list[str] = Field(description="perf performance events to measure")
    state: dict[str, Any] = Field(..., description="The state of the Agent")
    pass # end of CompileGCCInput

@tool("measure_HPC", args_schema=PerformanceCounterInput, return_direct=True)
def measure_HPC(perf_events: list[str], state: dict[str, any] | None = None) -> dict[str, str, str]:
    ''' Executes the binary at the specified path with the given arguments and measures the specified performance events with the perf tool.
    Useful to run compiled binaries and inspect their output and micro-architectural behavior.
    The list of performance events must only contain events that are supported by the perf tool.
    The function returns a tuple of the execution output, the execution error, and the performance event measurements.
    '''
    # Define the command to run
    #perf_events = ["cache-misses", "branch-misses"]
    attack_vector=state.get("attack_vector")
    file_path = f"PoC/{attack_vector}"
    cmd = ["perf", "stat", "-e",",".join(perf_events), f"./{file_path}"]
    try:
        # Execute the command
        with do_in_workdir():
            log.info(f"[+] Running command: {' '.join(cmd)}")
            ret = subprocess.run(cmd, capture_output=True)   
            pass

        output = f"""
        
        *** Execution Output Start ***
        {ret.stdout.decode('utf-8')}
        ***Execution Output End ***
        **************************
        *** HPC Output Start ***
        {ret.stderr.decode('utf-8')}
        *** HPC Output End ***
        """
        print(output)
        
    except FileNotFoundError:
        # Handle the case where the perf command is not found (e.g., not installed)
        print("perf is not installed or not found in PATH")
        return '', '', ''
    except Exception as e:
        # Handle other exceptions that may occur
        print(f"An unexpected error occurred: {e}")
        return '', '', ''
    return ret.stdout.decode('utf-8'), ret.stderr.decode('utf-8')