# tools/feedback_reader.py
# Goal:Read feedback files for RAG-Documents 
import os
import logging
import re
from typing import Dict, Any, Optional, Tuple

# Langchain imports
from langchain.tools import tool # type: ignore
from pydantic import BaseModel, Field # type: ignore

# Local imports
from tools.file_ops import do_in_workdir, read_file, write_file
from app_config import get_logger, config

log = get_logger(__name__)

class FeedbackReader(BaseModel):
    """
    Search for a source file in the directory that matches the attack vector name to find the evaluation metrics.

    Args:
        attack_vector (str): The attack vector name (e.g., "Spectre-v1").

    Returns:
        Optional[str]: The contents of the evaluation metrics file if found, otherwise None.
    """
    file_contents: str = Field(description="the contents of the file")
    state: dict[str, Any] = Field(default=None, description="The state of the Agent")
    pass # end of FeedbackReader

def get_feedback_dir(selected_model_key: str, attack_vector: str, template_number: int) -> str:
    key = (selected_model_key or "").lower()
    attack_vector = (attack_vector or "").strip()
    # Normalize attack vector for directory naming
    attack_vector_dir = attack_vector.replace(" ", "-")
    if "claude" in key or "anthropic" in key:
        model_dir = "Claude-4"
    elif "gpt" in key or "openai" in key or "4o" in key:
        model_dir = "GPT-4o"
    elif "qwen3-coder" in key or "together" in key:
        model_dir = "Qwen3"
    else:
        model_dir = "None"  # Default fallback
    feedback_dir = f"/home/Anonymous/app/Expert_Feedback/{model_dir}/{attack_vector_dir}/T{template_number}"
    return feedback_dir

def get_rag_dir(selected_model_key: str, attack_vector: str) -> str:
    key = (selected_model_key or "").lower()
    attack_vector = (attack_vector or "").strip()
    # Normalize attack vector for directory naming
    attack_vector_dir = attack_vector.replace(" ", "-")
    if "claude" in key or "anthropic" in key:
        model_dir = "/home/Anonymous/workdir/RAG_Dir_Claude"
    elif "gpt" in key or "openai" in key or "4o" in key:
        model_dir = "/home/Anonymous/workdir/RAG_Dir_GPT"
    elif "qwen3-coder" in key or "together" in key:
        model_dir = "/home/Anonymous/workdir/RAG_Dir_Qwen3"
    else:
        model_dir = "None"  # Default fallback
        log.error(f"[get_rag_dir] Unknown model key '{key}'.)")
    rag_dir = f"{model_dir}/{attack_vector_dir}"
    return rag_dir

@tool("read_feedback", args_schema=FeedbackReader, return_direct=True)
def read_feedback(file_contents: str, state: Dict[str, Any] | None = None) -> dict[str]:
    """
    Read the feedback for the specified attack attribute or rag document.

    Args:
        attack_vector (str): The attack vector name (e.g., "Spectre-v1").

    Returns:
        dict[str]: The evaluation metrics for the attack vector.
    """

    file_name = "Feedback.txt"

    # Prefer runtime state's template_number; fallback to global config
    template_number = (state or {}).get("template_number", getattr(config, "TEMPLATE_NUMBER", 3))
    attack_vector = (state or {}).get("attack_vector")
    selected_model_key = (state or {}).get("selected_model_key")
    

    
    ####### Directory for Feedback Resources   ##############
    # feedback_dir = f"/home/Anonymous/app/Expert_Feedback/GPT-4o/T{template_number}"
    feedback_dir = get_feedback_dir(selected_model_key, attack_vector, template_number)
    file_feedback = os.path.join(feedback_dir, file_name)



    if not file_feedback:
        log.error(f"Feedback: Source file for attack vector '{attack_vector}', Template 'T{template_number}' not found.")
        return None

    with open(file_feedback, "r", encoding="utf-8") as f:
        print(f"[+] Reading file: {file_feedback}")
        feedback = f.read()

    return feedback

@tool("read_rag_document", args_schema=FeedbackReader, return_direct=True)
def read_rag_document(file_contents: str, state: Dict[str, Any] | None = None) -> dict[str]:
    """
    Read the feedback for the specified attack attribute or rag document.

    Args:
        attack_vector (str): The attack vector name (e.g., "Spectre-v1").

    Returns:
        dict[str]: The evaluation metrics for the attack vector.
    """

    # Prefer runtime state's template_number; fallback to global config
    template_number = (state or {}).get("template_number", getattr(config, "TEMPLATE_NUMBER", 3))
    selected_model_key = (state or {}).get("selected_model_key")
    attack_vector = (state or {}).get("attack_vector", "Spectre-v1")
    file_name = f"T{template_number}_RAG_Document.txt"
    
    ####### Directory for RAG Resources   ##############
    # rag_dir = "/home/Anonymous/workdir/RAG_Dir_GPT"
    rag_dir = get_rag_dir(selected_model_key, attack_vector)
    file_rag = os.path.join(rag_dir, file_name)

    if not file_rag:
        log.error(f"RAG: RAG Document for attack vector '{attack_vector}', Template 'T{template_number}' not found.")
        return None

    with open(file_rag, "r", encoding="utf-8") as f:
        log.info(f"[+] Reading RAG Document from: {file_rag}")
        rag_doc = f.read()

    return rag_doc

@tool("store_rag_document", args_schema=FeedbackReader, return_direct=True)
def store_rag_document(file_contents: str, state: Dict[str, Any] | None = None):
    """
     Save updated rag document based on the feedback in the specified file.
    Args:
        file_contents (str): The contents of the code to be saved.
      """

    # Prefer runtime state's template_number; fallback to global config
    template_number = (state or {}).get("template_number", getattr(config, "TEMPLATE_NUMBER", 3))
    selected_model_key = (state or {}).get("selected_model_key")
    attack_vector = (state or {}).get("attack_vector", "Spectre-v1")
    
    file_name = f"T{template_number}_RAG_Document.txt"
    ####### Directory for RAG Resources   ##############
    # rag_dir = "/home/Anonymous/workdir/RAG_Dir_GPT"
    rag_dir = get_rag_dir(selected_model_key, attack_vector)
    file_rag = os.path.join(rag_dir, file_name)

    # Ensure the directory exists
    os.makedirs(rag_dir, mode=0o755, exist_ok=True)
    log.info(f"[store_content] Saving content to {file_rag}")
    log.debug(f"[store_content] Updated Content:\n{file_contents}")
    
    
    try:
        with open(file_rag, 'w', encoding='utf-8') as f:
            f.write(file_contents)
        log.info(f"[+] File overwritten at: {file_rag}")
        return {"status": "success", "message": f"File updated at {file_rag}"}

    except PermissionError as e:
        log.error(f"Permission denied: {e}")
        return {"error": "Permission denied while writing to file."}
    
    except Exception as e:
        log.error(f"Error saving file: {e}")
        return {"error": f"Failed to save file: {str(e)}"}

