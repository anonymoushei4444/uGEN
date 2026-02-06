# Built-in imports
# from typing import TypedDict
from typing_extensions import TypedDict

# Langchain imports
from langchain_core.messages import BaseMessage # type: ignore

# Local imports

class AgentState(TypedDict):
    attack_vector: str
    target_language: str
    target_file_extension: str
    victim_function: int
    template_number: int
    selected_model_key: str
    query_index: int
    conversation: list[BaseMessage]
    programmer_response: BaseMessage
    programmer_reflection_response: BaseMessage
    programmer_tool_response: list[tuple[str,str]]
    programmer_reflection_tool_response: list[tuple[str,str]]
    programmer_count: int
    programmer_reflection_count: int
    programmer_evaluator_count: int
    programmer_source_code: str | None
    
    retrieval_questions: list[str]
    retrieval_responses: list[tuple[str,str]]
    retrieval_status: bool
    awaiting_retrieval: bool                 # gate: Programmer must yield to Retriever
    retrieval_result_ready: bool             # gate: Programmer can resume


    eva_exec_done: bool            # has execute_binaries run at least once?
    eva_exec_output: str           # latest stdout/stderr from execute_binaries
    eva_decision: str | None       # "success" | "fail" (or None)
    
    pass # end of AgentState
