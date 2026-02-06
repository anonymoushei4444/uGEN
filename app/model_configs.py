# model_configs.py
import os

models = {
    "gpt-4o": {
        "provider": "openai",
        "model": "gpt-4o",
        "args": {
            "temperature": 0,
            "api_key": os.getenv("OPENAI_API_KEY"),
            "base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        }
    },
    "gpt-5": {
        "provider": "openai",
        "model": "gpt-5",
        "args": {
            "temperature": 0,
            "api_key": os.getenv("OPENAI_API_KEY"),
            "base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        }
    },
    "llama-4-maverick": {
        "provider": "together",
        "model": "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",  # use your exact Together model id
        "args": {
            "temperature": 0,
            "api_key": os.getenv("TOGETHER_API_KEY"),
            "base_url": os.getenv("TOGETHER_BASE_URL", "https://api.together.xyz/v1"),
        }
    },
    "llama-4-scout": {
        "provider": "together",
        "model": "meta-llama/Llama-4-Scout-17B-16E-Instruct",  # use your exact Together model id
        "args": {
            "temperature": 0,
            "api_key": os.getenv("TOGETHER_API_KEY"),
            "base_url": os.getenv("TOGETHER_BASE_URL", "https://api.together.xyz/v1"),
        }
    },
    "deepseek-v3": {
        "provider": "together",
        "model": "deepseek-ai/DeepSeek-V3",  # use your exact Together model id
        "args": {
            "temperature": 0,
            "api_key": os.getenv("TOGETHER_API_KEY"),
            "base_url": os.getenv("TOGETHER_BASE_URL", "https://api.together.xyz/v1"),
        }
    },
    "llama3.3-70b-ionos": {
        "provider": "ionos",
        "model": "meta-llama/Llama-3.3-70B-Instruct",  
        "args": {
            "temperature": 0,
            "api_key": os.getenv("IONOS_API_KEY"),
            "base_url": os.getenv("IONOS_BASE_URL", "https://api.ionos.com/v1"),
        }
    },
    "llama3.2-ollama": {
        "provider": "ollama",
        "model": "llama3.2",   # must match the model you pulled with `ollama pull llama3.2`
        "args": {
            "temperature": 0,
            # Use Ollama's OpenAI-compatible API. When running inside Docker,
            # prefer host.docker.internal to reach host's 11434 port.
            "base_url": os.getenv("OLLAMA_OPENAI_BASE_URL", "http://host.docker.internal:11434/v1"),
            # ChatOpenAI requires an api_key; Ollama ignores it. Use a harmless placeholder.
            "api_key": os.getenv("OLLAMA_API_KEY", "ollama")
        }
    },
    "claude-sonnet-4": {
        "provider": "anthropic",
        "model": "claude-sonnet-4-20250514",
        "args": {
            "temperature": 0,
            "api_key": os.getenv("ANTHROPIC_API_KEY"),
            "base_url": os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1"),
        }
    },
    "Qwen3-Coder": {
        "provider": "together",
        "model": "Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8",  # use your exact Together model id
        "args": {
            "temperature": 0,
            "api_key": os.getenv("TOGETHER_API_KEY"),
            "base_url": os.getenv("TOGETHER_BASE_URL", "https://api.together.xyz/v1"),
            "max_tokens": 32000,
        }
    }
}
