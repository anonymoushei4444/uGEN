# Built-in imports
import copy
import json

# Langchain imports
from langchain_core.prompts import ChatPromptTemplate # type: ignore
from langchain_core.messages.ai import AIMessage # type: ignore
from langchain_core.runnables.base import RunnableSequence # type: ignore
from langchain_core.language_models.chat_models import BaseChatModel # type: ignore


# Local imports
from app_config import get_logger
from agents.AgentState import AgentState
from agents.prompts.PromptTemplateLoader import PromptTemplateLoader

class BaseAgent():
    '''
    Langchain Agent responsible for generating PoC code for a given task.
    '''

    def __init__(self, name: str, llm: BaseChatModel, tools: list = None, prompt_phase: str = None, version: str = "v1"):
        """Initializes the BaseAgent.

        Args:
            llm (BaseChatModel): The Chat Model (LLM) to use for the agent, if not set an LLM is instantiated here. Defaults to None.
            tools (list, optional): List of tools to bind to the LLM. Defaults to None.
        """
        self.log = get_logger(name)
        self.name = name
        self.version = version
        self.llm = llm
        self.tools = tools
        self.prompt_phase = prompt_phase


        # [NEW] Log LLM class so we know whether we’re on ChatOpenAI vs Ollama, etc.
        # self.log.info(f"[{self.name}] LLM impl: {type(self.llm)}")

        # Bind tools (latest LangChain) so model can emit tool_calls
        if self.tools:
            # tool_choice="auto" ensures the model can choose to call tools when appropriate
            self.llm = self.llm.bind_tools(self.tools, tool_choice="auto")
            pass

        # print(f"[DEBUG] {self.name} (EvaluatorAgent): LLM type = {type(self.llm)}")
        # if self.tools:
        #     print(f"[DEBUG] {self.name} (EvaluatorAgent): Number of tools bound = {len(self.tools)}")

        
        self.agent = self._get_agent()
        # self.agent: RunnableSequence = self._get_agent() # For Llama-based models
        pass

    
    def _get_agent(self) -> RunnableSequence:
        """Creates the RunnableSequence (LLMChain) for the BaseAgent.

        Returns:
            RunnableSequence: The object used for running invocations against the LLM in the currently configured LLMChain.
        """      
        template = PromptTemplateLoader.get_template(
                                        class_name=self.__class__.__name__, 
                                        version=self.version,
                                        prompt_phase=self.prompt_phase)
        
        prompt = ChatPromptTemplate.from_messages(template, template_format="jinja2")
        return prompt | self.llm

    def invoke(self, input: AgentState) -> AIMessage:
        """Wrapper around the RunnableSequence's (agent's) invoke method.

        Args:
            input (AgentState):  The input object for the agent
                
        Returns:
            AIMessage: The response from the agent
        """  
        # Defensive copy to avoid in-place mutations by the chain
        safe_input = copy.deepcopy(input)
        response = self.agent.invoke(safe_input)
        # print(f"[DEBUG] {self.name}: Invoked agent with state keys: {list(safe_input.keys())}")
        # print(f"[DEBUG] {self.name}: Model response = {response}")
        return response
        # return self.agent.invoke(safe_input)
    
    pass # end of BaseAgent
