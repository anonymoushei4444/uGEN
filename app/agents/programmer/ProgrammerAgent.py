# Built-in imports
import copy

# Langchain imports
from langchain_core.prompts import ChatPromptTemplate # type: ignore
from langchain_core.runnables.base import RunnableSequence # type: ignore

# Local imports
from agents.BaseAgent import BaseAgent
from agents.prompts.PromptTemplateLoader import PromptTemplateLoader

class ProgrammerAgent(BaseAgent):
    '''
    Langchain Agent responsible for generating PoC code for a given task.
    '''
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
        agent = (
            {  # how to get the variable values for the prompt template
                "attack_vector":            lambda state: state["attack_vector"],
                "target_language":          lambda state: state["target_language"],
                "target_file_extension":    lambda state: state["target_file_extension"],
                "retrieval_questions":      lambda state: state["retrieval_questions"],
                "retrieval_responses":      lambda state: state["retrieval_responses"],
                "conversation":             lambda state: state["conversation"],
            }
            | prompt   # the prompt template from the yaml file
            | self.llm # the LLM with tools
        )
        return agent
    
    pass # end of PoCProgrammerAgent
