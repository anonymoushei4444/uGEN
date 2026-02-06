# Built-in imports
from uuid import uuid4
import logging
import os
import importlib

# -----------------  Graph Selection -------------------------------------------
# graph without RAG with Evaluator : Offline Stage 1 --> S1: Identifying knowledge gaps 
# from graph_offline_s1 import MainGraph

# graph with RAG with Evaluator : Offline Stage 2 --> S2: RAG document generation
# from graph_offline_s2 import MainGraph

# graph with RAG with Evaluator : Offline Stage 3 --> S3: RAG Validation and refinement
# from graph_offline_s3 import MainGraph

# graph without RAG with Evaluator : Online Stage --> S4: Deployment
# from graph_online import MainGraph
# -------------------- END of Graph Selection ----------------------------------------


# Local imports
from app_config import config, get_logger
from model_configs import models
from agents.AgentState import AgentState



PHASE_CONFIG = {
    "Offline_1": "graph_offline_s1",
    "Offline_2": "graph_offline_s2-v2",
    "Offline_3": "graph_offline_s3-v3",
    "Online": "graph_online_v3",
}

# ============ MANUAL PHASE SELECTION ============
SELECTED_PHASE = "Online"  # Change this to test different phases :  "Online", "Offline_1", "Offline_2", "Offline_3"
# ================================================

if SELECTED_PHASE not in PHASE_CONFIG:
    raise SystemExit(f"Unknown phase '{SELECTED_PHASE}'. Available: {', '.join(PHASE_CONFIG.keys())}")

graph_module_name = PHASE_CONFIG[SELECTED_PHASE]
graph_module = importlib.import_module(graph_module_name)
MainGraph = getattr(graph_module, "MainGraph")




# Framework entry point
if __name__ == '__main__':
    config.UUID = uuid4().hex
    log = get_logger(__name__)

    # ============ MANUAL MODEL SELECTION ============
    # EDIT THIS LINE ONLY: choose either  "gpt-4o" or "claude-sonnet-4" or "Qwen3-Coder" 
    SELECTED_MODEL_KEY = "gpt-4o" 
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
    # =================================================================
    ## Retrieval Queries for Spectre-v1
        # Claude-Spectre-v1: ["Controlled Branch Mispredictor", "Controlled Delay", "Stride Masking", "Measuring Memory Access Time", "Array Initialization"]
        # GPT-4o-Spectre-v1: ["Array Initialization", "Controlled Branch Mispredictor", "Cache Eviction", "Controlled Delay","Measuring Memory Access Time", "Stride Masking", "Score Accumulation"]
        # Qwen3-Coder-Spectre-v1: ["Controlled Branch Mispredictor", "Controlled Delay" , "Mixed Probe order", "Probe and High-Resolution Timing", "Score Accumulation", "Array Initialization"]
    
    ## Retrieval Queries for Prime+Probe
        # Claude-Prime-Probe: ["Randomized Pointer-Chase Linked List Construction", "Probe and High-Resolution Timing", "Victim Memory Access"]
        # GPT-4o-Prime-Probe: ["Eviction Set Construction", "Randomized Pointer-Chase Linked List Construction", "Probe and High-Resolution Timing", "Victim Memory Access"]
        # Qwen3-Coder-Prime-Probe: ["Randomized Pointer-Chase Linked List Construction", "Probe and High-Resolution Timing", "Victim Memory Access"]
    
    initial_state['retrieval_questions'] = ["Controlled Branch Mispredictor", "Controlled Delay" , "Mixed Probe order", "Probe and High-Resolution Timing", "Score Accumulation", "Array Initialization"]
    
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


    initial_state['eva_exec_done'] = False          # Step-1 gate: has binary been executed at least once?
    initial_state['eva_exec_output'] = ""           # Optional: store exec stdout/stderr for LLM to read from conversation
    initial_state['eva_decision'] = None            # Optional: "success" | "fail"
    initial_state["programmer_source_code"] = None

    graph = MainGraph(SELECTED_MODEL_KEY, prompt_phase=SELECTED_PHASE)
    graph.run(initial_state)
    pass
    log.info(f"++++++++++ Langchain completed with UUID: {config.UUID} ++++++++++")
