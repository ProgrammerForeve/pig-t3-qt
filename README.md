# 🐖 PIG-T3 – AI Context Generator & Patcher

**PIG-T3** is a powerful desktop application (GUI) that helps you work with large codebases together with AI assistants (ChatGPT, Claude, DeepSeek, local Ollama models).

It generates a **context report** containing the full project structure and source code, ready to be sent to any LLM. It then allows you to **apply the AI's JSON-based code changes automatically** – including creating, editing, moving and deleting files – with full undo/redo support.

Additionally, PIG-T3 includes:
- 📝 **AI Plan Manager** – generate step-by-step implementation plans and execute them automatically.
- 🔍 **Code Quality Scanner** – analyse your Python code (complexity, maintainability, lint score, security).
- 🧠 **Context Optimizer** – select only the most relevant files for a given task using dependency graphs and AI ranking.
- 🎨 **Multiple themes** (dark, light, pink, eye-care) and Git integration.

---

## ✨ Features

### 🏠 Context Generator
- Scan a project folder, ignore binary/unwanted files, collect source code.
- Produce a single `.txt` or `.md` file with XML-like tags for each file.
- Optionally include line numbers and an AI instruction prompt for JSON patching.
- Copy the output file directly to the clipboard.

### ✏️ JSON Patcher (Editor)
- Paste the LLM's response (JSON array of actions).
- Validate and pretty-print the JSON.
- Apply changes to the disk: **create**, **delete**, **move**, **edit** (replace_lines, insert_after_line, replace_text).
- Built-in **Ollama Auto-Fix** – if the LLM returns malformed JSON, let a local model repair it.
- Full **Undo/Redo** history (files are backed up inside `.pig/backups`).

### 📝 AI Plan Manager
- Describe your project goal in natural language – PIG-T3 will generate a detailed step-by-step plan.
- Each step can be executed automatically:
  - The app prepares an optimized context.
  - An LLM (local or web) generates the necessary code changes in JSON format.
  - Changes are applied immediately (or sent to the Editor for manual review).
- Supports retries on errors, plan validation, and Git auto-commit before each step.

### 📊 Code Quality Analysis
- Scans all Python files in the project.
- Calculates:
  - **Cyclomatic Complexity** (Radon CC)
  - **Maintainability Index** (Radon MI)
  - **Pylint Score** (custom penalty-based score)
  - **Security Issues** (Bandit)
- Displays results in a sortable tree with color-coded statuses.

### 🧠 Context Optimizer
- Given a task description, selects the most important files for the AI to understand.
- Uses a **dependency graph** (imports) with BFS and an **LLM-based relevance ranking**.
- Helps keep the context size within token limits while retaining crucial information.

### 🤖 Supported AI Backends
- **Ollama** – any local model (e.g., `qwen2.5-coder`).
- **Web APIs** – DeepSeek (Chat), Gemini (AI Studio) via browser automation.
- **BomjAPI** – a manual testing tool (opens a window where you paste responses by hand).

---

## 📦 Installation

PIG-T3 requires **Python 3.8+**. Install directly from PyPI:

```bash
pip install pig-t3
```

If you plan to use the **Web API** backends (DeepSeek, Gemini), you also need to install a Chromium browser for Playwright:

```bash
playwright install chromium
```

### Dependencies
These are installed automatically:
`requests`, `radon`, `pylint`, `vulture`, `bandit`, `Pillow`, `majorchik-api` (Playwright-based web automation), `networkx`.

---

## 🚀 Quick Start

1. Launch the application:
   ```bash
   pig-t3
   ```
2. Select your project folder (or let it auto-detect).
3. In the **Generator** tab, optionally adjust extensions and ignore list, then click **Generate Context**.
4. Copy the generated file and send it to your favourite AI assistant.
5. Paste the AI's JSON response into the **Editor** tab, click **Apply Changes**.

---

## 🧩 How It Works

### Workflow
1. **Scan** → Collect all source files into a single report.
2. **Send** → The report is given to an LLM along with the editing instructions (optionally).
3. **Receive JSON** → The LLM returns a JSON array of file operations.
4. **Apply** → PIG-T3 parses the JSON, backs up affected files, and performs the changes.

### JSON Actions Reference
A typical LLM response looks like this:

```json
[
  {
    "action": "create",
    "path": "utils/helper.py",
    "content": "def help():\n    return True"
  },
  {
    "action": "edit",
    "path": "main.py",
    "operations": [
      {
        "type": "replace_lines",
        "start": 10,
        "end": 12,
        "content": "    new_code()"
      },
      {
        "type": "insert_after_line",
        "line": 15,
        "content": "    logger.info('Done')"
      }
    ]
  }
]
```

Full specification is available in the **Info / JSON Specs** tab inside the app.

---

## ⚙️ Configuration

All settings are saved in `app_config.json` (global) and in `.pig/state.json` (per project).
You can tweak:
- Theme, font size, tree row height.
- Context optimizer parameters (BFS depth, LLM weighting).
- Git integration (auto-commit, auto-push, branch mode).
- LLM timeouts and retry settings.

---

## 🐙 Git Integration

When enabled in settings, PIG-T3 can:
- Automatically create a new Git branch before executing a plan step.
- Commit all changes with a descriptive message.
- Push to remote after each successful step.

---

## 🧪 Development & Building

To build a standalone executable:

```bash
pyinstaller pig_t3.spec --noconfirm
```

The spec bundles PySide6, qt-material stylesheets, application icons
and the quality-scan / context-optimizer dependencies. Output:

- Linux: `dist/PIG-T3`
- Windows: `dist/PIG-T3.exe`
- macOS: `dist/PIG-T3` (unsigned; `xattr -dr com.apple.quarantine dist/PIG-T3`
  after copying to another machine)
```

---

## 📄 License

PIG-T3 is released under the **MIT License**. See the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgements

This project uses several open-source libraries and tools:
Radon, Pylint, Vulture, Bandit, NetworkX, Playwright, and others.
Special thanks to the Ollama project for local AI capabilities.

---

> Made with ❤️ by Loki (gosoftware2025@gmail.com)
> updated by ProgrammeForever
