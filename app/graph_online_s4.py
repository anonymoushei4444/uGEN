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
import time
from uuid import uuid4
from typing import Any, Dict, List


import openai

# Langchain imports
from langchain_core.messages import ToolMessage, HumanMessage # type: ignore
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
from tools.compiler import compile_C, compile_CPP, compile_rust
from tools.measureHPC import measure_HPC
from tools.executor import execute_binaries
from tools.code_reader_tools import source_code_reader, read_problem_statement
from tools.content_storage import store_content, save_missing_metrics
from tools.evaluator_tool import evaluation_metrics_reader
from tools.extract_system_info import collect_system_info
from tools.cache_threshold import measure_cache_threshold


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
    final_summary_node: tuple[str, callable]




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
        
        self.final_summary_node = (
            "FinalSummaryNode",
            self._final_summary_node_action
        )

        self._timeout_exceeded = False
        self.graph = self._create_graph()
        pass

    def _is_timed_out(self) -> bool:
        elapsed = time.time() - getattr(self, '_execution_start_time', time.time())
        if elapsed >= config.TIMEOUT_SECONDS:
            self._timeout_exceeded = True
            return True
        return False

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
        prog_tools   = [read_problem_statement, collect_system_info, compile_C, compile_CPP, compile_rust, measure_cache_threshold]
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
        prog_ref_tools   = [compile_C, compile_CPP, compile_rust, measure_HPC, execute_binaries, measure_cache_threshold]
        return ProgrammerReflectionAgent(
            llm     = self.llm,
            name    = prog_ref_name,
            tools   = prog_ref_tools,
            version = prog_ref_version,
            prompt_phase=self.prompt_phase
            )



    def _detect_convergence(self, response: AIMessage) -> bool:
        """
        Detect if ProgrammerReflectionAgent has truly converged using multi-layer validation.
        Returns True only if convergence is certain, defaults to False on ambiguous cases.
        
        Layer 1: Structured token detection - [STATUS: SUCCESS]
        Layer 2: Tool call validation - no tool_calls means LLM concluded action
        Layer 3: Phrase + position validation - success phrase at end of response
        Layer 4: Semantic context validation - positive context preceding success phrase
        """
        if not response or not response.content:
            return False
        
        content = response.content.strip()
        
        # ============ LAYER 1: Structured Token (Strongest Signal) ============
        # If LLM explicitly ends with [STATUS: SUCCESS], that's definitive convergence
        if "[STATUS: SUCCESS]" in content:
            self.log.info("✓ Convergence detected via [STATUS: SUCCESS] token")
            return True
        
        # ============ LAYER 2: Tool Call Validation (Critical Check) ============
        # If there are tool_calls, LLM is continuing work → NOT converged
        if getattr(response, 'tool_calls', None):
            self.log.debug("Response has tool_calls → LLM not converged (continuing work)")
            return False
        
        # ============ LAYER 3: Phrase & Position Validation ============
        success_phrase = "THE PoC CODE IS CORRECT AND SATISFACTORY"
        if success_phrase not in content:
            # Phrase not found, not converged
            return False
        
        # Check phrase position: should be in final ~20% of response
        # (to avoid cases where it's just discussing the prompt instruction)
        phrase_index = content.find(success_phrase)
        response_length = len(content)
        phrase_relative_pos = phrase_index / response_length if response_length > 0 else 0
        
        if phrase_relative_pos < 0.75:
            # Phrase is too early in response (likely just discussing instructions)
            self.log.debug(f"Success phrase found at {phrase_relative_pos:.1%} position → too early, likely instructional")
            return False
        
        # ============ LAYER 4: Semantic Context Validation ============
        # Check preceding text (500 chars before phrase) for positive/negative indicators
        context_start = max(0, phrase_index - 500)
        preceding_text = content[context_start:phrase_index].lower()
        
        positive_indicators = [
            "compiles successfully", "compiles without error", "no errors",
            "executes without errors", "execution is successful", "output is correct",
            "all tests passed", "all steps completed", "binary runs successfully",
            "passes all", "correctly leak", "successful leak"
        ]
        has_positive = any(indicator in preceding_text for indicator in positive_indicators)
        
        negative_indicators = ["not correct", "fails", "error", "issue", "problem", "but", "however"]
        has_negative = any(neg in preceding_text for neg in negative_indicators)
        
        if has_negative and not has_positive:
            self.log.debug("Success phrase preceded by negative context → not converged")
            return False
        
        # All layers passed → convergence achieved
        self.log.info("✓ Convergence detected: PoC passes all benchmark steps")
        return True

    def _create_graph(self) -> Any:
        workflow = StateGraph(AgentState)

        workflow.add_node(*self.programmer_node)
        workflow.add_node(*self.programmer_tools_node)
        workflow.add_node(*self.programmer_reflection_tools_node)
        workflow.add_node(*self.programmer_reflection_node)    
        workflow.add_node(*self.programmer_retriever_node)
        workflow.add_node(*self.final_summary_node)

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
      
        # Reflection -> Reflection Tools or, Programmer Agent, or Final Summary (with convergence check)
        workflow.add_conditional_edges(
            self.programmer_reflection_node[0],         # source
            self._programmer_reflection_router          # conditional sink
        )
        
        # Final Summary -> END (always ends after summary)
        workflow.add_edge(
            self.final_summary_node[0],                 # source
            END                                         # sink
        )

        return workflow.compile()
    

    def _truncate_conversation(self, state: AgentState, keep_head: int = 4, keep_tail: int = 12) -> bool:
        """Remove middle messages from the conversation to reduce token count.

        Keeps the first `keep_head` messages (problem-statement tool results / system info)
        and the last `keep_tail` messages (most recent context).  Any leading ToolMessages
        in the tail slice are skipped forward to avoid orphaned tool results.

        Returns True if truncation was performed, False if the conversation is already small.
        """
        conv = state['conversation']
        if len(conv) <= keep_head + keep_tail:
            return False

        head = conv[:keep_head]
        tail = conv[-keep_tail:]

        # Never start the tail on an orphaned ToolMessage (its parent AIMessage was cut).
        while tail and isinstance(tail[0], ToolMessage):
            tail = tail[1:]

        if not tail:
            return False

        removed = len(conv) - keep_head - len(tail)
        self.log.warning(
            f"Conversation truncated: removed {removed} middle messages "
            f"(kept first {keep_head} + last {len(tail)}; total {keep_head + len(tail)})"
        )
        state['conversation'] = head + tail
        return True

    def _invoke_with_retry(self, agent, state: AgentState) -> AIMessage:
        """Invoke an agent with automatic recovery from OpenAI 429 errors.

        - 'tokens' type (single request exceeds TPM budget): truncate the conversation
          and retry immediately — sleeping is useless when the request itself is over-size.
        - Any other 429 (requests-per-minute throttle): sleep 60 s and retry.
        """
        while True:
            try:
                return agent.invoke(state)
            except openai.RateLimitError as e:
                err_body = getattr(e, 'body', None) or {}
                err_type = err_body.get('error', {}).get('type', '')
                # Fallback: check error string for providers that don't set body correctly
                is_token_overflow = (err_type == 'tokens') or ('tokens per min' in str(e).lower())
                if is_token_overflow:
                    self.log.warning(f"Request too large: {e}. Truncating conversation and retrying...")
                    if not self._truncate_conversation(state):
                        self.log.error("Cannot truncate further — conversation already minimal. Re-raising.")
                        raise
                else:
                    self.log.warning(f"Rate limit hit: {e}. Sleeping 60s before retry...")
                    time.sleep(60)

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


        if config.LLM_NODE_DELAY_SECONDS > 0:
            self.log.debug(f"Sleeping {config.LLM_NODE_DELAY_SECONDS}s before LLM call (TPM throttle)")
            time.sleep(config.LLM_NODE_DELAY_SECONDS)

        result: AIMessage = self._invoke_with_retry(self.programmer_agent, state)
        result.content = result.content.strip()

        state['programmer_count'] += 1
        state['total_nodes_executed'] = state.get('total_nodes_executed', 0) + 1  
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
        state['total_nodes_executed'] = state.get('total_nodes_executed', 0) + 1
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
        state['total_nodes_executed'] = state.get('total_nodes_executed', 0) + 1

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

        # Retrieval responses are injected as HumanMessage (not AIMessage) so the LLM
        # sees them as externally delivered information, not its own prior output.
        # Using AIMessage here caused the LLM to treat retrieval content as self-generated
        # text and fabricate additional retrieval responses in subsequent turns.
        result = HumanMessage(
          content=f"""[Retriever Node] Retrieved information for query: \"{query}\"\n{''.join(content)}"""
        )
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

        last_msg = state['conversation'][-1] if state['conversation'] else None
        guard_rail_path = False

        # Guard-rail path: the router bypassed tool execution and routed directly here,
        # leaving an AIMessage with unanswered tool_calls in the conversation.
        # The LLM API requires every tool_call_id to have a matching ToolMessage response,
        # so inject synthetic ToolMessages before invoking the Reflection agent.
        if last_msg is not None and isinstance(last_msg, AIMessage):
            pending_calls = getattr(last_msg, 'tool_calls', None) or []
            if pending_calls:
                for tc in pending_calls:
                    state['conversation'].append(ToolMessage(
                        name=tc['name'],
                        tool_call_id=tc.get('id', ''),
                        content=(
                            "Compilation already verified as successful in the previous step. "
                            "No further tool execution needed. "
                            "Routing to ProgrammerReflectionAgent for code review."
                        )
                    ))
                self.log.info(
                    f"Injected {len(pending_calls)} synthetic ToolMessage(s) for unanswered "
                    "tool_calls (guard-rail bypass path)."
                )
                guard_rail_path = True

        # Inject a fresh-analysis signal whenever the Programmer has handed off updated code:
        # - Normal path: last message is an AIMessage with no tool_calls.
        # - Guard-rail path: synthetic ToolMessages were just injected above.
        # The signal tells the Reflection agent that all previous tool outputs are stale.
        last_msg_now = state['conversation'][-1] if state['conversation'] else None
        is_programmer_handoff = guard_rail_path or (
            last_msg_now is not None
            and isinstance(last_msg_now, AIMessage)
            and not getattr(last_msg_now, 'tool_calls', None)
        )
        if is_programmer_handoff:
            state['conversation'].append(HumanMessage(content=(
                "[FRESH ANALYSIS REQUIRED] The ProgrammerAgent has just submitted UPDATED source code. "
                "All previous tool results in this conversation (execute_binaries output, measure_HPC output, etc.) "
                "are from an OLDER version of the code and MUST NOT be reused. "
                "You MUST perform a completely fresh analysis: invoke execute_binaries in Step 2 to get "
                "current execution results, and re-invoke any other tools needed for subsequent steps."
            )))
            self.log.info("Injected fresh-analysis signal into conversation (Programmer handoff detected).")

        if config.LLM_NODE_DELAY_SECONDS > 0:
            self.log.debug(f"Sleeping {config.LLM_NODE_DELAY_SECONDS}s before LLM call (TPM throttle)")
            time.sleep(config.LLM_NODE_DELAY_SECONDS)

        result: AIMessage = self._invoke_with_retry(self.programmer_reflection_agent, state)
        result.content = result.content.strip()

        state['programmer_reflection_count'] += 1
        state['total_nodes_executed'] = state.get('total_nodes_executed', 0) + 1
        state['conversation'].append(result)  
        self.log.info(f"Programmer Reflection Agent Response:\n{result.content}")
        # self.log.info(f"Programmer Reflection Agent Tool Calls:\n{result.tool_calls}")
        
        # Detect convergence using multi-layer validation
        if self._detect_convergence(result):
            state['convergence_achieved'] = True
            self.log.info("Setting convergence_achieved = True")
        
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
        state['total_nodes_executed'] = state.get('total_nodes_executed', 0) + 1
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
        # PRIORITY 0: Timeout exceeded → terminate immediately
        if self._is_timed_out():
            elapsed = time.time() - self._execution_start_time
            self.log.warning(f"Timeout ({config.TIMEOUT_SECONDS}s) exceeded ({elapsed:.0f}s elapsed) in Programmer router — routing to FinalSummaryNode.")
            return self.final_summary_node[0]

        last = state['conversation'][-1]
        if getattr(last, 'tool_calls', None):
            # Guard: detect a stuck compile loop.
            # Pattern: Programmer calls compile_X → compile succeeds →
            # Programmer calls compile_X again (typically because it wanted to
            # "execute" next but only has compile in its tool list).
            # When the immediately preceding message is a ToolMessage for the
            # same compile tool that returned successfully, the Programmer has
            # nothing new to compile — route to Reflection to break the loop.
            current_tool_names = {tc['name'] for tc in last.tool_calls}
            conversation = state['conversation']
            if len(conversation) >= 2:
                prev_msg = conversation[-2]
                prev_content = getattr(prev_msg, 'content', '')
                prev_tool_name = getattr(prev_msg, 'name', None)
                prev_clean = not any(
                    ind in prev_content.lower()
                    for ind in ['error', 'failed', 'exception', 'traceback', 'warning:']
                )
                if (isinstance(prev_msg, ToolMessage) and
                        prev_tool_name in current_tool_names and
                        prev_clean):
                    self.log.warning(
                        f"Programmer re-invoking '{prev_tool_name}' after a clean result "
                        "— routing to Reflection to break the loop."
                    )
                    return self.programmer_reflection_node[0]

            return self.programmer_tools_node[0]

        if state['query_index'] < len(state['retrieval_questions']):
            return self.programmer_retriever_node[0]

        return self.programmer_reflection_node[0]
    

    def _programmer_reflection_router(self, state: AgentState) -> str:
        ''' Router to determine the next node after the programmer reflection node.
        
        Priority:
        1. If convergence_achieved → go to final summary (exit early)
        2. If tool_calls present → execute reflection tools
        3. If PROG_REF_CNT exceeded → go to final summary (exhausted without convergence)
        4. Otherwise → back to programmer for another iteration

        Returns:
            str: The name of the next node to go to.
        '''
        
        # PRIORITY 0: Timeout exceeded → terminate immediately
        if self._is_timed_out():
            elapsed = time.time() - self._execution_start_time
            self.log.warning(f"Timeout ({config.TIMEOUT_SECONDS}s) exceeded ({elapsed:.0f}s elapsed) in Reflection router — routing to FinalSummaryNode.")
            return self.final_summary_node[0]

        # PRIORITY 1: Convergence achieved → early exit to final summary
        if state.get('convergence_achieved', False):
            self.log.info("Convergence achieved! Routing to final summary node.")
            return self.final_summary_node[0]
        
        # # PRIORITY 3: Max reflection iterations reached → exit to final summary
        # if state['programmer_reflection_count'] > config.PROG_REF_CNT:
        #     self.log.info(f"Max PROG_REF_CNT ({config.PROG_REF_CNT}) reached. Routing to final summary node.")
        #     return self.final_summary_node[0]
        
        # PRIORITY 2: Tool calls present → execute them
        last = state['conversation'][-1]
        if getattr(last, 'tool_calls', None):
            return self.programmer_reflection_tools_node[0]
        
        # DEFAULT: Continue iteration, back to programmer
        return self.programmer_node[0]
    
    def _final_summary_node_action(self, state: AgentState, increment_counter: bool = True) -> AgentState:
        ''' Action for the final summary node.
        Generates a comprehensive summary of the execution and determines success/incomplete status.

        Args:
            state (AgentState): The final state of the agent with all execution history.
            increment_counter (bool): Whether to increment total_nodes_executed counter. Default True.
                Set to False when calling outside the graph stream (e.g., as fallback handler).
        Returns:
            AgentState: The updated state with final_summary populated.
        '''
        self.log.info("##### Final Summary Node Start #####")
        if increment_counter:
            state['total_nodes_executed'] = state.get('total_nodes_executed', 0) + 1

        # Compute execution time
        elapsed_secs = time.time() - getattr(self, '_execution_start_time', time.time())
        h = int(elapsed_secs // 3600)
        m = int((elapsed_secs % 3600) // 60)
        s = elapsed_secs % 60
        execution_time_str = f"{h:02d}:{m:02d}:{s:05.2f}  ({elapsed_secs:.1f}s total)"

        # Count tokens from all AIMessages in conversation
        total_input_tokens = 0
        total_output_tokens = 0
        for msg in state.get('conversation', []):
            meta = getattr(msg, 'usage_metadata', None)
            if meta:
                total_input_tokens  += meta.get('input_tokens', 0)
                total_output_tokens += meta.get('output_tokens', 0)
        total_tokens = total_input_tokens + total_output_tokens
        token_str = (
            f"{total_tokens:,}  (input: {total_input_tokens:,} / output: {total_output_tokens:,})"
            if total_tokens > 0 else "N/A (usage metadata unavailable)"
        )

        # Extract key metrics from state
        attack_vector = state.get('attack_vector', 'Unknown')
        target_language = state.get('target_language', 'Unknown')
        selected_model = state.get('selected_model_key', 'Unknown')
        programmer_iterations = state.get('programmer_count', 0)
        reflection_iterations = state.get('programmer_reflection_count', 0)
        total_nodes_executed = state.get('total_nodes_executed', 0)
        convergence_achieved = state.get('convergence_achieved', False)

        # Build summary message
        summary_lines = [
            "\n" + "=" * 80,
            "EXECUTION SUMMARY",
            "=" * 80,
            f"UUID:                 {config.UUID}",
            f"Phase:                {self.prompt_phase}",
            f"Attack Vector:        {attack_vector}",
            f"Target Language:      {target_language}",
            f"Model Used:           {selected_model}",
            f"Programmer Iterations:  {programmer_iterations}",
            f"Reflection Iterations:  {reflection_iterations}",
            f"Total Nodes Executed:   {total_nodes_executed} / {config.RECURSION_LIMIT}",
            # f"Max Reflection Count:   {config.PROG_REF_CNT}",
            f"Execution Time:       {execution_time_str}",
            f"Tokens Generated:     {token_str}",
            "-" * 80,
        ]
        
        if convergence_achieved:
            summary_lines.extend([
                "STATUS:               ✓ SUCCESS",
                "RESULT:               PoC generation converged successfully.",
                "DESCRIPTION:          The Reflection Agent confirmed that the generated",
                "                      proof-of-concept code passes all benchmark steps:",
                "                      - Compiles without errors",
                "                      - Executes without runtime errors",
                "                      - Produces correct/expected output",
                "-" * 80,
            ])
        elif self._timeout_exceeded:
            summary_lines.extend([
                "STATUS:               ✗ TIMEOUT",
                f"RESULT:               Framework exceeded the {config.TIMEOUT_SECONDS}s time limit ({config.TIMEOUT_SECONDS // 60} min) without convergence.",
                "DESCRIPTION:          The graph was forcefully terminated by the timeout guard.",
                "                      The agents may have entered a repetitive loop. The",
                "                      generated code may require further refinement.",
                "-" * 80,
            ])
        else:
            summary_lines.extend([
                "STATUS:               ✗ INCOMPLETE",
                "RESULT:               PoC generation did not converge within limits.",
                f"DESCRIPTION:          Maximum reflection iterations ({config.PROG_REF_CNT})",
                "                      or recursion limit was reached before the Reflection",
                "                      Agent confirmed PoC correctness. The generated code may",
                "                      require further refinement.",
                "-" * 80,
            ])
        
        summary_lines.extend([
            "EXECUTION COMPLETED",
            "=" * 80 + "\n",
        ])
        
        summary_message = "\n".join(summary_lines)
        state['final_summary'] = summary_message
        
        # Log summary to both console and file
        self.log.info(summary_message)
        
        self.log.info("##### Final Summary Node End #####")
        return state

    def run(self, state: AgentState) -> None:
        self._execution_start_time = time.time()
        try:
            # Stream the graph execution. Each node updates state['total_nodes_executed'] directly.
            events = self.graph.stream(state, {'recursion_limit': config.RECURSION_LIMIT})
            for event in events:
                # LangGraph emits {node_name: <state_dict>} where the value is the
                # full state returned by the node — update our local copy each step.
                if isinstance(event, dict):
                    for node_name, node_output in event.items():
                        if isinstance(node_output, dict):
                            state.update(node_output)
                            # NOTE: total_nodes_executed is now incremented directly by each node action

                # Safety net: catches a single long-running node that blocks the routers.
                elapsed = time.time() - self._execution_start_time
                if elapsed >= config.TIMEOUT_SECONDS and not self._timeout_exceeded:
                    self._timeout_exceeded = True
                    self.log.warning(f"Timeout safety net triggered after {elapsed:.0f}s — breaking stream.")
                    break
        except Exception as e:
            # Handle recursion limit or other stream errors
            self.log.warning(f"Graph stream terminated: {str(e)}")
            # Mark that we hit the limit without convergence
            if 'final_summary' not in state or not state['final_summary']:
                state['convergence_achieved'] = state.get('convergence_achieved', False)
                # Generate final summary if not already done
                state = self._final_summary_node_action(state, increment_counter=False)
        
        # Ensure final summary is always generated, even if stream completes normally
        # but final summary node wasn't reached due to recursion limit
        if 'final_summary' not in state or not state['final_summary']:
            self.log.info("Final summary not generated during stream, generating now...")
            state = self._final_summary_node_action(state, increment_counter=False)
        
        return
    
    pass # end of MainGraph
