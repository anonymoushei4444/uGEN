# Built-in imports
import os
import re
import yaml
import logging
from typing import List, Union
# LangChain imports
from langchain_core.prompts import MessagesPlaceholder  # type: ignore

log = logging.getLogger(__name__)

class PromptTemplateLoader:
    '''Class for retrieving prompt templates based on agent class names and versions.
    '''
    
    SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))


    @staticmethod
    def _to_messages(entries: List[dict]) -> List[Union[tuple, MessagesPlaceholder]]:
        """Convert YAML prompt entries to ChatPromptTemplate.from_messages-compatible list."""
        out: List[Union[tuple, MessagesPlaceholder]] = []
        for i, item in enumerate(entries):
            t = (item.get("type") or "").strip().lower()
            if t == "placeholder":
                # Accept "{conversation}" or "conversation"
                raw = item.get("prompt", "") or item.get("name", "")
                m = re.match(r"^\{?([A-Za-z_][A-Za-z0-9_]*)\}?$", str(raw).strip())
                var = m.group(1) if m else "conversation"
                out.append(MessagesPlaceholder(variable_name=var))
            elif t in ("system", "human", "ai"):
                prompt = item.get("prompt", "")
                # Ensure a string (empty string is okay)
                if prompt is None:
                    prompt = ""
                out.append((t, str(prompt)))
            else:
                # Unknown type -> log and skip
                log.warning(f"Unknown prompt entry type '{t}' at index {i}; skipping.")
        return out

    @staticmethod
    def get_template(class_name: str, version: str = "v1", prompt_phase: str = None) -> List[Union[tuple, MessagesPlaceholder]]:
        '''Retrieve and return the prompt template for a given class and version.

        Args:
            class_name (str): The class name of the agent whose template is required.
            version (str): The version of the template to retrieve (default is "v1").

        Raises:
            FileNotFoundError: If the template file does not exist.
            KeyError: If the specified version is not found in the template file.
            ValueError: If any other issues occur while fetching the template.

        Returns:
            List[tuple|MessagesPlaceholder]: Items consumable by ChatPromptTemplate.from_messages.
        '''
        # Use phase directory if provided
        if prompt_phase:
            prompt_dir = os.path.join(PromptTemplateLoader.SCRIPT_DIR, prompt_phase)
        else:
            prompt_dir = PromptTemplateLoader.SCRIPT_DIR
        
        promptname = f"{class_name}Prompt.yaml"
        filename = os.path.join(prompt_dir, promptname)
        
        if not os.path.exists(filename):
            raise FileNotFoundError(f"Prompt file not found: {filename}")

        with open(filename, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        if version not in data:
            raise KeyError(f"Version '{version}' not found in {filename}. Available: {list(data.keys())}")

        entries = data.get(version) or []
        if not isinstance(entries, list):
            raise ValueError(f"Template version '{version}' in {filename} must be a list.")

        messages = PromptTemplateLoader._to_messages(entries)
        if not messages:
            # Provide a minimal default system message to avoid runtime errors
            log.warning(f"No messages found in {filename} for version '{version}'. Using a default system message.")
            messages = [("system", f"{class_name} is running without a configured prompt.")]

        # print(f"[DEBUG] PromptTemplateLoader: Loading prompt for class='{class_name}', version='{version}', prompt_phase='{prompt_phase}'")
        # print(f"[DEBUG] PromptTemplateLoader: Template file='{filename}'")
        # print(f"[DEBUG] PromptTemplateLoader: Loaded entries (raw): {entries}")
        # print(f"[DEBUG] PromptTemplateLoader: Loaded messages (final): {messages}")

        return messages
    
    pass # end of PromptTemplates
