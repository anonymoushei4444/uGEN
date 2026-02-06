# Import necessary modules
# from langchain import hub # type: ignore
from langchain_community.document_loaders import DirectoryLoader # type: ignore
from langchain_core.documents import Document # type: ignore
from langchain_text_splitters import RecursiveCharacterTextSplitter # type: ignore
from typing_extensions import List, TypedDict # type: ignore
from langchain_core.vectorstores import InMemoryVectorStore # type: ignore
from langchain_openai import OpenAIEmbeddings # type: ignore
from langchain_community.document_loaders.pdf import PyMuPDFLoader # type: ignore
from langchain_community.document_loaders.text import TextLoader # type: ignore
from langchain_community.document_loaders.html_bs import BSHTMLLoader # type: ignore
from langchain_community.vectorstores import Chroma # type: ignore
from agents.AgentState import AgentState
# from agents.programmer.ProgrammerAgent import ProgrammerAgent

from langchain.tools import tool # type: ignore
from pydantic import BaseModel, Field # type: ignore

import tiktoken
import re
import os
import pickle
from pathlib import Path
import numpy as np
from typing import Any, Dict


from app_config import get_logger
log = get_logger(__name__)

# Define cache directory and file path
# CACHE_DIR = Path("/home/Anonymous/workdir/RAG_Dir_GPT/.chroma_db")
# CACHE_DIR = Path("/home/Anonymous/workdir/RAG_Dir_Claude/.chroma_db")

def get_cache_and_doc_dir(selected_model_key: str, attack_vector: str):
    key = (selected_model_key or "").lower()
    attack_vector = (attack_vector or "").strip()
    # Expandable mapping-by-substring (add 'llama', 'deepseek', etc. as you add stores)
    if "claude" in key or "anthropic" in key:
        cache_dir = Path(f"/home/Anonymous/workdir/RAG_Dir_Claude/{attack_vector}/.chroma_db")
        doc_dir = f"/home/Anonymous/workdir/RAG_Dir_Claude/{attack_vector}"
    elif "gpt" in key or "openai" in key or "4o" in key:
        cache_dir = Path(f"/home/Anonymous/workdir/RAG_Dir_GPT/{attack_vector}/.chroma_db")
        doc_dir = f"/home/Anonymous/workdir/RAG_Dir_GPT/{attack_vector}"
    elif "qwen3-coder" in key or "together" in key:
        cache_dir = Path(f"/home/Anonymous/workdir/RAG_Dir_Qwen3/{attack_vector}/.chroma_db")
        doc_dir = f"/home/Anonymous/workdir/RAG_Dir_Qwen3/{attack_vector}"
    elif "llama" in key or "maverick" in key or "ollama" in key:
        cache_dir = Path(f"/home/Anonymous/workdir/RAG_Dir_Llama/{attack_vector}/.chroma_db")
        doc_dir = f"/home/Anonymous/workdir/RAG_Dir_Llama/{attack_vector}"
    elif "deepseek" in key:
        cache_dir = Path(f"/home/Anonymous/workdir/RAG_Dir_deepseek/{attack_vector}/.chroma_db")
        doc_dir = f"/home/Anonymous/workdir/RAG_Dir_deepseek/{attack_vector}"
    else:
        # Safe default (keep GPT as fallback)
        cache_dir = Path(f"/home/Anonymous/workdir/RAG_Dir_GPT/{attack_vector}/.chroma_db")
        doc_dir = f"/home/Anonymous/workdir/RAG_Dir_GPT/{attack_vector}"
    return cache_dir, doc_dir

def initialize_retriever(document_directory: str, cache_dir: Path, force_refresh: bool = False):
    """
    overview of the workflow:
        Document Loading: loading documents from a specified directory.     
        Text Splitting: segments the text into chunks of a specified size with optional overlap between chunks.
        Embedding Generation: For each text chunk, the function generates embeddings using a model like OpenAIEmbeddings. 
        Vector Store Creation: The generated embeddings are stored in a vector store, such as InMemoryVectorStore that allows rapid retrieval based on semantic similarity.
    Obj:     
        Build vector store once and cache doc chunks + their embeddings to disk.
        Subsequent calls load cached docs/embeddings unless force_refresh=True or cache missing.
    """
    # Ensure cache dir exists
    cache_dir.mkdir(parents=True, exist_ok=True)

    # If Chroma DB exists and not force_refresh, load it
    if not force_refresh and any(cache_dir.iterdir()):
        try:
            embeddings = OpenAIEmbeddings(model="text-embedding-3-large")
            vector_store = Chroma(
                persist_directory=str(cache_dir),
                embedding_function=embeddings
            )
            log.info(f"[+] Loaded Chroma vector store from {cache_dir}")
            return vector_store
        except Exception as e:
            log.warning(f"[!] Failed loading Chroma DB ({e}), rebuilding vector store.")

    log.info(f"[+] Building Chroma vector store from documents in {document_directory}...")
    loaders = []
    pdf_loader = DirectoryLoader(
        path=document_directory,
        glob="**/*.pdf",
        loader_cls=PyMuPDFLoader,
        recursive=True,
        silent_errors=False
    )
    loaders.append(pdf_loader)
    text_loader = DirectoryLoader(
        path=document_directory,
        glob="**/*.txt",
        loader_cls=TextLoader,
        recursive=True,
        silent_errors=False
    )
    loaders.append(text_loader)
    html_loader = DirectoryLoader(
        path=document_directory,
        glob="**/*.html",
        loader_cls=BSHTMLLoader,
        recursive=True,
        silent_errors=False
    )
    loaders.append(html_loader)

    documents = []
    for loader in loaders:
        loaded_docs = loader.load()
        for doc in loaded_docs:
            log.info(f"[+] Loaded document: {doc.metadata.get('source', 'Unknown Source')}")
        documents.extend(loaded_docs)

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=6000, chunk_overlap=1500)
    docs = text_splitter.split_documents(documents)

    embeddings = OpenAIEmbeddings(model="text-embedding-3-large")
    vector_store = Chroma.from_documents(
        docs,
        embeddings,
        persist_directory=str(cache_dir)
    )
    vector_store.persist()
    log.info(f"[+] Chroma vector store built and persisted to {cache_dir}")

    # Token counting (unchanged)
    encoding = tiktoken.encoding_for_model("text-embedding-3-large")
    total_tokens = 0
    for doc in docs:
        num_tokens = len(encoding.encode(doc.page_content))
        total_tokens += num_tokens

    log.info(f"*********************  Total number of tokens processed: {total_tokens}  ***************************")
    return vector_store

class RetrieveResponse(BaseModel):
    query: str = Field(default=None, description="The search query")
    state: Dict[str, Any] = Field(default_factory=dict)
    # vector_store: InMemoryVectorStore =Field(description="The vector store containing document embeddings")
    pass
    
    # model_config = ConfigDict(arbitrary_types_allowed=True)



# Define the retrieve_document tool
# changing from "retrieve_document" to "rag_tool"
@tool("rag_tool", args_schema=RetrieveResponse, return_direct=True)
def rag_tool(query: str, state: Dict[str, Any] | None = None) -> tuple[str, str]:
    """
    The rag_tool function is designed to facilitate the retrieval of information from a collection of documents, 
    such as PDFs and text files, by leveraging embeddings for semantic search. 
    Retrieve documents from the vector store that are semantically similar to the query.

    Args:
        query (str): The search query.

    Returns:
        Tuple[str, str]: A tuple containing the retrieved content and any error messages.
    """
    try:
        # Define the document directory
        selected_model_key = "gpt-4o"  # Default
        if state and "selected_model_key" in state:
            selected_model_key = state["selected_model_key"]
        attack_vector = (state or {}).get("attack_vector")
        cache_dir, document_directory = get_cache_and_doc_dir(selected_model_key, attack_vector)

        log.info(f"[rag_tool] selected_model_key={selected_model_key}")
        log.info(f"[rag_tool] Using doc_dir={document_directory}, cache_dir={cache_dir}")

        # Initialize the retriever with the directory
        vector_store = initialize_retriever(document_directory, cache_dir)

        # Perform similarity search in the vector store
        retrieved_docs = vector_store.similarity_search(query, k=1)

        if not retrieved_docs:
            return "", "No relevant documents found."

        # Format the retrieved documents
        serialized_docs = "\n\n".join(
            f"Source: {doc.metadata}\nContent: {doc.page_content}"
            for doc in retrieved_docs
        )
        return query, serialized_docs

    except Exception as e:
        return "", str(e)
    
