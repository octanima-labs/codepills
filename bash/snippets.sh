# ### ID: sh0001 ###
# Title: Linux version ID
# Description: Print distribution name, architecture, release version, and kernel version.
# Tags:
# - linux
# - system-info
# - clipboard
# Platforms:
# - Linux

# [name] [arch] [os-version] [kernel-version]
source /etc/os-release && echo "$PRETTY_NAME $(uname -m) $VERSION, $(uname -r)" | tee /tmp/cp.txt &&  xclip /tmp/cp.txt -selection clipboard


# ### ID: sh0002 ###
# Title: Concatenating commands
# Description: Branch shell execution based on command success or failure with && and ||.
# Tags:
# - bash
# - control-flow
# - errors
# Platforms:
# - Linux
# - macOS

# You don't need to test if $? is not 0. The shell provides && and || so you can easily branch based on implicit result of that test:

some_command && {
    # executes this block of code,
    # if some_command would result in:  $? -eq 0
} || {
    # executes this block of code,
    # if some_command would result in:  $? -ne 0
}

# Remove either branch, depending on what you want. E.g. just test failure (i.e. $? -ne 0):

some_command_returning_nonzero || {
    # executes this block of code when:     $? -ne 0
    # and nothing if the command succeeds:  $? -eq 0
}


# ### ID: sh0003 ###
# Title: Zsh interactive comments
# Description: Enable comments in an interactive Z shell session.
# Tags:
# - zsh
# - shell
# - comments
# Platforms:
# - Linux
# - macOS

# Comments in Z Shell: https://apple.stackexchange.com/questions/405246/zsh-comment-character
setopt interactivecomments


# ### ID: sh0004 ###
# Title: Bash for loop
# Description: Iterate over shell array items and run a command for each item.
# Tags:
# - bash
# - loop
# - arrays
# Platforms:
# - Linux
# - macOS

endpoints=(
"value-1"
"value-2"
"value-3"
)
for i in ${items[@]}; do
	cmd $i
	echo "================================"
done


# ### ID: sh0005 ###
# Title: Bash fail-safe mode
# Description: Stop shell execution on errors, unset variables, and failed pipeline commands.
# Tags:
# - bash
# - safety
# - errors
# Platforms:
# - Linux
# - macOS

# https://gist.github.com/mohanpedala/1e2ff5661761d3abd0385e8223e16425?permalink_comment_id=3935570
set -euo pipefail


# ### ID: sh0006 ###
# Title: Generate RSA key pair
# Description: Generate an RSA private key and export the matching public key.
# Tags:
# - openssl
# - rsa
# - keys
# Platforms:
# - Linux
# - macOS

openssl genrsa | tee private.pem && openssl rsa -in private.pem -pubout -out public.pem && cat public.pem


# ### ID: sh0007 ###
# Title: Frozen VM directories
# Description: Create a standard project evidence directory tree for a frozen virtual machine.
# Tags:
# - linux
# - directories
# - vm
# Platforms:
# - Linux

# Crea la estructura de las carpetas para hacer _"frozen"_
sudo bash -c "mkdir -p /PROJECT/$(hostname | cut -f1,2,3 -d- | tr '-' '_')/EVIDENCIAS\ LABORATORIO/{SOURCES,RESULTS,SAMPLES,TOOLS} /PROJECT/$(hostname | cut -f1,2,3 -d- | tr '-' '_')/{TOE,EXTRA}; chown -R evaluator:evaluator /PROJECT/" 


# ### ID: sh0008 ###
# Title: Change keyboard layout
# Description: Change the keyboard layout in Linux console and X sessions.
# Tags:
# - linux
# - keyboard
# - layout
# Platforms:
# - Linux

loadkeys es # Linux
setxkbmap es # For X


# ### ID: sh0009 ###
# Title: Update Kali archive keyring
# Description: Refresh the Kali archive keyring and APT rolling repository source.
# Tags:
# - kali
# - apt
# - keyring
# Platforms:
# - Linux

sudo wget https://archive.kali.org/archive-keyring.gpg -O /usr/share/keyrings/kali-archive-keyring.gpg
echo "deb http://http.kali.org/kali kali-rolling main contrib non-free non-free-firmware" | sudo tee /etc/apt/sources.list


# ### ID: sh0010 ###
# Title: Add user to Docker group
# Description: Create the docker group and add the current user to it.
# Tags:
# - docker
# - linux
# - users
# Platforms:
# - Linux

sudo groupadd docker
sudo usermod -aG docker $USER


# ### ID: sh0011 ###
# Title: Linux clipboard from terminal
# Description: Install and use xclip to copy terminal output through the X clipboard.
# Tags:
# - linux
# - clipboard
# - xclip
# Platforms:
# - Linux

sudo apt-get install xclip

cat file | xclip

xclip -o

# To paste somewhere else other than an X application, such as a text area of a web page in a browser window, use:

cat file | xclip -selection clipboard

# Consider creating an alias:

alias "c=xclip"
alias "v=xclip -o"

# Terminal 1:
pwd | c

# Terminal 2:
cd `v`
