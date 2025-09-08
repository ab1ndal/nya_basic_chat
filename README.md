# NYA Basic Chat

A lightweight chat application with file upload and preview capabilities, built with Streamlit and Python.

## 📋 Features

- 💬 Chat interface with streaming responses
- 📁 File upload support (images, PDFs, and more)
- 📄 PDF preview functionality
- 🖼️ Image preview
- 🔄 Conversation history
- 🔒 Secure file handling

## 🏗️ Project Structure

```
ya_basic_chat/
├── assets/                  # Static assets (images, icons, etc.)
│   └── NYA_logo.svg        # Application logo
├── src/                    # Source code
│   └── nya_basic_chat/     # Python package
│       ├── __init__.py     # Package initialization
│       ├── helpers.py      # Utility functions
│       └── llm_client.py   # LLM client implementation
├── uploads/                # User-uploaded files
├── .env.example            # Example environment variables
├── app.py                  # Main Streamlit application
├── poetry.lock             # Poetry dependency lock file
└── pyproject.toml          # Project configuration and dependencies
```

## 🚀 Getting Started

### Prerequisites

- Python 3.13
- Poetry (for dependency management)

### Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd nya_basic_chat
   ```

2. Install dependencies:
   ```bash
   poetry install
   ```

3. Copy the example environment file and update with your API keys:
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

### Running the Application

Start the Streamlit application:
```bash
poetry run streamlit run app.py
```

## 🛠️ Development

### Dependencies

- Python 3.13
- Poetry for dependency management

### Development Setup

1. Install development dependencies:
   ```bash
   poetry install --with dev
   ```

2. Set up pre-commit hooks:
   ```bash
   pre-commit install
   ```

### Code Style

This project uses:
- Black for code formatting
- Ruff for linting
- Pre-commit hooks for automated code quality checks

## 📝 License

This project is licensed under the terms of the MIT License. See the [LICENSE](LICENSE) file for details.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
