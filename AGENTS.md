# Agent Guidelines

This file contains important information for AI agents working in this codebase.

## Local Development

### Code checks

Ensure all pre-commit checks pass before considering work complete.

**Run checks on modified files only**:

```bash
pre-commit run --files <file1> <file2>...
```

## Testing

### Running Tests

The project uses pytest for testing. Always run tests after making changes to ensure nothing breaks.

**Run all tests**:

```bash
python -m pytest -v
```

**Run specific test file**:

```bash
python -m pytest tests/test_models.py -v
```

**Run specific test function**:

```bash
python -m pytest tests/test_models.py::test_reference_location -v
```

**Notes**:

- Use `python -m pytest` instead of just `pytest` to ensure the correct Python environment is used
- Some tests may be skipped if environment variables (e.g., `OPENAI_API_KEY`) are not set
- All tests should pass before considering work complete
