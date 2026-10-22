# Contributing to Mnemos

Thanks for helping make portable AI memory more useful.

## Ground rules

- Keep the core local-first and usable without API keys or network access.
- Prefer the Python standard library for core functionality.
- Preserve provenance and make search/relationship behavior explainable.
- Never commit memory databases, exports containing personal data, credentials, or API keys.
- Add tests for behavior changes and update relevant documentation.
- Keep each change focused and reviewable.

## Development

Requires Python 3.11+.

```bash
python -m unittest discover -s tests -v
python -m pip install -e .
mnemos --help
```

## Pull requests

Describe the user problem, behavior changed, tests run, and any migration or data-format impact. For export changes, include compatibility notes.
