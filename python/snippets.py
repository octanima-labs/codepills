#########################################################

## Input values in multiples lines


def input_multiline():
    lines = []

    while line := input():
        lines.append(line)
    return lines

#########################################################

## Interactive debug shell

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

#########################################################

## Faking a command

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

#########################################################

## Formating strings

# - `!s` (por defecto): Llama a `__str__`, representación legible para el usuario final.
# - `!r`: Llama a `__repr__`, representación técnica del objeto, ideal para desarrolladores
# - `!a`: Llama a `ascii()`,  funciona como repr() pero escapa cualquier carácter que no sea ASCII. 

#########################################################


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