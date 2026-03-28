# Star Wars D6 MUSH - Installation & Setup Guide (Windows)

## Prerequisites

### 1. Install Python 3.11+

Download from: https://www.python.org/downloads/

**IMPORTANT during installation:**
- Check the box **"Add Python to PATH"** on the first screen
- Click "Install Now" (or Customize and ensure pip is included)

Verify after install — open **Command Prompt** (Win+R, type `cmd`, Enter):

```
python --version
```

You should see `Python 3.11.x` or higher. If you see a Microsoft Store prompt
or "not recognized", Python isn't on your PATH. Reinstall with the PATH
checkbox checked.


### 2. Install a MUD Client (for Telnet)

Any of these work:
- **Mudlet** (free, recommended): https://www.mudlet.org/
- **MUSHclient** (free, classic): http://mushclient.com/
- **PuTTY** (free, set to Raw mode): https://www.putty.org/

Or use the Windows built-in telnet client:
1. Open "Turn Windows features on or off"
2. Check "Telnet Client"
3. Then from Command Prompt: `telnet localhost 4000`


---

## Installation

### Step 1: Extract the archive

Extract `sw_mush_complete.tar.gz` to a folder of your choice.
Windows 11 can extract .tar.gz natively. Otherwise use 7-Zip (https://7-zip.org/).

You should have a folder structure like:

```
sw_mush/
├── main.py
├── requirements.txt
├── server/
├── parser/
├── engine/
├── world/
├── space/
├── db/
├── data/
│   ├── skills.yaml
│   └── species/
│       ├── human.yaml
│       ├── wookiee.yaml
│       └── ... (9 species total)
└── tests/
```


### Step 2: Open a terminal in the project folder

Open Command Prompt or PowerShell, then navigate to the extracted folder:

```
cd C:\path\to\sw_mush
```

Or in Windows Explorer: navigate to the `sw_mush` folder, click the address
bar, type `cmd`, and press Enter. This opens a terminal already in that folder.


### Step 3: Create a virtual environment

```
python -m venv venv
```

### Step 4: Activate the virtual environment

**Command Prompt:**
```
venv\Scripts\activate
```

**PowerShell:**
```
venv\Scripts\Activate.ps1
```

If PowerShell gives an "execution policy" error, run this first:
```
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

You should see `(venv)` at the start of your prompt.


### Step 5: Install dependencies

```
pip install -r requirements.txt
```

This installs: telnetlib3, websockets, aiosqlite, bcrypt, pyyaml, pytest

**If bcrypt fails to install** (rare, but possible if C++ build tools are missing):
```
pip install bcrypt --only-binary :all:
```
If that also fails, install Microsoft C++ Build Tools from:
https://visualstudio.microsoft.com/visual-cpp-build-tools/


### Step 6: Run the tests

```
python -m pytest tests/ -v
```

You should see all 107 tests pass. If they do, everything is installed
correctly.


---

## Running the Server

### Start the server

```
python main.py
```

You'll see:

```
    ╔══════════════════════════════════════════════════╗
    ║       ____  _                __    __            ║
    ║      / ___|| |_ __ _ _ __  / / /\ \ \__ _ _ __  ║
    ║      \___ \| __/ _` | '__| \ \/  \/ / _` | '__| ║
    ║       ___) | || (_| | |     \  /\  / (_| | |    ║
    ║      |____/ \__\__,_|_|      \/  \/ \__,_|_|    ║
    ║                                                  ║
    ║            D 6   M U S H   S E R V E R           ║
    ╚══════════════════════════════════════════════════╝

2026-03-20 12:00:00 [INFO   ] ...  Star Wars D6 MUSH is running. Telnet:4000  WebSocket:4001
```

The server creates `sw_mush.db` (SQLite database) on first run with three
seed rooms: Landing Pad, Mos Eisley Street, and Chalmun's Cantina.


### Command-line options

```
python main.py --telnet-port 4000 --ws-port 4001 --db sw_mush.db --log-level DEBUG
```


### Stop the server

Press `Ctrl+C` in the terminal. The server saves all character data and
shuts down gracefully.


---

## Connecting to the Game

### Via Mudlet
1. Open Mudlet
2. Click "New" to create a new profile
3. Server address: `localhost`
4. Port: `4000`
5. Click "Connect"

### Via PuTTY
1. Host Name: `localhost`
2. Port: `4000`
3. Connection type: **Raw** (not SSH)
4. Click "Open"

### Via Windows Telnet
```
telnet localhost 4000
```

### Via WebSocket (for developers)
Connect a WebSocket client to `ws://localhost:4001`
Send JSON: `{"input": "your command here"}`


---

## First Login

When you connect, you'll see:

```
╔══════════════════════════════════════════════╗
║          STAR WARS D6 MUSH                   ║
║   A long time ago in a galaxy far, far away…  ║
╚══════════════════════════════════════════════╝

  Type 'connect <username> <password>' to log in.
  Type 'create <username> <password>' to register.
  Type 'quit' to disconnect.
```

### Create an account
```
create myusername mypassword
```

### Create a character
You'll be prompted to enter a character name. (Full character creation with
species/attributes/skills will be wired in during Phase 2C-2.)

### Basic commands once in-game
```
look                    - Look at your surroundings
north / south / east    - Move (abbreviations: n, s, e, w, u, d)
say Hello everyone!     - Say something to the room
whisper Han = Got a job  - Whisper to another player
emote grins widely      - Perform an emote / pose
who                     - See who's online
sheet                   - View your character sheet
inventory               - Check your inventory
@desc A tall smuggler   - Set your character description
@ooc Anyone there?      - Out-of-character chat to the room
help                    - List all commands
quit                    - Disconnect
```

### Seed world
Three rooms are pre-built and connected:

```
Landing Pad ──north──> Mos Eisley Street ──east──> Chalmun's Cantina
            <──south──                   <──west──
```


---

## Windows Firewall Note

If you want other machines on your network to connect, Windows Firewall
will prompt you to allow Python through when you first run the server.
Click "Allow access" for private networks.

For local-only testing, no firewall changes are needed.


---

## Project Structure

```
sw_mush/
├── main.py                  # Entry point - boots the server
├── requirements.txt         # Python dependencies
├── server/
│   ├── config.py            # All tunables (ports, timeouts, etc.)
│   ├── session.py           # Protocol-agnostic session abstraction
│   ├── game_server.py       # Central orchestrator (login, game loop)
│   ├── telnet_handler.py    # Telnet protocol (port 4000)
│   ├── websocket_handler.py # WebSocket protocol (port 4001)
│   └── ansi.py              # Color codes for terminal output
├── parser/
│   ├── commands.py           # Command framework (base class, registry, dispatcher)
│   └── builtin_commands.py   # 12 built-in commands (look, move, say, etc.)
├── engine/
│   ├── dice.py              # D6 dice engine (pools, Wild Die, checks)
│   ├── species.py           # Species loader and validation
│   ├── character.py         # Character model, skills, wounds, serialization
│   └── creation.py          # Character creation state machine
├── db/
│   └── database.py          # SQLite schema, account ops, room/character queries
├── data/
│   ├── skills.yaml          # 76 skill definitions by attribute
│   └── species/
│       ├── human.yaml       # 9 species YAML files
│       ├── wookiee.yaml
│       ├── twilek.yaml
│       ├── rodian.yaml
│       ├── mon_calamari.yaml
│       ├── bothan.yaml
│       ├── trandoshan.yaml
│       ├── duros.yaml
│       └── sullustan.yaml
├── world/                   # (Future: room/zone management)
├── space/                   # (Future: ship/space combat)
└── tests/
    ├── test_dice.py         # 47 tests - dice engine
    ├── test_species.py      # 17 tests - species loading/validation
    ├── test_character.py    # 26 tests - character model/skills/wounds
    └── test_creation.py     # 17 tests - creation state machine
```


---

## What's Built So Far

### Phase 1 - Server Core
- Dual-protocol server (Telnet + WebSocket)
- Session abstraction (protocol-agnostic)
- Account system (bcrypt password hashing, lockout on failed attempts)
- Command parser with alias expansion and prefix matching
- 12 built-in commands
- SQLite database with WAL mode
- 3 seed rooms with exits

### Phase 2A - D6 Dice Engine
- Dice pools (parse/display "4D+2" notation)
- Wild Die (exploding 6s, complication on 1)
- Difficulty checks, opposed rolls
- Scale system for cross-scale combat
- Multi-action and wound penalties

### Phase 2B - Character Data
- 9 playable species with attribute ranges and special abilities
- 76 skills across 6 attributes with specializations
- Character model with full skill resolution
- Wound tracking (Stunned through Dead, stacking)
- JSON serialization to/from database

### Phase 2C-1 - Character Creation
- Interactive state machine (name → species → attributes → skills → confirm)
- Species info browser, attribute budget validation, skill allocation
- Reset/redo at any step


## What's Next

- **2C-2**: Wire character creation into the game server
- **2D**: Skill check commands (`roll`, `check`)
- **Phase 3+**: Personal combat, NPCs, space combat, Force powers
