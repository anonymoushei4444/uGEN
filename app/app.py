# Built-in imports
from uuid import uuid4
import logging
import os
import importlib

# Local imports
from app_config import config, get_logger
from model_configs import models
from agents.AgentState import AgentState
from retrieval_queries import get_retrieval_questions



PHASE_CONFIG = {
    "Offline_1": "graph_offline_s1",
    "Offline_2": "graph_offline_s2",
    "Offline_3": "graph_offline_s3",
    "Online": "graph_online_s4",
}



# =================  Graph Selection =================
# graph_offline_s1 --> S1: Identifying knowledge gaps 
# graph_offline_s2 --> S2: RAG document generation
# graph_offline_s3 --> S3: RAG Validation and refinement
# graph_online_s4  --> S4: Deployment 

SELECTED_PHASE = "Online"  # Change this to test different phases :  "Online", "Offline_1", "Offline_2", "Offline_3"
# ====================================================

if SELECTED_PHASE not in PHASE_CONFIG:
    raise SystemExit(f"Unknown phase '{SELECTED_PHASE}'. Available: {', '.join(PHASE_CONFIG.keys())}")


# Framework entry point
if __name__ == '__main__':
    # UUID must be set BEFORE importing the graph module so that all module-level
    # loggers in tool files are initialized with the correct log file path.
    config.UUID = uuid4().hex
    graph_module_name = PHASE_CONFIG[SELECTED_PHASE]
    graph_module = importlib.import_module(graph_module_name)
    MainGraph = getattr(graph_module, "MainGraph")
    log = get_logger(__name__)

    # ============ MANUAL MODEL SELECTION ============
    # EDIT THIS LINE ONLY: choose either  "gpt-4o" or "claude-sonnet-4" or "Qwen3-Coder" 
    SELECTED_MODEL_KEY = "Qwen3-Coder" 
    config.SELECTED_MODEL_KEY = SELECTED_MODEL_KEY
    # ===============================================

    # Validate selection
    if SELECTED_MODEL_KEY not in models:
        raise SystemExit(
            f"Unknown model key '{SELECTED_MODEL_KEY}'. "
            f"Available: {', '.join(models.keys())}"
        )

    selected_model = models[SELECTED_MODEL_KEY]

    # Set the global config
    config.MODEL = f"{selected_model['provider']}-{selected_model['model']}"
    config.ATTACK_VECTORS = 'Spectre-v1'
    config.TARGET_LANGUAGES = 'C'
    config.TARGET_FILE_EXTENSION = 'c'
    config.VICTIM_FUNCTION = 1  # 1 is default, set as needed for different victim functions
    config.TEMPLATE_NUMBER = 3  # set template number as needed for different attack metrics

    # Run the Langchain
    log.info(f"++++++++++ Starting Langchain with UUID: {config.UUID} ++++++++++")
    log.info(f"++++++++++ Using model: {config.MODEL} ++++++++++")
    log.info(f"++++++++++ Running: {SELECTED_PHASE}   ++++++++++")
    # Initial agent state   
    initial_state = AgentState()
    initial_state['attack_vector'] = config.ATTACK_VECTORS
    initial_state['target_language'] = config.TARGET_LANGUAGES
    initial_state['target_file_extension'] = config.TARGET_FILE_EXTENSION
    initial_state['victim_function'] = config.VICTIM_FUNCTION
    initial_state['template_number']   = config.TEMPLATE_NUMBER
    initial_state['retrieval_questions'] = get_retrieval_questions(SELECTED_MODEL_KEY, config.ATTACK_VECTORS)
    initial_state['query_index'] = 0
    initial_state['programmer_count'] = 0
    initial_state['programmer_reflection_count'] = 0
    initial_state['programmer_evaluator_count'] = 0
    initial_state['conversation'] = list()
    initial_state['programmer_response'] = None
    initial_state['programmer_reflection_response'] = None
    initial_state['programmer_tool_response'] = list()
    initial_state['programmer_reflection_tool_response'] = list()
    initial_state['retrieval_responses'] = list()
    initial_state['awaiting_retrieval'] = False
    initial_state['retrieval_result_ready'] = False
    # initial_state['retrieval_status'] = True
    initial_state['retrieval_tool_call_id'] = uuid4().hex  # Generate a unique tool_call_id
    initial_state['selected_model_key'] = SELECTED_MODEL_KEY

    initial_state['total_nodes_executed'] = 0       # Track graph node executions
    initial_state['eva_exec_done'] = False          # Step-1 gate: has binary been executed at least once?
    initial_state['eva_exec_output'] = ""           # Optional: store exec stdout/stderr for LLM to read from conversation
    initial_state['eva_decision'] = None            # Optional: "success" | "fail"
    initial_state["programmer_source_code"] = None
    
    # New fields for convergence detection and final summary
    initial_state['convergence_achieved'] = False   # Set to True when Reflection Agent confirms success
    initial_state['final_summary'] = ""             # Final summary message with status

    graph = MainGraph(SELECTED_MODEL_KEY, prompt_phase=SELECTED_PHASE)
    graph.run(initial_state)
    
    # Display final summary after execution completes
    if initial_state.get('final_summary'):
        print(initial_state['final_summary'])
    
    pass
    log.info(f"++++++++++ Langchain completed with UUID: {config.UUID} ++++++++++")

