# ### ID: py0001 ###
# Title: Input multiline values
# Description: Read standard input until an empty line and return all entered lines.
# Tags:
# - input
# - stdin
# - cli
# Platforms:
# - Linux
# - macOS
# - Windows

def input_multiline():
    lines = []

    while line := input():
        lines.append(line)
    return lines


# ### ID: py0002 ###
# Title: Interactive debug shell
# Description: Pause execution and evaluate interactive expressions until interrupted.
# Tags:
# - debugging
# - interactive
# - repl
# Platforms:
# - Linux
# - macOS
# - Windows

def debug_shell():
    ind = 0
    print("[#] EXECUTION PAUSED (ctrl + c to continue)")
    while True:
        try:
            print(f"[{ind}] Output:", eval(input(f"[{ind}]  Input: ")))
        except KeyboardInterrupt:
            print("\n[#] EXECUTION RESUMED")
            break
        except Exception as e:
            print(f"[{ind}]  Error: ", e)
        finally:
            ind += 1


# ### ID: py0003 ###
# Title: Fake command prompt
# Description: Render a fake terminal command and expected output for demonstrations.
# Tags:
# - terminal
# - demo
# - color
# Platforms:
# - Linux
# - macOS
# - Windows

def fake_cmd(command, params: list[str] = [], expected_output: str = ''):
    from colorama import Fore, Style
    import os
    import sys
    
    homepath = ''
    prefix = ''
    
    if sys.platform == 'win32':
        prefix = 'PS '
        homepath = os.getenv('USERPROFILE')
        os.system('cls') # Clear screen
    else:
        homepath = os.getenv('HOME')
        os.system('clear') # Clear screen
    print(
        f"{prefix}{homepath}> {Fore.LIGHTYELLOW_EX}{command}{Style.RESET_ALL}{' '.join(params)}",
        expected_output,
        "", "", "", 
        sep='\n\n'
    )
fake_cmd(
    command='date',
    expected_output="miércoles, 25 de febrero de 2026 12:21:09"
)


# ### ID: py0004 ###
# Title: String conversion flags
# Description: Document Python conversion flags for readable, repr, and ASCII string formatting.
# Tags:
# - strings
# - formatting
# - repr
# Platforms:
# - Linux
# - macOS
# - Windows

# - `!s` (por defecto): Llama a `__str__`, representación legible para el usuario final.
# - `!r`: Llama a `__repr__`, representación técnica del objeto, ideal para desarrolladores
# - `!a`: Llama a `ascii()`,  funciona como repr() pero escapa cualquier carácter que no sea ASCII.


# ### ID: py0005 ###
# Title: Formatting and colored output helpers
# Description: Normalize colon-separated text and color status-prefixed terminal messages.
# Tags:
# - formatting
# - ansi
# - terminal
# Platforms:
# - Linux
# - macOS
# - Windows

def format_req(r):
    """Normalize length (adding space padding) then removes brackets (<>) so its easier to read"""
    split = str(r).split(': ', maxsplit=1)
    print(split)
    return f"{'{: <19}{}'.format(*split)}"


def cprint(value: str, quiet: bool = False) -> None | str:
    COLORS = {
        "[*]": "\033[94m",   # light blue
        "[+]": "\033[92m",   # green
        "[-]": "\033[93m",   # yellow
        "[!]": "\033[91m",   # red
        "[#]": "\033[90m",   # grey
        "<<<": "\033[95m",   # purple
    }
    RESET = "\033[0m"

    for prefix, color in COLORS.items():
        if value.strip().startswith(prefix):
            value = f"{color}{value}{RESET}"
            break
    if quiet:
        return value
    else:
        print(value)  # default color
        return None


# ### ID: py0006 ###
# Title: ANSI color print helper
# Description: Print status-prefixed colored messages using ANSI escape sequences without external dependencies.
# Tags:
# - terminal
# - ansi
# - color
# - print
# Platforms:
# - Linux
# - macOS
# - Windows

class Cprint:
    PURPLE = "\033[95m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    RESET = "\033[0m"
    COLORS = [PURPLE, CYAN, GREEN, YELLOW, RED]

    @staticmethod
    def debug(msg: str, **kwargs):
        print(f"{Cprint.PURPLE}[#] {msg}{Cprint.RESET}", **kwargs)

    @staticmethod
    def info(msg: str, **kwargs):
        print(f"{Cprint.CYAN}[*] {msg}{Cprint.RESET}", **kwargs)

    @staticmethod
    def success(msg: str, **kwargs):
        print(f"{Cprint.GREEN}[+] {msg}{Cprint.RESET}", **kwargs)

    @staticmethod
    def warning(msg: str, **kwargs):
        print(f"{Cprint.YELLOW}[-] {msg}{Cprint.RESET}", **kwargs)

    @staticmethod
    def error(msg: str, **kwargs):
        print(f"{Cprint.RED}[!] {msg}{Cprint.RESET}", **kwargs)

    @staticmethod
    def cprint(msg: str, color: str | None = None, **kwargs):
        if color not in Cprint.COLORS:
            print(msg, **kwargs)
            return

        print(f"{color}{msg}{Cprint.RESET}", **kwargs)


# ### ID: py0007 ###
# Title: Safe filename sanitizer
# Description: Sanitize filenames or path components for cross-platform filesystem compatibility.
# Tags:
# - filesystem
# - filename
# - sanitize
# - path
# Platforms:
# - Linux
# - macOS
# - Windows

def safe_filename(
    name: str,
    *,
    file_sep: str = "_",
    dir_sep: str = "-",
    case: str = "lower",
    is_dir: bool = False,
    preserve_ext: bool = True,
    preserve_path: bool = False,
) -> str:
    """Return a cross-platform-safe filename or path.

    Spaces and reserved filesystem characters are replaced with ``file_sep`` for
    files and ``dir_sep`` for directories. When ``preserve_path`` is true, path
    separators are kept and each component is sanitized independently.

    Examples:
        safe_filename("Is This A veRy unSEcurE nAme!?.txt")
        # "is_this_a_very_unsecure_name.txt"

        safe_filename("My Folder", is_dir=True)
        # "my-folder"

        safe_filename("CON.txt")
        # "_con.txt" and emits a warning
    """

    import re
    import warnings

    if not isinstance(name, str):
        raise TypeError("name must be a string")

    if case not in {"lower", "upper", "camel", "snake"}:
        raise ValueError("case must be one of: lower, upper, camel, snake")

    reserved_chars = '<>:"/\\|?*'
    reserved_names = {
        "con",
        "prn",
        "aux",
        "nul",
        *(f"com{i}" for i in range(1, 10)),
        *(f"lpt{i}" for i in range(1, 10)),
    }

    def validate_separator(separator: str, label: str) -> None:
        if not isinstance(separator, str):
            raise TypeError(f"{label} must be a string")
        if not separator:
            raise ValueError(f"{label} cannot be empty")
        if separator in {".", ".."}:
            raise ValueError(f"{label} cannot be '.' or '..'")
        if any(char.isspace() or char in reserved_chars or char == "." for char in separator):
            raise ValueError(f"{label} cannot contain spaces, dots, or reserved path characters")

    validate_separator(file_sep, "file_sep")
    validate_separator(dir_sep, "dir_sep")

    def trim_edges(value: str, separator: str) -> str:
        previous = None
        while value != previous:
            previous = value
            value = value.strip().strip(".")
            if value.startswith(separator):
                value = value[len(separator) :]
            if value.endswith(separator):
                value = value[: -len(separator)]
        return value

    def apply_case(value: str, separator: str) -> str:
        if case == "snake":
            words = [word for word in re.split(r"[\W_]+", value, flags=re.UNICODE) if word]
            return "_".join(word.lower() for word in words)
        if case == "lower":
            return value.lower()
        if case == "upper":
            return value.upper()

        words = [word for word in re.split(r"[\W_]+", value, flags=re.UNICODE) if word]
        return "".join(word[:1].upper() + word[1:].lower() for word in words)

    def sanitize_text(value: str, separator: str, *, allow_empty: bool = False) -> str:
        had_reserved_chars = any(char in reserved_chars for char in value)
        if had_reserved_chars:
            warnings.warn("reserved filename characters were replaced", stacklevel=3)

        value = re.sub(rf"[\s{re.escape(reserved_chars)}]+", separator, value.strip())
        value = re.sub(rf"(?:{re.escape(separator)})+", separator, value)
        value = trim_edges(value, separator)
        value = apply_case(value, separator)
        value = trim_edges(value, "_" if case == "snake" else separator)

        if not value and not allow_empty:
            raise ValueError("sanitized filename is empty")
        return value

    def split_extension(component: str) -> tuple[str, str]:
        if component in {".", ".."}:
            return component, ""
        dot_index = component.rfind(".")
        if dot_index <= 0 or dot_index == len(component) - 1:
            return component, ""
        return component[:dot_index], component[dot_index + 1 :]

    def sanitize_component(component: str, component_is_dir: bool) -> str:
        separator = "_" if case == "snake" else (dir_sep if component_is_dir else file_sep)

        if component_is_dir or not preserve_ext:
            safe = sanitize_text(component, separator)
            stem = safe
            extension = ""
        else:
            stem, extension = split_extension(component)
            stem = sanitize_text(stem, separator)
            extension = sanitize_text(extension, separator, allow_empty=True)
            if case == "camel":
                extension = extension.lower()
            safe = f"{stem}.{extension}" if extension else stem

        if stem.lower() in reserved_names:
            warnings.warn("reserved Windows device name was prefixed with '_'", stacklevel=3)
            stem = f"_{stem}"
            safe = f"{stem}.{extension}" if extension else stem

        if not safe:
            raise ValueError("sanitized filename is empty")
        return safe

    if not preserve_path:
        return sanitize_component(name, is_dir)

    tokens = re.split(r"([/\\]+)", name)
    component_indexes = [index for index, token in enumerate(tokens) if token and not re.fullmatch(r"[/\\]+", token)]
    if not component_indexes:
        raise ValueError("sanitized filename is empty")

    last_component_index = component_indexes[-1]
    sanitized_tokens = []

    for index, token in enumerate(tokens):
        if not token:
            continue
        if re.fullmatch(r"[/\\]+", token):
            sanitized_tokens.append(token)
            continue

        component_is_dir = index != last_component_index or is_dir
        sanitized_tokens.append(sanitize_component(token, component_is_dir))

    return "".join(sanitized_tokens)
