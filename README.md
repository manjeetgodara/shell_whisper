# how

Type what you want in plain English and get the command.

```
$ how docker apps on same network
 ❯ ● docker network create <network>
     Create a user-defined bridge network
     why: Containers on the same user-defined network can reach each other by container name (built-in DNS).
   ● docker run -d --name <name> --network <network> <image>
   ● docker network connect <network> <container>
   ● docker compose up -d
  ↑/↓ move · enter select · 1-9 jump · q quit   ● read-only ● modifies ▲ destructive
```

Pick a command and `how` asks you to fill in the `<placeholders>`, then runs it, copies it (`c`) or prints it (`p`).

## Install

Install it straight from GitHub (needs Python 3.9+ and Git):

```
pip install git+https://github.com/manjeetgodara/shell_whisper.git
```

With the optional Claude features (Claude re-ranks and writes commands it hasn't seen):

```
pip install "how-cli[ai] @ git+https://github.com/manjeetgodara/shell_whisper.git"
```

To update to the latest version:

```
pip install --upgrade git+https://github.com/manjeetgodara/shell_whisper.git
```

Then try it:

```
how list running containers
```

**From a local copy** (if you cloned the repo to edit the code):

```
pip install -e .            # offline mode, no dependencies
pip install -e ".[ai]"      # with the optional Claude features
```

If your terminal can't find `how` after installing, add the folder that pip's warning names to your PATH, or run it as `python -m how ...`.

## Share it with someone else

**Send the file.** Build a single install file:

```
python -m pip wheel . --no-deps -w dist
```

Send them `dist/how_cli-<version>-py3-none-any.whl`. They install it with:

```
pip install how_cli-<version>-py3-none-any.whl
```

For an update, bump `version` in `pyproject.toml`, rebuild, and send the new file. They reinstall it with `--upgrade` added.

**Install from GitHub (best for a team).** Push this folder to a repo, leaving out `dist/`, `*.egg-info/` and `__pycache__/`. Anyone can then install it with:

```
pip install git+https://github.com/manjeetgodara/shell_whisper.git
```

Run the same command with `--upgrade` to get the latest version.

**Copy the folder (for people who'll edit the code).** Zip the project without `dist/` and `*.egg-info/`. They unzip it, open a terminal in the folder, and run `pip install -e .`. Their code changes take effect without reinstalling.

**What doesn't carry over:**
- Learned tools, self-heal notes and usage history are stored per person in `~/.how/`, so each person starts fresh. They can run `how learn <tool>` themselves, or you can send them your `~/.how/learned.json` to put in their own `~/.how/` folder.
- Claude ranking is optional and needs each person's own setup: `pip install anthropic` and their own `ANTHROPIC_API_KEY`. Don't share your key.

## Commands

| | |
|---|---|
| `how <anything>` | Search, pick with the arrow keys, run |
| `how learn <tool>` | Read `<tool> --help` recursively and learn every subcommand |
| `how tools` | List the tools `how` has learned |
| `how forget <tool>` | Drop a learned tool |
| `how heals` | Show what `how` learned from failed commands |
| `how -p <query>` | Print the best match only, for scripts |
| `--ai` / `--no-ai` | Force Claude on or off |

## How it works

- **Search** runs offline. It uses BM25 over a built-in set of about 90 commands (docker, git, kubectl, files, network, processes) plus every tool you've taught it. It understands synonyms ("delete" also matches rm and prune) and ranks the commands you pick often higher.
- **`learn`** runs `<tool> --help`, finds the command listings (cobra, docker, argparse and git styles), and recurses into subcommands in parallel (`--depth`, default 3). It turns the `Usage:` line into a template with required positionals as `<placeholders>`. Flags marked `(required)` are added too.
- **Risk** is inferred from the command itself: verbs (`list`/`view` vs. `create`/`push` vs. `delete`/`prune`), dangerous flags (`--force`, `--hard`, `-rf`), and the description as a fallback. A command that changes state asks `[Y/n]`. A destructive one makes you type `yes`.
- **Self-heal**: when a command fails, `how` reads the error. It recognises cobra (`required flag(s) "title" not set`), argparse, click, docker (`requires exactly 1 argument`), and gh (`must provide --title`). It remembers the missing parameter against that command and offers to retry with it filled in. Next time, the parameter is part of the template.
- **Claude** (optional): if the `anthropic` package is installed and `ANTHROPIC_API_KEY` is set, Claude re-ranks the local matches and can suggest commands `how` doesn't know yet. Any error falls back to the offline ranking. Set `HOW_MODEL` to change the model, or `HOW_NO_AI=1` to turn it off.

Data lives in `~/.how/` (override with `HOW_HOME`): `learned.json`, `heal.json` and `usage.json`.
