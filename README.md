# Code Pills

Code Pills is a curated collection of standalone scripts and reusable snippets.
The repository is managed with `codepills.py`, a standard-library Python CLI for
checking metadata, searching entries, copying snippets, importing scripts, and
running standalone tools.

## Layout

- `codepills.py`: repository helper CLI.
- `python/`, `bash/`, `powershell/`, `js/`: language-specific scripts.
- `*/snippets.*`: normalized snippet notebooks for each language.

## Quick Start

Run commands from the repository root.

```bash
git clone git@github.com:octanima-labs/codepills.git codepills
cd codepills
python codepills.py check
python codepills.py ensurepath
python codepills.py search
python codepills.py search --type snippet -t linux
python codepills.py search --type script -t python -D
python codepills.py get py0006
python codepills.py run python/pingwave --tests
```

To start a fresh Code Pills collection from this toolset:

```bash
python codepills.py ensurepath
codepills reset --force
git remote add origin <YOUR_REPO_URL>
```

## CLI

After running `python codepills.py ensurepath`, examples can use `codepills`
directly instead of `python codepills.py` in new shell sessions.

### Ensure Path

Install the `codepills` command into the user PATH.

```bash
python codepills.py ensurepath
```

On POSIX systems this makes `codepills.py` executable, creates a
`~/.local/bin/codepills` symlink, and adds `~/.local/bin` to a shell startup file
when needed. On Windows it creates a `codepills.cmd` shim in `%USERPROFILE%\.local\bin`
and adds that directory to the user PATH.

### Reset

Reset the repository into a fresh Code Pills collection.

```bash
codepills reset
codepills reset --force
```

`reset` empties language folders, recreates empty snippet notebooks, removes the
current `.git` directory, and runs `git init`. It keeps `codepills.py`,
`README.md`, and the language folders. It does not configure a remote.

After reset, configure your own remote:

```bash
git remote add origin <YOUR_REPO_URL>
```

Without `--force`, `reset` asks for confirmation with a default No answer.

### Check

Validate standalone script metadata and normalized snippets.

```bash
python codepills.py check
```

### Search

Search scripts and snippets by metadata.

```bash
python codepills.py search [--type script|snippet] [-D] [-n NAME] [-d TEXT] [-t TAG] [-p PLATFORM]
```

- `-n`, `--name`: case-insensitive substring match on name/title.
- `-d`, `--description`: case-insensitive substring match on description.
- `-t`, `--tag`: exact case-insensitive tag match. Can be repeated.
- `-p`, `--platform`: exact case-insensitive platform match. Can be repeated.
- `--type`: restrict results to `script` or `snippet`. Can be repeated.
- `-D`, `--details`: include description and tags columns.

Multiple filters use AND logic.

### Get

Print one or more snippets and copy the same content to the clipboard.

```bash
python codepills.py get py0001
python codepills.py get py0001 sh0001 ps0001
```

Only snippet content is printed and copied; the ID/header metadata is omitted.
When multiple snippets are selected, they are separated by two blank lines.

Clipboard support uses platform commands when available:

- Linux: `wl-copy`, `xclip`, or `xsel`
- macOS: `pbcopy`
- Windows: `clip` or PowerShell `Set-Clipboard`

If clipboard copy fails, the snippet content is still printed.

### Run

Run a standalone script and pass through all remaining arguments.

```bash
python codepills.py run python/pingwave --tests
python codepills.py run python/zipperzero --self-test
python codepills.py run powershell/barabara -h
```

The script reference is `<language>/<name>` with an optional extension. Examples:

- `python/pingwave` or `python/pingwave.py`
- `bash/swap_file` or `bash/swap_file.sh`
- `powershell/barabara` or `powershell/barabara.ps1`

`run` executes standalone scripts only. Snippets are not runnable through this
command, and browser JavaScript snippets/scripts are blocked from CLI execution.

### Import

Import an existing script into the repository and add metadata when needed.

```bash
python codepills.py import /path/to/tool.py
python codepills.py import /path/to/tool.py --name better-name
```

The destination directory is chosen from the file extension:

- `.py` -> `python/`
- `.sh` -> `bash/`
- `.ps1` -> `powershell/`
- `.js` -> `js/`

`--name` is a filename stem only; the original extension is preserved. Existing
destination files are not overwritten.

The generated `repo` metadata is inferred from `git remote origin`. If `origin`
is not configured, `import` fails with a clear error.

## Standalone Script Metadata

Every standalone script must start with a parseable `CODEPILLS-META` header.
If a shebang is present, it must remain the first line and the metadata follows it.

Required fields:

- `schema: codepills.tool/v1`
- `name`
- `version` using `X.Y.Z`
- `author`
- `description`
- `repo`, pointing to the script's public source URL
- `license`
- `usage`
- `tags`
- `requires`
- `platforms`

Run `python codepills.py check` after editing scripts. `check` requires `repo`
to be present, but it does not require the URL to match the current local
`origin`; imported scripts may preserve their original upstream URLs.

## Snippet Format

Snippets live in language-specific `snippets.*` files. Each snippet has a stable
ID, metadata header, and content body.

```python
# ### ID: py0001 ###
# Title: Input multiline values
# Description: Read standard input until an empty line and return all entered lines.
# Tags:
# - input
# - stdin
# Platforms:
# - Linux
# - macOS
# - Windows

def input_multiline():
    ...
```

ID prefixes are language-specific:

- Python: `py0001`
- Bash: `sh0001`
- PowerShell: `ps0001`
- JavaScript: `js0001`

IDs are stable once assigned. When adding a snippet, use the lowest available
number for that language.

## Maintenance

Before committing changes, run:

```bash
python codepills.py check
```

Useful focused checks:

```bash
python python/freezenv.py --tests
python python/zipperzero.py --self-test
python python/pingwave.py --tests
bash -n bash/swap_file.sh
```

Do not execute `bash/swap_file.sh` as a smoke test unless you intentionally want
to modify system swap configuration.
