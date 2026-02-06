# tools/ground_truth_retriever.py
# compatible with graph_wo_rag_w_evaluator
import os
import logging
import re
import uuid
from typing import Dict, Any, Optional, Tuple

# Langchain imports
from langchain.tools import tool # type: ignore
from pydantic import BaseModel, Field # type: ignore

# Local imports
from tools.file_ops import do_in_workdir, read_file, write_file
from app_config import get_logger, config

log = get_logger(__name__)

class StoreContent(BaseModel):
    """
    Search for a source file in the directory that matches the attack vector name and target file extension.

    Args:
        file_path: str = Field(description="the path of the file to be saved including file name")
        file_contents: str = Field(description="the contents of the file")
        state: (optional) runtime state with 'selected_model_key' and 'template_number'.

    Returns:
        Optional[str]: The full file path if found, otherwise None.
    """
    file_path: str = Field(description="the path of the file to be saved")
    file_contents: str = Field(description="the contents of the file")
    state: Dict[str, Any] = Field(default_factory=dict)
    pass # end of StoreContent

def _resolve_rag_dir(state: Dict[str, Any]) -> str:
    # Model family
    selected_model_key = (
        state.get("selected_model_key")
        or getattr(config, "SELECTED_MODEL_KEY", None)
        or os.getenv("SELECTED_MODEL_KEY")
    )
    key = str(selected_model_key).lower()
    attack_vector = state.get("attack_vector")

    if ("claude" in key) or ("anthropic" in key):
        base_dir = f"/home/Anonymous/workdir/RAG_Dir_Claude_Draft/{attack_vector}"
    elif ("gpt" in key) or ("openai" in key):
        base_dir = f"/home/Anonymous/workdir/RAG_Dir_GPT_Draft/{attack_vector}"
    elif ("qwen3-coder" in key) or ("together" in key):
        base_dir = f"/home/Anonymous/workdir/RAG_Dir_Qwen3_Draft/{attack_vector}"
    else:
        base_dir = f"/home/Anonymous/workdir/"
        log.error(f"[resolve_rag_dir] Unknown model key '{selected_model_key}'.)")

    # Template number
    tn = state.get("template_number", getattr(config, "TEMPLATE_NUMBER", 1))

    return os.path.join(base_dir, f"T{tn}")

def _safe_filename(name: str) -> str:
    # Keep letters, numbers, _, -, ., spaces; turn others into '_', then collapse spaces
    name = re.sub(r"[^\w\-. ]+", "_", name)
    name = re.sub(r"\s+", "_", name).strip("._")
    return name or "untitled"

@tool("store_content", args_schema=StoreContent, return_direct=True)
def store_content(file_path: str, file_contents: str, state: Dict[str, Any] = {}) -> dict[str, str]:
    """
     Store the document
     args: 
        file_path: str = Field(description="the name of the file to be saved")
        file_contents: str = Field(description="the path of the file to be saved including file name")
    """

    rag_dir = _resolve_rag_dir(state)
    # --- make filename unique ---
    base = os.path.basename(file_path)
    base = _safe_filename(base)
    stem, ext = os.path.splitext(base)

    # short UID to guarantee uniqueness even within the same second
    # ts   = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    run_uid = getattr(config, "UUID", "")  # set in app.py: config.UUID = uuid4().hex
    unique_name = f"{stem}_{run_uid}{ext}"


    rag_file = os.path.join(rag_dir, unique_name)

   

    # Ensure the directory exists
    os.makedirs(rag_dir, mode=0o755, exist_ok=True)
    log.info(f"[store_content] Saving content to {rag_file}")
    log.debug(f"[store_content] New Content:\n{file_contents}")
    
    
    try:
        with open(rag_file, 'w', encoding='utf-8') as f:
            f.write(file_contents)
        log.info(f"[+] File overwritten at: {rag_file}")
        return {"status": "success", "message": f"File updated at {rag_file}"}
    
    except PermissionError as e:
        log.error(f"Permission denied: {e}")
        return {"error": "Permission denied while writing to file."}
    
    except Exception as e:
        log.error(f"Error saving file: {e}")
        return {"error": f"Failed to save file: {str(e)}"}
    


@tool("save_missing_metrics", args_schema=StoreContent, return_direct=True)
def save_missing_metrics(file_path: str, file_contents: str, state: Dict[str, Any] = {}) -> None:
    """
     Save proof-of-concept code in the specified file.
    Args:
        file_path (str): The path of the file to save the code.
        file_contents (str): The contents of the code to be saved.
      """
    
    write_file(file_path, file_contents)



