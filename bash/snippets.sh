# Linux version ID
# [name] [arch] [os-version] [kernel-version]
source /etc/os-release && echo "$PRETTY_NAME $(uname -m) $VERSION, $(uname -r)" | tee /tmp/cp.txt &&  xclip /tmp/cp.txt -selection clipboard

########################################################

## CONCATENATING COMMANDS

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

########################################################

# Comments in Z Shell: https://apple.stackexchange.com/questions/405246/zsh-comment-character
setopt interactivecomments

########################################################

# FOR LOOPS

endpoints=(
"value-1"
"value-2"
"value-3"
)
for i in ${items[@]}; do
	cmd $i
	echo "================================"
done

########################################################

# FAIL SAFE: Stops the execution upon first error encountered
# https://gist.github.com/mohanpedala/1e2ff5661761d3abd0385e8223e16425?permalink_comment_id=3935570

set -euo pipefail

########################################################

## GENERATE RSA KEY PAIR
openssl genrsa | tee private.pem && openssl rsa -in private.pem -pubout -out public.pem && cat public.pem

########################################################

## FROZEN VM DIRECTORIES

# Crea la estructura de las carpetas para hacer _"frozen"_
sudo bash -c "mkdir -p /PROJECT/$(hostname | cut -f1,2,3 -d- | tr '-' '_')/EVIDENCIAS\ LABORATORIO/{SOURCES,RESULTS,SAMPLES,TOOLS} /PROJECT/$(hostname | cut -f1,2,3 -d- | tr '-' '_')/{TOE,EXTRA}; chown -R evaluator:evaluator /PROJECT/" 


########################################################

## Change keyboard layout
loadkeys es # Linux
setxkbmap es # For X

########################################################

# KALI: Update kali archive keyring and APT sources list

sudo wget https://archive.kali.org/archive-keyring.gpg -O /usr/share/keyrings/kali-archive-keyring.gpg
echo "deb http://http.kali.org/kali kali-rolling main contrib non-free non-free-firmware" | sudo tee /etc/apt/sources.list

########################################################

# Add docker group and user to group

sudo groupadd docker
sudo usermod -aG docker $USER

########################################################

## Linux clipboard from terminal

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

########################################################
