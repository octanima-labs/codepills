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
