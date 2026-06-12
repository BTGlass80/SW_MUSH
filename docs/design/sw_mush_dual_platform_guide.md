# SW_MUSH Dual-Platform Development Guide

## Windows Desktop (RTX 3070) + MacBook Air M4

---

## 1. The AI Question — What Changes and What Doesn't

SW_MUSH has two AI providers with very different hardware implications.

**Claude Haiku (Director AI + Narrative Memory)** — No change needed. This is a cloud API. It works identically on both machines. Your `ANTHROPIC_API_KEY` environment variable, the `ClaudeProvider` in `ai/claude_provider.py`, the budget tracker, the circuit breaker — all of it is pure HTTP over `aiohttp`. The MacBook Air will make the same API calls at the same cost. Nothing to configure.

**Ollama / Mistral 7B (NPC Dialogue)** — This is the interesting one. Three options:

### Option A: Run Ollama Locally on the M4 (Recommended for Dev)

The MacBook Air M4 has a 10-core GPU with unified memory. It can run Mistral 7B, but the experience differs from the 3070:

- The M4 Air has 16GB or 24GB unified memory (check yours — it matters). Mistral 7B needs ~4.5GB in Q4 quantization. With 16GB total shared between CPU/GPU/OS, it'll run but you'll feel memory pressure if you also have VS Code, a browser, and the game server open. 24GB is comfortable.
- Inference speed will be slower than the 3070 (roughly 15–25 tok/s on M4 Air vs 30–40 tok/s on the 3070 8GB). For NPC dialogue where you're generating short responses, this is fine — players won't notice the difference.
- The Ollama macOS app is a native Apple Silicon build. Installation is trivial (covered in Section 3).

### Option B: Point the MacBook at the Desktop's Ollama (Remote)

If both machines are on the same network, you can run Ollama only on the Windows desktop and have the MacBook connect to it remotely. In your `ai/providers.py`, the Ollama base URL is configurable. Set it to `http://<desktop-ip>:11434` on the Mac instead of `http://localhost:11434`.

Pros: Zero GPU load on the MacBook, full 3070 performance. Cons: Requires the desktop to be on, adds network latency, won't work at a coffee shop.

To expose Ollama on the network from Windows, set the environment variable `OLLAMA_HOST=0.0.0.0:11434` before starting Ollama. Be aware this opens it to your LAN.

### Option C: MockProvider (No AI at All)

Your `AIManager` already has a `MockProvider`. For pure code/UI development where you don't need live NPC dialogue, just set the AI provider to mock. NPCs will return canned responses. This is the lightest option and what you'd use on a plane or anywhere without the desktop.

### Recommendation

Use **Option A** for general development (it works, it's self-contained) and **Option C** when you're working on non-AI features. Only bother with Option B if you're specifically testing NPC dialogue quality and want the 3070's speed.

### What to Put in Your Config

Add an environment-based toggle so you don't have to edit code when switching machines. A `.env` file (not committed to git) per machine:

```bash
# .env on Windows desktop
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=mistral:7b
AI_PROVIDER=ollama

# .env on MacBook Air (local Ollama)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=mistral:7b
AI_PROVIDER=ollama

# .env on MacBook Air (remote to desktop)
OLLAMA_BASE_URL=http://192.168.1.100:11434
OLLAMA_MODEL=mistral:7b
AI_PROVIDER=ollama

# .env on MacBook Air (no AI)
AI_PROVIDER=mock
```

Your `providers.py` should read `OLLAMA_BASE_URL` from the environment with a localhost default. If it doesn't already, that's a small patch.

---

## 2. Line Endings — The Silent Killer

You already know this one from the CRLF patch failures. With two OS's sharing a repo, you **must** configure Git's line ending handling before cloning on the Mac, or you'll get phantom diffs on every file.

Add a `.gitattributes` file to the repo root (if you don't have one already):

```
# Force LF everywhere — Python, YAML, HTML, JS, Markdown
* text=auto eol=lf

# Binary files — never touch these
*.sqlite binary
*.db binary
*.png binary
*.jpg binary
*.pdf binary
*.zip binary
```

This ensures both machines check out LF line endings regardless of OS. Commit this from the Windows side first, then clone fresh on the Mac.

---

## 3. Setting Up the MacBook Air — Step by Step

You're coming from Windows. macOS will feel alien for about a week, then it'll click. Here's everything from first boot to running the game server.

### 3.1 Terminal Basics

macOS has a built-in terminal app called **Terminal** (in Applications → Utilities). It runs `zsh` by default, which is similar to bash. You can also install **iTerm2** later if you want a better terminal, but the built-in one is fine to start.

Key differences from Windows Command Prompt / PowerShell:
- Paths use forward slashes: `/Users/brian/projects/SW_MUSH`
- Your home directory is `~` which expands to `/Users/brian`
- No drive letters. Everything hangs off `/`
- `ls` instead of `dir`, `rm` instead of `del`, `cp` instead of `copy`
- File/folder names are case-insensitive by default on macOS (unlike Linux)

### 3.2 Install Homebrew (macOS Package Manager)

Homebrew is the equivalent of `apt` on Linux or `winget`/`choco` on Windows. You'll use it to install almost everything.

Open Terminal and paste:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Follow the prompts. When it finishes, it'll tell you to run two commands to add Homebrew to your PATH — do that. Then close and reopen Terminal.

Verify: `brew --version`

### 3.3 Install Git

macOS ships with a version of Git via Xcode Command Line Tools, but Homebrew's is newer:

```bash
brew install git
```

Configure your identity (use the same name/email as on Windows):

```bash
git config --global user.name "BTGlass80"
git config --global user.email "your-email@example.com"
git config --global core.autocrlf input
git config --global init.defaultBranch main
```

The `core.autocrlf input` setting ensures Git converts CRLF to LF on commit but doesn't touch files on checkout. Combined with the `.gitattributes` file, this prevents line ending issues.

### 3.4 Set Up SSH Key for GitHub

You'll want SSH so you don't type your password constantly:

```bash
ssh-keygen -t ed25519 -C "your-email@example.com"
```

Press Enter for default location, set a passphrase (or leave blank for convenience).

```bash
# Start the SSH agent
eval "$(ssh-agent -s)"

# Add key to agent (macOS Keychain will remember the passphrase)
ssh-add --apple-use-keychain ~/.ssh/id_ed25519

# Copy the public key to clipboard
pbcopy < ~/.ssh/id_ed25519.pub
```

Go to GitHub → Settings → SSH and GPG Keys → New SSH Key → paste → Save.

Test: `ssh -T git@github.com` — should say "Hi BTGlass80!"

### 3.5 Install Python

macOS ships with Python, but it's an older system version you shouldn't touch. Install a clean one:

```bash
brew install python@3.12
```

(Use 3.12 for now — your project says 3.14 in the architecture doc, but 3.12 is the current stable. If you're actually on 3.14-dev on Windows, install the same version via `brew install python@3.14` if available, or use `pyenv` — see below.)

Verify:

```bash
python3 --version
pip3 --version
```

**Important:** On macOS, the command is `python3` and `pip3`, not `python` and `pip`. You can alias it if you want:

```bash
echo 'alias python=python3' >> ~/.zshrc
echo 'alias pip=pip3' >> ~/.zshrc
source ~/.zshrc
```

**If you need to match your Windows Python version exactly**, install `pyenv`:

```bash
brew install pyenv
echo 'eval "$(pyenv init -)"' >> ~/.zshrc
source ~/.zshrc
pyenv install 3.12.4   # or whatever version you use on Windows
pyenv global 3.12.4
```

### 3.6 Clone the Repo

```bash
mkdir -p ~/projects
cd ~/projects
git clone git@github.com:BTGlass80/SW_MUSH.git
cd SW_MUSH
```

### 3.7 Create a Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
```

Your prompt should now show `(venv)`. This is the equivalent of `venv\Scripts\activate` on Windows.

**Add to your shell config so you don't forget to activate:**

```bash
# Optional convenience — cd into the project auto-activates
echo 'function sw() { cd ~/projects/SW_MUSH && source venv/bin/activate; }' >> ~/.zshrc
source ~/.zshrc
```

Now just type `sw` to jump to the project with the venv active.

### 3.8 Install Python Dependencies

```bash
pip install -r requirements.txt
```

If you don't have a `requirements.txt` yet (you should make one!), install manually:

```bash
pip install aiohttp aiosqlite pyyaml
```

**Create `requirements.txt` from your Windows machine** if you haven't:

```bash
# On Windows, in your venv:
pip freeze > requirements.txt
git add requirements.txt
git commit -m "Add requirements.txt for cross-platform"
git push
```

### 3.9 Install Ollama (if using Option A)

```bash
# Download from the website — Homebrew doesn't have it
# Go to https://ollama.com/download/mac and download the .dmg
# Drag to Applications, launch it

# Or via curl:
curl -fsSL https://ollama.com/install.sh | sh
```

Pull the model:

```bash
ollama pull mistral:7b
```

Verify: `ollama list` should show `mistral:7b`.

Ollama runs as a background service on macOS. It starts automatically and listens on `localhost:11434`.

### 3.10 Install VS Code

Download from https://code.visualstudio.com/ — there's a native Apple Silicon build.

Or via Homebrew:

```bash
brew install --cask visual-studio-code
```

**Install the `code` command for terminal access:**
Open VS Code → Cmd+Shift+P → type "shell command" → select "Install 'code' command in PATH"

Now you can do:

```bash
cd ~/projects/SW_MUSH
code .
```

**Recommended VS Code extensions** (same as Windows):
- Python (Microsoft)
- Pylint or Ruff
- GitLens
- Remote - SSH (if you ever want to edit files on the desktop from the MacBook)

### 3.11 Set Up Your .env File

```bash
cp .env.example .env  # if you have a template
# or create from scratch:
cat > .env << 'EOF'
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=mistral:7b
AI_PROVIDER=ollama
ANTHROPIC_API_KEY=sk-ant-your-key-here
EOF
```

Make sure `.env` is in your `.gitignore` so you never commit API keys.

### 3.12 Run the Server

```bash
source venv/bin/activate
python3 main.py
```

You should see the server boot on ports 4000 (Telnet), 4001 (WebSocket), 8080 (HTTP). Open `http://localhost:8080` in Safari or Chrome to hit the web client.

### 3.13 SQLite — No Install Needed

macOS ships with SQLite. Your `aiosqlite` Python package handles everything. The `.sqlite` database file is portable between Windows and Mac without conversion.

---

## 4. Cross-Platform Workflow

### 4.1 Git as the Bridge

Your workflow across both machines is simple:

1. **Finish a session on one machine** → `git add . && git commit -m "description" && git push`
2. **Start on the other machine** → `git pull`

That's it. The database file (`sw_mush.db` or whatever you named it) should be in `.gitignore` — don't sync it via Git. Each machine keeps its own local DB. Run `build_mos_eisley.py` after a fresh clone to populate rooms.

### 4.2 Files to .gitignore

Make sure your `.gitignore` covers:

```
venv/
__pycache__/
*.pyc
.env
*.sqlite
*.db
*.bak
.DS_Store
patches/*.bak
```

`.DS_Store` is a macOS metadata file that Finder creates everywhere. Add it now so it never pollutes your repo.

### 4.3 Branch Strategy

Even as a solo dev, consider feature branches when working across machines. If you're mid-feature on the desktop and want to do something different on the MacBook:

```bash
git checkout -b feature/space-expansion
# work...
git push -u origin feature/space-expansion
```

On the other machine: `git fetch && git checkout feature/space-expansion`

### 4.4 Path Differences to Watch

Your Python code should already be OS-agnostic since you're using asyncio and aiosqlite, but double-check for any hardcoded Windows paths. The main gotcha:

- `pathlib.Path` works cross-platform — prefer it over string concatenation
- `os.path.join()` also works — it uses the right separator per OS
- Never hardcode `\\` backslashes in file paths

The SQLite database path in your config should use a relative path like `./sw_mush.db` rather than an absolute Windows path.

---

## 5. Performance Expectations — Mac vs. Desktop

| Component | Windows (RTX 3070) | MacBook Air M4 |
|---|---|---|
| Python asyncio server | Fast | Fast (may be slightly faster — M4 is excellent at single-thread) |
| SQLite operations | Fast | Fast |
| Ollama Mistral 7B inference | 30–40 tok/s | 15–25 tok/s (unified memory, no dedicated VRAM) |
| Claude Haiku API calls | Same | Same (network-dependent) |
| Web client (browser) | Same | Same |
| Simultaneous load (server + Ollama + VS Code + browser) | Comfortable (32GB RAM typical) | Fine with 24GB, tight with 16GB |

The MacBook Air has no fan. Under sustained Ollama inference it will throttle slightly, but NPC dialogue calls are short bursts — you won't hit thermal limits in normal development.

---

## 6. Quick Reference — Daily Commands

```bash
# Start of session on Mac
sw                              # cd + activate venv (if you set up the alias)
git pull                        # get latest from the other machine
python3 main.py                 # start server

# Start of session on Windows
cd C:\projects\SW_MUSH
venv\Scripts\activate
git pull
python main.py

# End of session (either machine)
git add .
git commit -m "description of changes"
git push

# Check Ollama status
ollama list                     # see installed models
curl http://localhost:11434/api/tags   # same as @ai status pings
```

---

## 7. Troubleshooting

**"python3: command not found" on Mac** — You didn't install Python via Homebrew, or Homebrew's path isn't in your shell. Run `brew install python@3.12` and restart Terminal.

**"pip install fails with externally-managed-environment"** — You're trying to install outside a venv. Activate it first: `source venv/bin/activate`.

**Ollama returns errors on Mac** — Make sure the Ollama app is running (check the menu bar for the llama icon). Run `ollama serve` manually if the background service isn't started.

**"Permission denied" on scripts** — macOS may block downloaded scripts. Run `chmod +x script.py` or prefix with `python3`.

**Git shows every file as modified** — Line ending issue. Make sure `.gitattributes` is committed and run `git checkout -- .` to reset.

**SQLite "database is locked"** — Two server instances running. Check with `lsof -i :4000` and kill the stale process.

**VS Code Python interpreter wrong** — Cmd+Shift+P → "Python: Select Interpreter" → choose the one in your `venv/bin/python3`.

---

*Guide version 1.0 — April 2026*
*For SW_MUSH architecture v20, Python 3.x, Ollama + Claude Haiku dual-AI stack*
