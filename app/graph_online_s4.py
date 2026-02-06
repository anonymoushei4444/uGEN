######################  Online Phase ##############################
'''
Online Stage 
[+] RAG
[-] Evaluator 
'''

# Built-in imports
import logging
import re, json, ast
import inspect
from uuid import uuid4
from typing import Any, Dict, List


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
from tools.compiler import compile_C, compile_CPP, compile_rust #collect_cache_info
from tools.measureHPC import measure_HPC
from tools.executor import execute_binaries
from tools.code_reader_tools import source_code_reader, read_problem_statement
from tools.content_storage import store_content, save_missing_metrics
from tools.evaluator_tool import evaluation_metrics_reader
from tools.extract_cache_info import collect_cacheinfo


# Factory + model registry
from llm_factory import build_chat_llm
from model_configs import models


# Import the new retriever tool and the initialize_retriever function
from tools.retriever_llm import rag_tool

# The main graph that orchestrates all agents and tools
class MainGraph():
    log: logging.Logger
    llm: BaseChatModel
    graph: Any
    programmer_agent: ProgrammerAgent
    programmer_reflection_agent: ProgrammerReflectionAgent
    programmer_node: tuple[str, callable]
    programmer_tools_node: tuple[str, callable]
    programmer_reflection_node: tuple[str, callable]
    programmer_reflection_tools_node: tuple[str, callable]
    programmer_retriever_node: tuple[str, callable]




    def __init__(self, model_key: str, prompt_phase: str = "Online"):
        """ 
            model_key: key in model_configs.MODELS, e.g., "gpt-4o" or "llama-maverick".
        """
        self.log = get_logger(__name__)
        self.llm: BaseChatModel = self._get_llm(model_key)
        self.prompt_phase = prompt_phase
        self.programmer_agent = self._get_programmer_agent()
        self.programmer_reflection_agent = self._get_programmer_reflection_agent()

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
        
        self.programmer_retriever_node = (
        f"{self.programmer_agent.name}Retriever",
        self._retriever_node_action
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
        prog_tools   = [read_problem_statement, collect_cacheinfo, compile_C, compile_CPP, compile_rust]
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
        prog_ref_tools   = [compile_C, compile_CPP, compile_rust, measure_HPC, execute_binaries]
        return ProgrammerReflectionAgent(
            llm     = self.llm,
            name    = prog_ref_name,
            tools   = prog_ref_tools,
            version = prog_ref_version,
            prompt_phase=self.prompt_phase
            )
    

    def _create_graph(self) -> Any:
        workflow = StateGraph(AgentState)

        workflow.add_node(*self.programmer_node)
        workflow.add_node(*self.programmer_tools_node)
        workflow.add_node(*self.programmer_reflection_tools_node)
        workflow.add_node(*self.programmer_reflection_node)    
        workflow.add_node(*self.programmer_retriever_node) 

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

        workflow.add_edge(
            self.programmer_retriever_node[0],      # source
            self.programmer_node[0]  # sink
        )
      
        # Reflection -> Reflection Tools or, Programmer Agent, or END
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


        # Only append retrieval_responses if present, then clear them
        if 'retrieval_responses' in state and state['retrieval_responses']:
            state['conversation'].extend(state['retrieval_responses'])
            state['retrieval_responses'].clear()  # Clear after use


        result: AIMessage = self.programmer_agent.invoke(state)
        result.content = result.content.strip()

        state['programmer_count'] += 1  
        state['conversation'].append(result)
        self.log.info(f"Programmer Agent Response:\n{result.content}")
        # self.log.info(f"Programmer Agent Tool Calls:\n{result.tool_calls}")
        self.log.info('##### Programmer Node End #####')
        return state
    

    def _programmer_tools_node_action(self, state: AgentState) -> AgentState:
        ''' Action for the programmer tools node.
        Args:
            state (AgentState): The current state of the agent.
        Returns:
            AgentState: The updated state of the agent.
        '''
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
                # **** start: version 1 ****
                # ret = tool_obj.invoke(tool_call['args']) 
                # **** end: version 1 ****

                # **** start: version 2 ****
                args = dict(tool_call['args'] or {})
                # If the tool expects `state` but it wasn't provided by the LLM, inject it.
                fields = getattr(getattr(tool_obj, "args_schema", None), "model_fields", {}) or {}
                if "state" in fields and "state" not in args:
                    # Pass a plain dict to avoid TypedDict/Message objects causing serialization issues
                    args["state"] = dict(state)
                ret = tool_obj.invoke(args)
                # **** end: version 2 ****

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
    

    def _retriever_node_action(self, state: AgentState) -> AgentState:
        ''' Action for the retriever node.
        Args:
            state (AgentState): The current state of the agent.
        Returns:
            AgentState: The updated state of the agent.
        '''

        self.log.info(f"##### Retriever Node Start {state['query_index']+1}#####")

        # Simulate retrieval based on document questions
        query_index = state.get('query_index',[])
        retrieval_questions = state.get('retrieval_questions', [])
        query = retrieval_questions[query_index] if query_index < len(retrieval_questions) else ""
        # self.log.info(f"Query: {query}")
        # tool_call_id = state.get('retrieval_tool_call_id', uuid4().hex)
       
        # Directly invoke the rag_tool as in offline graph
        try:
            ret = rag_tool.invoke({'query': query, 'state': dict(state)})
        except Exception as e:
            ret = f"Tool execution error: {e}"

        # Format output as in offline graph
        if isinstance(ret, dict):
            content = [f"{key}:\n```\n{value}\n```" for key, value in ret.items()]
        elif isinstance(ret, tuple):
            content = [f"Retriever Tool Output:\n```\n{ret}\n```"]
        else:
            content = [f"Retriever Tool Output:\n```\n{ret}\n```"]

        # result = ToolMessage(
        #     name='rag_tool',
        #     tool_call_id=tool_call_id,
        #     content='\n'.join(content)
        # )
        result = AIMessage(
          content=f"""Retrieved information for query: \"{query}\"\n{''.join(content)}"""
        )
        # state['conversation'].append(result)
        state['retrieval_responses'].append(result)
        self.log.info(f"Question: {query}\nRetrieved Answer: {content or 'No answer found.'}")

        state['query_index'] += 1
        self.log.info(f"##### Retriever Node End #####")
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
        self.log.info(f"Programmer Reflection Agent Response:\n{result.content}")
        # self.log.info(f"Programmer Reflection Agent Tool Calls:\n{result.tool_calls}")
        self.log.info('##### Programmer Reflection Node End #####')
        return state
    
    
    def _programmer_reflection_tools_node_action(self, state: AgentState) -> AgentState:
        ''' Action for the programmer reflection tools node.
        Args:
            state (AgentState): The current state of the agent.
        Returns:
            AgentState: The updated state of the agent.
        '''
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
                # **** start: version 1 ****
                # ret = tool_obj.invoke(tool_call['args']) 
                # **** end: version 1 ****

                # **** start: version 2 ****
                args = dict(tool_call['args'] or {})
                # If the tool expects `state` but it wasn't provided by the LLM, inject it.
                fields = getattr(getattr(tool_obj, "args_schema", None), "model_fields", {}) or {}
                if "state" in fields and "state" not in args:
                    # Pass a plain dict to avoid TypedDict/Message objects causing serialization issues
                    args["state"] = dict(state)
                ret = tool_obj.invoke(args)
                # **** end: version 2 ****

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
    

    def _programmer_router(self, state: AgentState) -> str:
        ''' Router to determine the next node after the programmer node.

        Returns:
        str: The name of the next node to go to.
        '''
        last = state['conversation'][-1]
        if getattr(last, 'tool_calls', None):
            return self.programmer_tools_node[0]
        
        if state['query_index'] < len(state['retrieval_questions']):
            return self.programmer_retriever_node[0]
             
        return self.programmer_reflection_node[0]
    

    def _programmer_reflection_router(self, state: AgentState) -> str:
        ''' Router to determine the next node after the programmer reflection node.

        Returns:
            str: The name of the next node to go to.
        '''

        if state['programmer_reflection_count'] > (config.PROG_REF_CNT):
            return END
        
        last = state['conversation'][-1]
        
        if getattr(last, 'tool_calls', None):
            return self.programmer_reflection_tools_node[0]
        
        return self.programmer_node[0]

    def run(self, state: AgentState) -> None:
        events = self.graph.stream(state, {'recursion_limit': config.RECURSION_LIMIT})
        for event in events:
            # self.log.info('----- Event Start -----')
            # self.log.debug(event)
            # self.log.info('----- Event End -----')
            pass
        return
    
    pass # end of MainGraph
