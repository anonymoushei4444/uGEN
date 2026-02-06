# Built-in imports
import subprocess
import os
from concurrent.futures import ThreadPoolExecutor
import stat
# Langchain imports
from langchain.tools import tool # type: ignore
from pydantic import BaseModel, Field # type: ignore

# Local imports
from app_config import get_logger
from tools.file_ops import do_in_workdir, read_file

log = get_logger(__name__)



class ExecuteBinaries(BaseModel):
    file_path: str = Field(default="PoC",description="the path of the file to execute")
    cpu_core: int = Field(default=2, description="the cpu core in which the file will be executed")
    pass # end of ExecuteBinary
    
def execute_binary(file_path: str, cpu_core: int) -> dict[str, str]:
    ''' Executes the binary of the PoC at the specified path. The function returns a tuple of the execution output, 
    the execution error.
    '''
    # cpu_core=1
    # Define the command to run
    cmd=["taskset", "-c", str(cpu_core), file_path]
    log.info(f"File path 2nd:{os.path.dirname(file_path)}")
    # Execute the command
    with do_in_workdir():
        file_path = os.path.join(os.getcwd(), file_path)
        log.info(f"File path: {file_path}")
        ret = subprocess.run(cmd, capture_output=True)
        pass

    stdout, stderr = ret.stdout.decode('utf-8', errors='replace'), ret.stderr.decode('utf-8', errors='replace')
    # Output the result
    log.debug("*** Execution Output Start ***")
    log.debug(stdout)
    log.debug("*** Execution Output End ***")
    log.debug("**************************")
    log.debug("*** Execution Error Start ***")
    log.debug(stderr)
    log.debug("*** Execution Error End ***")
    pass

    return stdout, stderr

@tool("execute_binaries", args_schema=ExecuteBinaries, return_direct=True)
def execute_binaries(file_path: str = "PoC", cpu_core: int = 2) -> dict[str, str]:
    ''' Executes all the binaries at the specified path in parallel. The function returns a tuple of the execution output, 
    the execution error.
    '''
    executable=[]
    # folder_path=os.path.dirname(file_path)
    log.info(f"Input File path: {file_path}")
    folder_path="PoC"
    stdout=[]
    stderr=[]
    with do_in_workdir():
        file_path = os.path.join(os.getcwd(), folder_path)
        log.info(f"File path: {file_path}")
        # Iterate through all files in the folder
        for file in os.listdir(file_path):
            path = os.path.join(file_path, file)
            # Finding binaries in the folder
            _,ext = os.path.splitext(file)
            if ext=="": executable.append(path)    
        
        log.info(f"Executable files: {executable}")
        pass
            # is_executable=os.access(file, os.X_OK) 
            # log.info(f"{file}: {is_executable}")
            # if is_executable==True:
            #     executable.append(file) 

        # Run all binaries sequentially, pinned to the specified CPU core
        # cpu_core=2;
        for binary in executable:
            cmd=["taskset", "-c", str(cpu_core), binary]
            log.info(f"[+] Running command: {' '.join(cmd)}")
            try:
                ret = subprocess.run(cmd, capture_output=True, timeout=40)  # 40 seconds timeout
                stdout.append(ret.stdout.decode('utf-8', errors='replace'))
                stderr.append(ret.stderr.decode('utf-8', errors='replace'))
            except subprocess.TimeoutExpired:
                timeout_msg = f"Timeout Error: Execution of {binary} exceeded 40 seconds."
                log.error(timeout_msg)
                stdout.append("")
                stderr.append(timeout_msg)
        pass
        
    # Output the result

    log.debug("*** Execution Output Start ***")
    log.debug(stdout)
    log.debug("*** Execution Output End ***")
    log.debug("**************************")
    log.debug("*** Execution Error Start ***")
    log.debug(stderr)
    log.debug("*** Execution Error End ***")
    pass
    
    return ''.join(stdout), ''.join(stderr)
 