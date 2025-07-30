## Development Notes

- Always call venv activate command before running
- Use context7 mcp for understanding how to use libraries and there apis and documentation
- Never use hasattr make sure you have the variable present at all times in useable form
- Put timeout of 60s before calling running python scripts, so they stop
- When putting debug prints use _log_to_console or similar methods to print to our progress_ui 

## Python Linting

The project uses multiple linting tools for code quality:

### Tools Configured
- **flake8**: PEP 8 style guide enforcement
- **pylint**: Comprehensive code analysis

### Usage
- `python lint.py` - Run all linting checks
- Individual tools: `flake8 src/`, `pylint src/`

### Configuration Files
- `.flake8` - Flake8 settings (line length, ignores)
- `pyproject.toml` - Pylint configuration