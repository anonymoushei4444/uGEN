######################  Offline Phase ##############################
'''
Offline Stage 2: Create RAG document
[+] Evaluator --> SYNTHESIZER AGENT
'''

# Built-in imports
import logging
import os
from typing import Any
from uuid import uuid4

# Langchain imports
from langchain_core.messages import ToolMessage # type: ignore
from langchain_core.messages.ai import AIMessage # type: ignore
from langchain_core.language_models.chat_models import BaseChatModel # type: ignore
from langchain_ollama import OllamaLLM # type: ignore
from langchain_openai import ChatOpenAI # type: ignore
from langgraph.graph import StateGraph, END # type: ignore


# Local imports
from app_config import config, get_logger
from agents.AgentState import AgentState
from agents.programmer.ProgrammerAgent import ProgrammerAgent
from agents.programmer.ProgrammerReflectionAgent import ProgrammerReflectionAgent
from agents.programmer.ProgrammerEvaluatorAgent import ProgrammerEvaluatorAgent

# Tools imports
from tools.compiler import compile_C, compile_CPP,compile_rust #collect_cache_info
from tools.measureHPC import measure_HPC
from tools.executor import execute_binaries
from tools.code_reader_tools import source_code_reader, template_code_reader, read_problem_statement
from tools.content_storage import store_content
from tools.extract_cache_info import collect_cacheinfo

# Factory + model registry
from llm_factory import build_chat_llm
from model_configs import models

# The main graph that orchestrates all agents and tools
class MainGraph():
    log: logging.Logger
    llm: BaseChatModel
    graph: Any
    programmer_agent: ProgrammerAgent
    programmer_reflection_agent: ProgrammerReflectionAgent
    programmer_evaluator_agent: ProgrammerEvaluatorAgent
    programmer_node: tuple[str, callable]
    programmer_tools_node: tuple[str, callable]
    programmer_reflection_node: tuple[str, callable]
    programmer_reflection_tools_node: tuple[str, callable]
    programmer_evaluator_node: tuple[str, callable]
    programmer_evaluator_tools_node: tuple[str, callable]


    def __init__(self, model_key: str, prompt_phase: str = "Online"):
        """ 
            model_key: key in model_configs.MODELS, e.g., "gpt-4o" or "llama-maverick".
        """
        self.log = get_logger(__name__)
        self.llm: BaseChatModel = self._get_llm(model_key)
        self.prompt_phase = prompt_phase
        self.programmer_agent = self._get_programmer_agent()
        self.programmer_reflection_agent = self._get_programmer_reflection_agent()
        self.programmer_evaluator_agent = self._get_programmer_evaluator_agent()
  
        self.programmer_node = (
            self.programmer_agent.name,
            self._programmer_node_action
        )
        self.programmer_tools_node = (
            f"{self.programmer_agent.name}Tools",
            self._programmer_tools_node_action
        )
        self.programmer_reflection_node = (
            self.programmer_reflection_agent.name,
            self._programmer_reflection_node_action
        )

        self.programmer_reflection_tools_node = (
            f"{self.programmer_reflection_agent.name}Tools",
            self._programmer_reflection_tools_node_action
        )

        self.programmer_evaluator_node = (
            self.programmer_evaluator_agent.name,
            self._programmer_evaluator_node_action
        )

        self.programmer_evaluator_tools_node = (
            f"{self.programmer_evaluator_agent.name}Tools",
            self._programmer_evaluator_tools_node_action
        )

        self.graph = self._create_graph()
        pass


    # --- LLM construction via your factory ---
    def _get_llm(self, model_key: str) -> BaseChatModel:
        if model_key not in models:
            raise ValueError(f"Unknown model key '{model_key}'. Available: {', '.join(models.keys())}")
        llm = build_chat_llm(model_key, models)
        self.log.info(f"LLM constructed via factory for key='{model_key}'")
        return llm


    def _get_programmer_agent(self) -> ProgrammerAgent:
        prog_name    = 'ProgrammerAgent0'
        prog_version = 'v1'
        prog_tools   = [read_problem_statement, collect_cacheinfo, template_code_reader, compile_C, compile_CPP, compile_rust]
        return ProgrammerAgent(
            llm     = self.llm,
            name    = prog_name,
            tools   = prog_tools,
            version = prog_version,
            prompt_phase=self.prompt_phase
            )
    

    
    def _get_programmer_reflection_agent(self) -> ProgrammerReflectionAgent:
        prog_ref_name    = 'ProgrammerReflectionAgent0'
        prog_ref_version = 'v1'
        prog_ref_tools   = [compile_C, compile_CPP, compile_rust, measure_HPC]
        return ProgrammerReflectionAgent(
            llm     = self.llm,
            name    = prog_ref_name,
            tools   = prog_ref_tools,
            version = prog_ref_version,
            prompt_phase=self.prompt_phase
            )
    
    def _get_programmer_evaluator_agent(self) -> ProgrammerEvaluatorAgent:
        prog_eva_name    = 'ProgrammerEvaluatorAgent0'
        prog_eva_version = 'v1'
        prog_eva_tools   = [execute_binaries, source_code_reader, store_content]
        return ProgrammerEvaluatorAgent(
            llm     = self.llm,
            name    = prog_eva_name,
            tools   = prog_eva_tools,
            version = prog_eva_version,
            prompt_phase=self.prompt_phase
            )

    def _create_graph(self) -> Any:
        workflow = StateGraph(AgentState)

        workflow.add_node(*self.programmer_node)
        workflow.add_node(*self.programmer_tools_node)
        workflow.add_node(*self.programmer_reflection_tools_node)
        workflow.add_node(*self.programmer_reflection_node)    
        workflow.add_node(*self.programmer_evaluator_tools_node)
        workflow.add_node(*self.programmer_evaluator_node) 

        #START -> Programmer Agent
        workflow.set_entry_point(self.programmer_node[0])

        # Programmer -> Programmer Agent -> Reflection or, Programmer Tools
        workflow.add_conditional_edges(
            self.programmer_node[0],                    # source
            self._programmer_router                     # conditional sink
        )
        # Programmer Tools -> Programmer Agent
        workflow.add_edge(
            self.programmer_tools_node[0],              # source
            self.programmer_node[0]                     # sink
        )
        # Reflection Tools -> Reflection Agent
        workflow.add_edge(
            self.programmer_reflection_tools_node[0],   # source
            self.programmer_reflection_node[0]          # sink
        )

        # Evaluator Tools -> Evaluator Agent
        workflow.add_edge(
            self.programmer_evaluator_tools_node[0],   # source
            self.programmer_evaluator_node[0]          # sink
        )

        # Evaluator Agent-> Evaluator tools or, Reflection Agent
        workflow.add_conditional_edges(
            self.programmer_evaluator_node[0],   # source
            self._programmer_evaluator_router         # sink
        )
        
        # Reflection -> Reflection Tools or, Programmer Agent, or Evaluator or, END
        workflow.add_conditional_edges(
            self.programmer_reflection_node[0],         # source
            self._programmer_reflection_router          # conditional sink
        )

        return workflow.compile()
    


    
    def _programmer_node_action(self, state: AgentState) -> AgentState:
        ''' Action for the programmer node.

        Args:
            state (AgentState): The current state of the agent.

        Returns:
            AgentState: The updated state of the agent.
        '''
        self.log.info(f"##### Programmer Node Start {state['programmer_count']+1} #####")
        result: AIMessage = self.programmer_agent.invoke(state)
        result.content = result.content.strip()
        state['programmer_count'] += 1  
        state['conversation'].append(result)
        self.log.info(f"Programmer Response:\n{result.content}")
        self.log.info(f"Programmer Tool Calls:\n{getattr(result, 'tool_calls', [])}")
        self.log.info('##### Programmer Node End #####')
        return state
    


    
    def _programmer_tools_node_action(self, state: AgentState) -> AgentState:
        # Execute programmer tools
        self.log.info(f"##### Programmer Tools Node Start {state['programmer_count']} #####")
        tool_calls = getattr(state['conversation'][-1], 'tool_calls', [])
        if not tool_calls:
            self.log.warning('No tool calls found.')
            self.log.info('##### Programmer Tools Node End #####')
            return state

        for tool_call in tool_calls:
            # Find the tool by name
            tool_obj = next((t for t in self.programmer_agent.tools if getattr(t, "name", None) == tool_call['name']), None)
            if not tool_obj:
                self.log.warning(f"Tool '{tool_call['name']}' not found.")
                state['conversation'].append(ToolMessage(
                    name=tool_call['name'],
                    tool_call_id=tool_call.get('id',''),
                    content=f"ERROR: Tool '{tool_call['name']}' is not registered in this node."
                ))
                continue
            try:
                # ret = tool_obj.invoke(tool_call['args'])  
                args = dict(tool_call['args'] or {})
                # If the tool expects `state` but it wasn't provided by the LLM, inject it.
                fields = getattr(getattr(tool_obj, "args_schema", None), "model_fields", {}) or {}
                if "state" in fields and "state" not in args:
                    # Pass a plain dict to avoid TypedDict/Message objects causing serialization issues
                    args["state"] = dict(state)
                ret = tool_obj.invoke(args)
            except Exception as e:
                ret = f"Tool execution error: {e}"
            if isinstance(ret, dict):
                content = [f"{key}:\n```\n{value}\n```" for key, value in ret.items()]
            elif isinstance(ret, tuple):
                content = [f"Programmer Tool Output:\n```\n{ret}\n```"]
            else:
                content = [f"Programmer Tool Output:\n```\n{ret}\n```"]
            result = ToolMessage(
                name = tool_call['name'],
                tool_call_id = tool_call.get('id', ''),
                content = '\n'.join(content)
            )
            state['conversation'].append(result)
            self.log.debug(result.content)
        self.log.info('##### Programmer Tools Node End #####')
        return state
    

    def _programmer_reflection_node_action(self, state: AgentState) -> AgentState:
        ''' Action for the programmer reflection node.

        Args:
            state (AgentState): The current state of the agent.

        Returns:
            AgentState: The updated state of the agent.
        '''
        self.log.info(f"##### Programmer Reflection Node Start {state['programmer_reflection_count']+1} #####")
        result: AIMessage = self.programmer_reflection_agent.invoke(state)
        result.content = result.content.strip()
        state['programmer_reflection_count'] += 1
        state['conversation'].append(result)
        self.log.info(f"Reflection Response:\n{result.content}")
        self.log.info(f"Reflection Tool Calls:\n{getattr(result, 'tool_calls', [])}")
        self.log.info('##### Programmer Reflection Node End #####')
        return state
    
    
    def _programmer_reflection_tools_node_action(self, state: AgentState) -> AgentState:
        self.log.info(f"##### Programmer Reflection Tools Node Start {state['programmer_reflection_count']} #####")
        tool_calls = getattr(state['conversation'][-1], 'tool_calls', [])
        if not tool_calls:
            self.log.warning('No tool calls found.')
            self.log.info('##### Programmer Reflection Tools Node End #####')
            return state
        for tool_call in tool_calls:
            # Find the tool by name
            tool_obj = next((t for t in self.programmer_reflection_agent.tools if getattr(t, "name", None) == tool_call['name']), None)
            if not tool_obj:
                self.log.warning(f"Tool '{tool_call['name']}' not found.")
                state['conversation'].append(ToolMessage(
                    name=tool_call['name'],
                    tool_call_id=tool_call.get('id',''),
                    content=f"ERROR: Tool '{tool_call['name']}' is not registered in this node."
                ))
                continue
            try:
                # ret = tool_obj.invoke(tool_call['args'])
                args = dict(tool_call['args'] or {})
                # If the tool expects `state` but it wasn't provided by the LLM, inject it.
                fields = getattr(getattr(tool_obj, "args_schema", None), "model_fields", {}) or {}
                if "state" in fields and "state" not in args:
                    # Pass a plain dict to avoid TypedDict/Message objects causing serialization issues
                    args["state"] = dict(state)
                ret = tool_obj.invoke(args) 
            except Exception as e:
                ret = f"Tool execution error: {e}"
            if isinstance(ret, dict):
                content = [f"{key}:\n```\n{value}\n```" for key, value in ret.items()]
            elif isinstance(ret, tuple):
                content = [f"Reflection Tool Output:\n```\n{ret}\n```"]
            else:
                content = [f"Reflection Tool Output:\n```\n{ret}\n```"]
            result = ToolMessage(
                name = tool_call['name'],
                tool_call_id = tool_call.get('id', ''),
                content = '\n'.join(content)
            )
            state['conversation'].append(result)
            self.log.debug(result.content)
        self.log.info('##### Programmer Reflection Tools Node End #####')
        return state
    
    def _programmer_evaluator_node_action(self, state: AgentState) -> AgentState:
        self.log.info(f"##### Programmer Evaluation Node Start {state['programmer_evaluator_count']+1} #####")  
        # --- HARD GATE: before asking the LLM, force execute_binaries once ---
        if not state.get('eva_exec_done', False):
            tool_call_id = uuid4().hex
            attack_vector = state.get("attack_vector", "Spectre-v1")
            file_path = f"PoC/{attack_vector}"
            core=1
            # Synthesize an AIMessage that calls execute_binaries (args will be state-injected later)
            forced = AIMessage(
                content="Step 1: Executing binaries first per policy.",
                tool_calls=[{
                    "id": tool_call_id, 
                    "name": "execute_binaries", 
                    "args": {"file_path": file_path, "cpu_core": core},
                    "type": "tool_call",
                    }]
            )
            state['conversation'].append(forced)
            self.log.info("Evaluator (forced): execute_binaries enqueued before any other tools.")
            self.log.info('##### Programmer Evaluation Node End #####')
            return state
        # --- END HARD GATE ---

        result: AIMessage = self.programmer_evaluator_agent.invoke(state)
        result.content = result.content.strip()
        state['programmer_evaluator_count'] += 1
        state['conversation'].append(result)
        self.log.info(f"Evaluator Response:\n{result.content}")
        self.log.info(f"Evaluator Tool Calls:\n{getattr(result, 'tool_calls', [])}")
        self.log.info('##### Programmer Evaluation Node End #####')
        return state

    def _programmer_evaluator_tools_node_action(self, state: AgentState) -> AgentState:
        self.log.info(f"##### Programmer Evaluator Tools Node Start {state['programmer_evaluator_count']} #####")
        tool_calls = getattr(state['conversation'][-1], 'tool_calls', [])
        if not tool_calls:
            self.log.warning('No tool calls found.')
            self.log.info('##### Programmer Evaluator Tools Node End #####')
            return state

        step1_done = bool(state.get('eva_exec_done', False))

        for tool_call in tool_calls:
            tool_name = tool_call['name']

            # --- STEP-1 ENFORCEMENT: block everything except execute_binaries until it has run once
            if not step1_done and tool_name != 'execute_binaries':
                warn = ToolMessage(
                    name=tool_name,
                    tool_call_id=tool_call.get('id',''),
                    content=("Step 1 enforcement: You must call execute_binaries first and decide "
                            "success/failure before reading/updating the RAG document. Ignoring this call.")
                )
                state['conversation'].append(warn)
                self.log.debug(warn.content)
                continue
            # --- END ENFORCEMENT

            # Find tool object
            tool_obj = next((t for t in self.programmer_evaluator_agent.tools if getattr(t, "name", None) == tool_name), None)
            if not tool_obj:
                self.log.warning(f"Tool '{tool_name}' not found.")
                state['conversation'].append(ToolMessage(
                    name=tool_name,
                    tool_call_id=tool_call.get('id',''),
                    content=f"ERROR: Tool '{tool_name}' is not registered in this node."
                ))
                continue

            try:
                args = dict(tool_call.get('args') or {})
                fields = getattr(getattr(tool_obj, "args_schema", None), "model_fields", {}) or {}
                if "state" in fields and "state" not in args:
                    args["state"] = dict(state)
                ret = tool_obj.invoke(args)
            except Exception as e:
                ret = f"Tool execution error: {e}"

            # Record outputs as before
            if isinstance(ret, dict):
                content = [f"{k}:\n```\n{v}\n```" for k, v in ret.items()]
            elif isinstance(ret, tuple):
                content = [f"Evaluator Tool Output:\n```\n{ret}\n```"]
            else:
                content = [f"Evaluator Tool Output:\n```\n{ret}\n```"]

            result = ToolMessage(
                name = tool_name,
                tool_call_id = tool_call.get('id', ''),
                content = '\n'.join(content)
            )
            state['conversation'].append(result)
            self.log.debug(result.content)

            # If execute_binaries ran, flip the gate and stash its output for the LLM to judge
            if tool_name == 'execute_binaries':
                state['eva_exec_done'] = True
                # optional: keep the latest output string for downstream decisions
                if isinstance(ret, str):
                    state['eva_exec_output'] = ret
                elif isinstance(ret, dict):
                    state['eva_exec_output'] = '\n'.join(f"{k}: {v}" for k, v in ret.items())
                step1_done = True  # so subsequent tools in this same turn (if any) can be allowed

        self.log.info('##### Programmer Evaluator Tools Node End #####')
        return state


    def _programmer_router(self, state: AgentState) -> str:
        # After programmer: go to tools if any, else to reflection
        last = state['conversation'][-1]
        if getattr(last, 'tool_calls', None):
            return self.programmer_tools_node[0]
        return self.programmer_reflection_node[0]
    

    def _programmer_reflection_router(self, state: AgentState) -> str:
        # After reflection: either run tools, return to programmer, or proceed to evaluator
        last = state['conversation'][-1]
        if state['programmer_reflection_count'] >= config.PROG_REF_CNT:
            # Check for unresolved tool calls
            if getattr(last, 'tool_calls', None):
                tool_call_ids = {tc['id'] for tc in last.tool_calls}
                answered_ids = {
                    msg.tool_call_id
                    for msg in state['conversation']
                    if isinstance(msg, ToolMessage) and hasattr(msg, 'tool_call_id')
                }
                if not tool_call_ids.issubset(answered_ids):
                    return self.programmer_reflection_tools_node[0]
            return self.programmer_evaluator_node[0]


        if getattr(last, 'tool_calls', None):
            return self.programmer_reflection_tools_node[0]
        return self.programmer_node[0]
    
    
    def _programmer_evaluator_router(self, state: AgentState) -> str:
        # After evaluator: potentially run tools up to limit, else end

        # Stop only when we've reached or exceeded the limit
        last = state['conversation'][-1]
        if state['programmer_evaluator_count'] >= config.PROG_EVA_CNT:
            return END
        
        # if  state['programmer_evaluator_count'] < config.PROG_EVA_CNT and state['conversation'][-1].tool_calls:
        #     return self.programmer_evaluator_tools_node[0]
        
        # If the Evaluator produced tool calls, go run them
        if getattr(last, 'tool_calls', None):
            return self.programmer_evaluator_tools_node[0]
        
         # Otherwise, keep iterating the Evaluator up to the limit
        return self.programmer_evaluator_node[0]
        

    def run(self, state: AgentState) -> None:
        events = self.graph.stream(state, {'recursion_limit': config.RECURSION_LIMIT})
        for event in events:
            # self.log.info('----- Event Start -----')
            # self.log.debug(event)
            # self.log.info('----- Event End -----')
            pass
        return
    
    pass # end of MainGraph
