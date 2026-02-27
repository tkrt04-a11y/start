# AI Driven Development Starter Kit

This repository provides a minimal starter kit for AI-driven development in Python. It includes:

- A basic project structure
- Example code for loading and using AI models (OpenAI SDK)
- Simple CLI entry point
- Unit tests
- Development guidelines

## Setup

1. Create a Python virtual environment:
   ```sh
   python -m venv venv
   .\\venv\\Scripts\\activate
   ```
2. Install dependencies:
   ```sh
   pip install -r requirements.txt
   ```

## Usage

Run the main script:
```sh
python -m src.main
```

## Testing

```sh
pytest
```

## Notes

- Replace `requirements.txt` with needed AI libraries (e.g., openai, transformers)
- Configure environment variables (API keys) as required
