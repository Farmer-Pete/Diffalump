# Diffalump

![Diffalump Logo](Diffalump.png)

Diffalump is a command-line tool that analyzes changes between
two Git branches and breaks them down into chunks that are easily
digestible by an AI, combining small changes together while
splitting large files appropriately.

## Installation

Diffalump requires Python 3.8+ and can be installed using `uv`:

```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Usage

```bash
uv run python main.py
```

You can find a AI prompt that works well with Diffalump in [prompt.md](prompt.md)

## License

MIT License
