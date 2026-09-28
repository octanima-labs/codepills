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

########################################

function Get-DefaultDNSServer {
    # Execute nslookup against a generic IP to force the header output
    $output = nslookup 1.1.1.1

    # Extract the name and IP based on line position and clean up whitespace
    $name = ($output[0] -split ': ')[-1].Trim()
    $ip   = ($output[1] -split ': ')[-1].Trim()

    # Return a custom object with both properties
    [PSCustomObject]@{
        IP   = $ip
        Name = $name
    }
}

# Hash files in current dir
Get-ChildItem -File | Get-FileHash | Select-Object Hash, @{Name="FileName"; Expression={(Split-Path $_.Path -Leaf)}} | Format-Table -AutoSize

# Get SSL certificate
$targets = @(
    "your-domain.com",
)

foreach ($target in $targets) {
    $tcp = $null
    $ssl = $null

    try {
        $tcp = [System.Net.Sockets.TcpClient]::new($target, 443)
        $ssl = [System.Net.Security.SslStream]::new(
            $tcp.GetStream(),
            $false
        )

        # Uses normal Windows certificate-chain and hostname validation.
        $ssl.AuthenticateAsClient($target)

        [pscustomobject]@{
            Target  = $target
            Trusted = $true
            Subject = $ssl.RemoteCertificate.Subject
            Issuer  = $ssl.RemoteCertificate.Issuer
            Error   = $null
        }
    }
    catch {
        [pscustomobject]@{
            Target  = $target
            Trusted = $false
            Subject = $null
            Issuer  = $null
            Error   = $_.Exception.Message
        }
    }
    finally {
        if ($ssl) { $ssl.Dispose() }
        if ($tcp) { $tcp.Dispose() }
    }
}


# ### ID: ps0010 ###
# Title: grepfile
# Description: Keep regex-matching lines from a file and save them to a clean output file.
# Tags:
# - powershell
# - regex
# - files
# Platforms:
# - Windows
# - Linux
# - macOS

function grepfile {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Pattern,

        [Parameter(Mandatory = $true)]
        [string] $Path,

        [string] $OutputPath
    )

    if (-not $OutputPath) {
        $directory = Split-Path -Path $Path -Parent
        $filename = Split-Path -Path $Path -Leaf
        $stem = [System.IO.Path]::GetFileNameWithoutExtension($filename)
        $extension = [System.IO.Path]::GetExtension($filename)
        $cleanName = "${stem}_clean${extension}"
        $OutputPath = if ($directory) { Join-Path -Path $directory -ChildPath $cleanName } else { $cleanName }
    }

    Select-String -Pattern $Pattern -Path $Path |
        ForEach-Object { $_.Line } |
        Set-Content -Path $OutputPath -Encoding utf8
}


# ### ID: ps0011 ###
# Title: Get AD user
# Description: Query Active Directory for a user by samAccountName and return selected properties as compact JSON.
# Tags:
# - powershell
# - active-directory
# - ldap
# - user
# - json
# Platforms:
# - Windows

function Get-AdUserInfo {
    param(
        [string] $Username = $env:USERNAME
    )

    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8

    $escapedUsername = $Username.Replace('\', '\5c').Replace('*', '\2a').Replace('(', '\28').Replace(')', '\29').Replace([char]0, '\00')
    $searcher = [adsisearcher]"(samAccountName=$escapedUsername)"
    $user = $searcher.FindOne()

    if ($user) {
        [PSCustomObject]@{
            username = $Username
            full_name = [string]$user.Properties.displayname
            initials = [string]$user.Properties.initials
            mail = [string]$user.Properties.mail
        } | ConvertTo-Json -Compress
    } else {
        "NOT_FOUND"
    }
}
