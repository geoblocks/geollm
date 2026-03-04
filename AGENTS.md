# Agent Guidelines

This file contains important information for AI agents working in this codebase.

## Architecture

See [ARCHITECTURE.md](./ARCHITECTURE.md) for detailed documentation on:
- Spatial relations processing pipeline
- Component overview (Parser, DataSource, Spatial Operations)
- Data models and type system
- Project structure

## Local Development

### Completion Criteria

Changes are complete only when ALL of the following requirements are met:

1. **All pre-commit checks pass** - Run code checks on modified files
2. **All tests pass** - Run the full test suite or relevant test files
3. **Architecture documentation is updated** - Update [ARCHITECTURE.md](./ARCHITECTURE.md) if needed.

### Code checks

All pre-commit checks must pass before work is considered complete.

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
- Some tests may be skipped if environment variables (e.g., `LLM_API_KEY`) are not set
