# tools/evaluator_tool.py
import os
import logging
import re
from typing import Dict, Optional, Tuple, Any

# Langchain imports
from langchain.tools import tool # type: ignore
from pydantic import BaseModel, Field # type: ignore

# Local imports
from tools.file_ops import do_in_workdir, read_file, write_file
from app_config import get_logger

log = get_logger(__name__)

class EvaluationMetricsReader(BaseModel):
    """
    Search for a source file in the directory that matches the attack vector name to find the evaluation metrics.

    Args:
        state: dict[str, Any] = The state of the Agent (e.g., attack_vector).

    Returns:
        Optional[str]: The contents of the evaluation metrics file if found, otherwise None.
    """
    state: dict[str, Any] = Field(..., description="The state of the Agent")

    pass # end of EvaluationMetricsReader

@tool("evaluation_metrics_reader", args_schema=EvaluationMetricsReader, return_direct=True)
def evaluation_metrics_reader(state: dict[str, Any]| None = None) -> dict[str]:
    """
    Read the evaluation metrics for the specified attack vector.

    Args:
        state: dict[str, Any]: The state of the Agent (e.g., attack_vector).
            state("attack_vector"): The attack vector name (e.g., "Spectre-v1").

    Returns:
        dict[str]: The evaluation metrics for the attack vector.
    """
    attack_vector= state.get("attack_vector")
    file_name = f"{attack_vector}-Evaluation-Metrics.txt"
    ####### Directory for Evaluation Resources   ##############
    eval_dir = "/home/Anonymous/app/eval_dir"
    file_eval_metrics = os.path.join(eval_dir, file_name)

    if not file_eval_metrics:
        log.error(f"Evaluation Metrics: Source file for attack vector '{attack_vector}' not found.")
        return None

    with open(file_eval_metrics, "r", encoding="utf-8") as f:
        print(f"[+] Reading file: {file_eval_metrics}")
        eval_metrics = f.read()

    return eval_metrics

