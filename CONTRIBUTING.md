# Contributing

Thanks for helping. Bug reports, fixes and support for more `.ai` variants are all welcome.

## Reporting a bug

Open an issue with:

- the script's full output,
- your VectorCraft version (`VectorCraft --version`), Python version and macOS version,
- the Illustrator version that saved the file, if you know it.

**Do not attach `.ai` files with personal content** (names, addresses, photos) to a public issue. If a file is needed to reproduce the bug, make a minimal one that shows the problem, or ask in the issue for another way to share it.

## Pull requests

1. Fork the repository and create a branch.
2. Keep the script dependency-free: standard library only.
3. Add or update a test in `tests/` when you change the parsing or the fix.
4. Run the tests: `python3 -m unittest discover -s tests -v`.
5. Describe in the pull request what you tested, and on which kind of file.

## Style

- Follow the existing code: small functions, plain names, comments only where the reason is not obvious.
- Messages printed to the user stay short and say what happened.

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE), and that you follow the [Code of Conduct](CODE_OF_CONDUCT.md).
