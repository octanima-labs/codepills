# ### ID: ps0001 ###
# Title: Get PowerShell version
# Description: Print the current PowerShell version table.
# Tags:
# - powershell
# - version
# - diagnostics
# Platforms:
# - Windows
# - Linux
# - macOS

$PSVersionTable


# ### ID: ps0002 ###
# Title: SHA256 file hashes
# Description: Calculate SHA256 hashes for one file or all files in the current directory.
# Tags:
# - hash
# - sha256
# - files
# Platforms:
# - Windows

CertUtil -hashfile [path] SHA256
Get-FileHash .\* -Algorithm SHA256 | Format-List # Hash all files in dir


# ### ID: ps0003 ###
# Title: Set execution policy for current user
# Description: Allow script execution for the current user without requiring administrator scope.
# Tags:
# - powershell
# - execution-policy
# - scripts
# Platforms:
# - Windows

Set-ExecutionPolicy -Scope CurrentUser Bypass


# ### ID: ps0004 ###
# Title: Spawn PowerShell process
# Description: Start a new PowerShell process from the current session.
# Tags:
# - powershell
# - process
# - shell
# Platforms:
# - Windows

Start-Process -FilePath "powershell"


# ### ID: ps0005 ###
# Title: Allow script execution in process
# Description: Temporarily set unrestricted script execution for the current PowerShell process.
# Tags:
# - powershell
# - execution-policy
# - scripts
# Platforms:
# - Windows

Set-ExecutionPolicy Unrestricted -Scope Process


# ### ID: ps0006 ###
# Title: Hash a file
# Description: Calculate a SHA256 hash for a selected file with certutil.
# Tags:
# - hash
# - sha256
# - files
# Platforms:
# - Windows

certutil.exe -hashfile [path] SHA256


# ### ID: ps0007 ###
# Title: Check Windows version
# Description: Query Windows version and licensing information through PowerShell and system tools.
# Tags:
# - windows
# - version
# - diagnostics
# Platforms:
# - Windows

# Method 1: Simple Product Name
(Get-ComputerInfo).WindowsProductName

# Method 2: Registry (shows ReleaseId, ProductName, EditionID, DisplayVersion, ...)
(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion').ReleaseId

# Method 3: Detailed Licensing (best for edition)
slmgr /dlv


# ### ID: ps0008 ###
# Title: Activate Python virtual environment
# Description: Activate a Python virtual environment from PowerShell with a bypassed execution policy.
# Tags:
# - python
# - virtualenv
# - powershell
# Platforms:
# - Windows

powershell.exe -ExecutionPolicy Bypass -File .\venv\Scripts\Activate.ps1 


# ### ID: ps0009 ###
# Title: List environment variables
# Description: Print all environment variables visible to the PowerShell session.
# Tags:
# - powershell
# - environment
# - diagnostics
# Platforms:
# - Windows
# - Linux
# - macOS

Get-ChildItem Env:
