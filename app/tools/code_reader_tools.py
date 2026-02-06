# tools/code_reader_tools.py
import os
import logging
import re
# from typing import Dict, Optional, Tuple
from typing_extensions import TypedDict
from typing import Dict, Any
import subprocess

# Langchain imports
from langchain.tools import tool # type: ignore
from pydantic import BaseModel, Field # type: ignore

# Local imports
from app_config import get_logger, config
from agents.AgentState import AgentState

log = get_logger(__name__)

class SourceCodeReader(BaseModel):
    """
    Search for a source file in the directory that matches the attack vector name and target file extension.

    Args:
        state: dict[str, Any] = The state of the Agent (e.g., attack_vector, template_number, victim_function).

    Returns:
        Optional[str]: The full file path if found, otherwise None.
    """
    state: dict[str, Any] = Field(..., description="The state of the Agent")

    pass # end of SourceCodeReader
    
@tool("source_code_reader", args_schema=SourceCodeReader, return_direct=True)
def source_code_reader(state: Dict[str, Any] | None = None) -> dict[str]:
    """
    Retrieve the source codes (original and generated) based on the attack vector name.

    Args:
        state (dict): The state of the Agent which contains 'attack_vector' and 'target_file_extension'.
            state("attack_vector"): The attack vector name (e.g., "Spectre-v1").
            state("target_file_extension"): The expected file extension (e.g., "c", "rs").
    Returns:
        org_code (str): The content of the original (ground truth) source code file or an error message.
    """
           
    attack_vector = state.get("attack_vector")
    target_file_extension = state.get("target_file_extension")
    file_name = f"{attack_vector}.{target_file_extension}"


    ####### Ground Truth   ##############
    src_code_dir = "/home/Anonymous/app/src_code_dir"
    file_path_ground_truth = os.path.join(src_code_dir, file_name)

    if not file_path_ground_truth:
        log.error(f"Ground Truth/Original Source Code for attack vector '{attack_vector}' not found.")
        return None

    with open(file_path_ground_truth, "r", encoding="utf-8") as f:
        log.info(f"[+] Reading Ground Truth/Original Source Code: {file_path_ground_truth}")
        org_code = f.read()


    return org_code


@tool("template_code_reader", args_schema=SourceCodeReader, return_direct=True)
def template_code_reader(state: Dict[str, Any] | None = None) -> dict[str]:
    """
    Retrieve the template code (considering as starting checkpoint) based on the attack vector name.

    Args:
        state (dict): The state of the Agent which contains 'template_number', 'attack_vector', and 'target_file_extension'.
    Returns:
        template_code (str): The content of the template source code file that will act as the starting checkpoint.
    """
           
    attack_vector = state.get("attack_vector")
    target_file_extension = state.get("target_file_extension")  
    template_number = getattr(config, "TEMPLATE_NUMBER", 3)
    # Prefer runtime state's template_number; fallback to global config
    # template_number = (state or {}).get("template_number", getattr(config, "TEMPLATE_NUMBER", 3))
    # file_name = f"T4_{attack_vector}.{target_file_extension}"
    file_name = f"T{template_number}_{attack_vector}.{target_file_extension}"

    ####### Template Code   ##############
    template_code_dir = f"/home/Anonymous/app/template_code_dir/{attack_vector}"
    file_path_template_code = os.path.join(template_code_dir, file_name)

    if not file_path_template_code:
        log.error(f"Template Code: Source file for attack vector '{attack_vector}' not found.")
        return None

    with open(file_path_template_code, "r", encoding="utf-8") as f:
        print(f"[+] Reading file: {file_path_template_code}")
        template_code = f.read()

    return template_code


@tool("read_problem_statement", args_schema=SourceCodeReader, return_direct=True)
def read_problem_statement(state: Dict[str, Any] | None = None) -> dict[str]:
    """
    Retrieve the problem statement of the PoC based on the attack vector name.

    Args:
        state (dict): The state of the Agent which contains 'victim_function', 'attack_vector', and 'target_file_extension'.
    Returns:
        prob_statement (str): The content of the problem statement for the relevant PoC of the attack vector.
    """
    
    attack_vector = state.get("attack_vector")
    # Prefer the runtime state's victim_function; fallback to global config
    # victim_function = (state or {}).get("victim_function", getattr(config, "VICTIM_FUNCTION", 1))
    victim_function = getattr(config, "VICTIM_FUNCTION", 1)
    if victim_function == 1:
        file_name = f"{attack_vector}-PoC.txt"
    else:
        file_name = f"{attack_vector}-PoC-VF{victim_function}.txt"


    ####### Test Code   ##############
    prob_statement_dir = "/home/Anonymous/app/prob_statement_dir"
    file_path_prob_statement = os.path.join(prob_statement_dir, file_name)

    if not file_path_prob_statement:
        log.error(f"Problem Statement: Source file for attack vector '{attack_vector}' not found.")
        return None

    with open(file_path_prob_statement, "r", encoding="utf-8") as f:
        print(f"[+] Reading file: {file_path_prob_statement}")
        prob_statement = f.read()

    return prob_statement

