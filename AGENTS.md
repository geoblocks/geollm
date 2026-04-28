# Agent Guidelines

This file contains important information for AI agents working in this codebase.

## Local Development

### Completion Criteria

Changes are complete only when ALL of the following requirements are met:

1. **All pre-commit checks pass** - Run code checks on modified files
2. **All tests pass** - Run the full test suite or relevant test files
3. **Documentation audit passed** - See [Documentation Review](#documentation-review) below.

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

## Documentation Review

Documentation must remain in sync with code implementation. Before marking changes as complete, audit the affected documentation files against the corresponding Python code.

### Documentation-to-Code Mapping

Review these files based on which Python modules you modified:

#### `ARCHITECTURE.md`

- **Maps to**: `etter/parser.py`, `etter/datasources/`, `etter/spatial.py`, `etter/models.py`
- **Verify**:
  - System architecture diagram (Layer 1, 2, 3) still matches actual code organization
  - Component descriptions (GeoFilterParser, GeoDataSource, spatial operations) align with class names and responsibilities
  - Complete workflow example reflects current API behavior
  - Data model descriptions (GeoQuery, spatial relations) match Pydantic models in `models.py`

#### `README.md`

- **Maps to**: `etter/__init__.py`, package public API, `etter/examples.py`
- **Verify**:
  - Feature list matches current capabilities
  - Installation instructions are current (dependencies, version)
  - "What etter Does/Doesn't Do" section is accurate
  - Usage examples in Quick Start section run without errors
  - Links to documentation are not broken

#### `docs/guide/getting-started.md`

- **Maps to**: `etter/__init__.py`, `etter/parser.py`, `etter/examples.py`
- **Verify**:
  - API usage examples match current function signatures
  - Default parameters and behavior are current
  - Installation steps reference correct package versions
  - Code snippets are runnable

#### `docs/guide/spatial-relations.md`

- **Maps to**: `etter/spatial_config.py`, `etter/spatial.py`, `etter/models.py`
- **Verify**:
  - List of supported spatial relations matches `spatial_config.py` definitions
  - Descriptions of how each relation works match implementation in `spatial.py`
  - Geometry transformation examples are accurate
  - Buffer defaults match `spatial_config.py`

#### `docs/guide/datasources.md`

- **Maps to**: `etter/datasources/protocol.py`, `etter/datasources/*.py`
- **Verify**:
  - Supported datasources list matches actual implementations (swissnames3d, postgis, ign_bdcarto, composite)
  - API for creating custom datasources matches the `GeoDataSourceProtocol`
  - Example code for each datasource is current and runnable
  - Configuration options and parameters are accurate

#### `docs/guide/error-handling.md`

- **Maps to**: `etter/exceptions.py`, `etter/validators.py`
- **Verify**:
  - Exception types listed match classes in `exceptions.py`
  - Error scenarios and handling patterns match validator logic
  - Example error messages are current

#### `etter/examples.py` (Few-shot examples)

- **Maps to**: `etter/spatial_config.py`, all spatial relations
- **Verify**:
  - Examples cover representative spatial relation categories:
    - ≥1 containment relation (e.g., in)
    - ≥2 buffer relations demonstrating different patterns (e.g., near, on_shores_of, in_the_heart_of, left_bank/right_bank)
    - ≥1 directional relation (e.g., north_of)
  - Each example produces valid Pydantic model output
  - Examples demonstrate key features like ring_only, side parameters
  - Language coverage is representative (English primary, at least one other language)

### How to Conduct a Documentation Review

1. **Identify changed files**: Note which Python files were modified in this change
2. **Find mapped docs**: Use the mapping above to identify documentation files to review
3. **Spot check key sections**:
   - Run example code snippets to ensure they work
   - Verify function signatures in examples match actual code
   - Check parameter names and default values
   - Validate class and module names
4. **Flag issues**: If you find stale documentation:
   - Note the specific section and what changed in the code
   - Describe what the documentation currently says vs. what it should say
   - Create follow-up tasks or comments for documentation updates
5. **Mark complete**: Only when docs are in sync with code changes OR stale sections are clearly flagged for update
