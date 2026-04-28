FROM apache/airflow:2.9.3-python3.11

USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc \
    && rm -rf /var/lib/apt/lists/*

USER airflow

RUN pip install --no-cache-dir \
    "langchain>=0.3.0" \
    "langchain-core>=0.3.0" \
    "langchain-openai>=0.2.0" \
    "langchain-chroma>=0.2.0" \
    "chromadb>=0.5.0" \
    "biopython>=1.80" \
    "pydantic-settings>=2.0" \
    "python-dotenv>=1.0" \
    "tavily-python>=0.5.0"
