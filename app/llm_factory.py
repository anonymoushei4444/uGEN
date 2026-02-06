# llm_factory.py
import os
from langchain_openai import ChatOpenAI         # type: ignore
# from langchain_community.chat_models import ChatTogether     # type: ignore

def build_chat_llm(name: str, registry: dict):
    spec = registry[name]
    provider = spec["provider"].lower()
    model = spec["model"]
    args = spec.get("args", {})
    temperature = args.get("temperature", 0)
    max_tokens = args.get("max_tokens", None)
    

    if provider == "openai":
        api_key  = args.get("api_key")  or os.getenv("OPENAI_API_KEY")
        base_url = args.get("base_url") or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

    elif provider == "together":
        api_key  = args.get("api_key")  or os.getenv("TOGETHER_API_KEY")
        base_url = args.get("base_url") or os.getenv("TOGETHER_BASE_URL", "https://api.together.xyz/v1")

    elif provider == "ionos":
        api_key  = args.get("api_key")  or os.getenv("IONOS_API_KEY")
        base_url = args.get("base_url") or os.getenv("IONOS_BASE_URL", "https://api.ionos.com/v1")

    elif provider == "ollama":
        # No real key required; placeholder is fine. Base URL must point to Ollama's /v1 endpoint.
        api_key  = args.get("api_key")  or os.getenv("OLLAMA_API_KEY", "ollama")
        base_url = args.get("base_url") or os.getenv("OLLAMA_OPENAI_BASE_URL", "http://host.docker.internal:11434/v1")

    elif provider == "anthropic":
        api_key  = args.get("api_key")  or os.getenv("ANTHROPIC_API_KEY")
        base_url = args.get("base_url") or os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1")

    else:
        raise RuntimeError(f"Unknown provider '{provider}' for model '{name}'.")
    
    if not api_key:
        raise RuntimeError(f"Missing API key for provider '{provider}'")
    
    return ChatOpenAI(model=model, api_key=api_key, base_url=base_url, temperature=temperature, max_tokens=max_tokens)

