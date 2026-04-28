import os

import pytest
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.caches import InMemoryCache
from langchain_core.globals import set_llm_cache

from etter import GeoFilterParser


@pytest.fixture(scope="session")
def parser():
    """Create parser with LLM for testing (shared across all tests in the session)."""
    load_dotenv()
    if not os.getenv("LLM_API_KEY"):
        pytest.skip("LLM_API_KEY not set")
    set_llm_cache(InMemoryCache())
    LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")
    llm = init_chat_model(model=LLM_MODEL, temperature=0, api_key=os.getenv("LLM_API_KEY"))
    return GeoFilterParser(llm=llm)
