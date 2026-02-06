# uGEN
uGen: An Agentic Framework for Generating Microarchitectural Attack PoCs

## Roadmap

Tools:
- [x] C/C++ compiler
- [x] Rust compiler
- [x] Binary executor
- [x] Performance counter reader
- [x] Cache architecture reader
- [x] RAG Retreiver Tool
- [x] File r/w Tools

LLM providers:
- [x] [OpenAI](https://python.langchain.com/v0.2/docs/integrations/platforms/openai/)
- [x] [Anthropic](https://python.langchain.com/v0.2/docs/integrations/platforms/anthropic/)
- [x] [GPT4o](https://python.langchain.com/v0.2/docs/integrations/providers/)
- [x] [Qwen3-Coder](https://docs.together.ai/docs/integrations#langchain)

Chat models:
- OpenAI
    - [x] GPT-4o
- Anthropic
    - [x] Claude-4-Sonnet
- Qwen
    - [x] Qwen3-Coder

## Setup

The LLM framework is containerized to ease dependency management and code execution. Make sure that you have [Docker Engine](https://docs.docker.com/engine/install/) including the Docker Compose plugin installed on your system.

Create a `.env` file in the same directory as the `docker-compose.yml` file with the following content:

```env
OPENAI_API_KEY="..."
TOGETHER_API_KEY="..."
ANTHROPIC_API_KEY="..."
LANGCHAIN_API_KEY="..."
LANGCHAIN_PROJECT="..."
UNAME="anonymous"
```

The `LANDCHAIN_*` variables are optional and only required if you want to use [LangSmith](https://smith.langchain.com) to track the execution of your code. The `OPENAI_API_KEY` variable is required if you want to use the OpenAI API to generate code. The `UNAME`, `UID`, and `GID` variables are required to ensure that the files created in the container are owned by the correct user and group.

Fill in the missing parts (`"..."`) with the appropriate values. Also, if your user and group ID is not `1000`, change the `UID` and `GID` values accordingly. The files created in the container will be owned by the user with the specified UID and GID.

Create a folder called `workdir` in the same directory as the `docker-compose.yml` file. This folder will be mounted in the container as `~/workdir` and contain the LLM-generated source code files and binaries.

After these setup steps, you can run the LLM toolchain by executing the following command:

```shell
$ cd uGEN
$ ./run_uGEN --repeat <OPTIONAL> --sleep <OPTIONAL (SECOND)>
```

This command will (re-)build the container image and start the container. If you make changes to the framework, you can rebuild the container by running the same command again.


## Concepts

An *agent* is an LLM instance associated with a prompt template and a list of accessible tools.
An *agent input* is used to fill in the agent's prompt template.
A *tool* is a Python function that can be called by an agent to interact with the system it is running on.


## Deployment Stage: S4

The architecture consists of multiple LLM agents that play different roles and interact with each other and the system.

The current implementation of the framework consists of the following agents:
1. **Programmer Agent:** The agent is tasked with generating a PoC for a given attack vector and programming language. The programmer agent forwards the generated code to the programmer agent tools to compile the code.
2. **Programmer Agent Tools:** The tools provide the ability for the programmer agent to interact with the system it is running on. The output of the tools is passed on to the programmer agent.
3. **Programmer Reflection Agent:** The agent is tasked with analyzing the output of the programmer agent and its tools and generating feedback. The feedback is fed back to the programmer agent to improve the generated code.
4. **Reflector Agent Tools:** The tools provide the ability for the reflector agent to interact with the system it is running on. The output of the tools is passed on to the reflection agent.


## Implementation

The framework is implemented in Python. It uses [LangChain](https://python.langchain.com/v0.2/docs/introduction/) to access LLM agents and model their interaction as a graph where the nodes represent agents and the tools that they have access to and the edges represent the allowed communication channels. The graph is modeled with [LangGraph](https://langchain-ai.github.io/langgraph/).

The source code is located in the `app` folder, which currently has the following structure:

```bash
app/ # Root folder for the LLM framework
├── agents/ # Contains the agents
│   ├── programmer/ # Contains all agents
│   ├── prompts/ # Contains all prompts
│   ├── BaseAgent.py # The base class for all agents
│   ├── BaseReflectionAgent.py # The base class for all reflection agents
│   ├── BaseInput.py # The base class for all agent inputs
│   ├── AgentState.py # The state that is used to pass information between agents
├── tools/ # Contains the tools that the agents have access to
├── app_config.py # The state/configuration of the application
├── model_configs.py # The LLM models to be tested
├── llm_factory.py
├── graph_offline_s1.py # The graph that models the agents and their interactions
├── graph_offline_s2.py
├── graph_offline_s3.py
├── graph_offline_s4.py
├── app.py # The entry point of the framework
```


