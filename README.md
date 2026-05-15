# uGen — Agentic PoC Generation for Microarchitectural Attacks

uGen is an agentic framework that automatically generates, compiles, executes, and validates microarchitectural attack proof-of-concept (PoC) code using LLM agents, RAG-augmented retrieval, and iterative self-reflection.

---

## Supported Attack Vectors

- Spectre-v1
- Prime+Probe

## Evaluated Models

| Key | Provider | Model |
|-----|----------|-------|
| `gpt-4o` | OpenAI | GPT-4o |
| `claude-sonnet-4` | Anthropic | Claude Sonnet 4 |
| `Qwen3-Coder` | Together AI | Qwen3-Coder-480B |

---

## Prerequisites

- [Docker Engine](https://docs.docker.com/engine/install/) with the Compose plugin
- Linux host with `PERFMON` capability (required for hardware performance counters)
- API key for your chosen model provider (see below)

---

## API Keys

Only the key for your chosen provider is required. **`OPENAI_API_KEY` is not needed unless you are running GPT-4o** — Claude and Qwen3-Coder use a local embedding model (`BAAI/bge-small-en-v1.5`) that is pre-baked into the Docker image.

| Model | Required key |
|-------|-------------|
| `gpt-4o` | `OPENAI_API_KEY` |
| `claude-sonnet-4` | `ANTHROPIC_API_KEY` |
| `Qwen3-Coder` | `TOGETHER_API_KEY` |

---

## Setup

**1. Create your `.env` file**

```bash
cp .env.example .env
```

Open `.env` and fill in the key for your chosen provider. Set `UNAME` to your Linux username so that files created inside the container are owned by you. If your UID/GID is not `1000`, update those values accordingly.

```env
# Example for Claude
ANTHROPIC_API_KEY="sk-ant-..."
UNAME="your-linux-username"
UID=1000
GID=1000
```

**2. Create the workdir mount**

```bash
mkdir -p workdir
```

The container mounts `./workdir` as `~/workdir` inside the container. All generated source code, compiled binaries, and execution logs are written here.

---

## Running the Deployment Stage (S4)

> S4 is the final end-to-end deployment stage. Given a problem statement and a curated RAG knowledge base, it autonomously generates, compiles, executes, and validates a PoC binary — no manual intervention needed after launch.

### Step 1 — Configure `app/app.py`

Open `app/app.py` and set the two manual selection lines near the top of the `if __name__ == '__main__':` block:

```python
# ============ MANUAL PHASE SELECTION ============
SELECTED_PHASE = "Online"        # Keep as "Online" for S4
# ================================================

# ============ MANUAL MODEL SELECTION ============
SELECTED_MODEL_KEY = "claude-sonnet-4"   # "gpt-4o" | "claude-sonnet-4" | "Qwen3-Coder"
# ===============================================
```

Then set the attack parameters a few lines below:

```python
config.ATTACK_VECTORS        = 'Spectre-v1'   # "Spectre-v1" | "Prime-Probe"
config.TARGET_LANGUAGES      = 'C'
config.TARGET_FILE_EXTENSION = 'c'
```

Retrieval questions are selected **automatically** from `app/retrieval_queries.py` based on your model and attack vector.

### Step 2 — Build and run

```bash
./run_uGEN.sh
```

To run multiple times with a pause between runs:

```bash
./run_uGEN.sh --repeat 5 --sleep 60
```

The script calls `docker compose build` then `docker compose run --rm app` on each iteration.

> **Note:** The first build downloads and caches the local embedding model inside the Docker image. Subsequent builds reuse the cache and are fast.

### Step 3 — Collect output

```
workdir/<UUID>/PoC/<attack_vector>.<ext>   # Generated source code
workdir/<UUID>/PoC/<attack_vector>         # Compiled binary
workdir/logs/<UUID>.log                    # Full execution log
```

A final summary is printed to stdout when the run completes, reporting whether the PoC converged successfully or hit the time/iteration limit.

---

## How S4 Works

S4 runs a LangGraph state machine. The control flow is:

```
START → [Programmer]
          ├─ tool_calls?              → [ProgrammerTools]  → [Programmer]
          ├─ retrieval queries left?  → [Retriever]        → [Programmer]
          └─ otherwise               → [Reflection]
                ├─ tool_calls?        → [ReflectionTools]  → [Reflection]
                ├─ converged or limit → [FinalSummary]     → END
                └─ otherwise          → [Programmer]
```

**Programmer Agent** generates and iteratively refines the PoC code. 

**Retriever Node** answers the curated retrieval queries one by one from the Chroma vector store before each handoff to Reflection. 

**Reflection Agent** Proof-read the generated code and suggest possible fixing during failure condition.

**Convergence** is declared when the Reflection Agent emits `[STATUS: SUCCESS]`

**Termination** occurs at convergence, when the maximum `RECURSION_LIMIT` is exceeded, or when the wall-clock timeout (`TIMEOUT_SECONDS`) is reached — whichever comes first.

---

## Tuning (`app/app_config.py`)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `RECURSION_LIMIT` | `70` | LangGraph node execution cap |
| `LLM_NODE_DELAY_SECONDS` | `0` | Sleep before each LLM call; increase if hitting TPM rate limits |
---

## Four-Stage Pipeline

uGen is structured as a four-stage pipeline. **S4 (Deployment) is the final deployment stage** and can be run standalone using the pre-built RAG documents included in this repository.

| Stage | Graph file | Purpose | RAG | Evaluator |
|-------|-----------|---------|:---:|:---------:|
| S1 | `graph_offline_s1.py` | Identify knowledge gaps | — | Gap Profiler |
| S2 | `graph_offline_s2.py` | Generate RAG documents | ✓ | Synthesizer |
| S3 | `graph_offline_s3.py` | Validate and refine RAG docs | ✓ | Validator |
| **S4** | `graph_online_s4.py` | **Deploy — generate PoC** | ✓ | — |

Stages S1–S3 are offline preparation steps. Their outputs (the `workdir/RAG_Dir_*/` documents) are already included in this repository for all supported model/attack combinations, so you can **run S4 directly** without going through the offline stages.

---
