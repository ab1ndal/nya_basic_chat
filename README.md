# NYA Basic Chat

A lightweight Streamlit application for chat interactions with file upload and preview support.

## Prerequisites
- Python 3.13 (matching the version specified in `pyproject.toml`)
- [Poetry](https://python-poetry.org/docs/#installation) for dependency management

## Installation
1. Clone this repository and move into the project directory:
   ```bash
   git clone <repository-url>
   cd nya_basic_chat
   ```
2. Install the project dependencies with Poetry:
   ```bash
   poetry install
   ```
3. Create a local environment file:
   ```bash
   cp .env.example .env
   ```
   Update `.env` with the credentials or configuration your deployment needs.

## Project Structure
```
nya_basic_chat/
  app.py
  assets/
    NYA_logo.svg
  src/
    nya_basic_chat/
      __init__.py
      helpers.py
      llm_client.py
  uploads/
  .env.example
  poetry.lock
  pyproject.toml
```

## File Reference
- `app.py`: Streamlit entry point; wires UI components, file upload handling, and chat workflow.
- `assets/NYA_logo.svg`: Logo displayed in the Streamlit interface.
- `src/nya_basic_chat/__init__.py`: Marks `nya_basic_chat` as a package and exposes reusable components.
- `src/nya_basic_chat/helpers.py`: Shared helper functions for formatting, validation, and file processing.
- `src/nya_basic_chat/llm_client.py`: Wrapper around the LLM API, manages prompts and streaming responses.
- `uploads/`: Runtime storage for files users upload in the chat interface (ignored by version control).
- `.env.example`: Template for required environment variables such as API keys or model configuration.
- `pyproject.toml`: Project metadata, dependency definitions, and tool configuration.
- `poetry.lock`: Locked dependency versions ensuring reproducible installs.

## Running the App
Start the Streamlit development server:
```bash
poetry run streamlit run app.py
```
The command launches Streamlit on the default port (usually http://localhost:8501/). The terminal output will display the exact URL.

## Optional: Development Setup
- Install development dependencies and tools:
  ```bash
  poetry install --with dev
  ```
- Run the test suite:
  ```bash
  poetry run pytest
  ```

## Troubleshooting
- If Poetry cannot find Python 3.13, install it and re-run `poetry env use 3.13`.
- To refresh dependencies after editing `pyproject.toml`, run `poetry lock --no-update` followed by `poetry install`.
