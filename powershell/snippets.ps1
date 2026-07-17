#######################################################################
####### Get PS version ################################################
#######################################################################

$PSVersionTable

#######################################################################
####### SHA 256 #######################################################
#######################################################################

CertUtil -hashfile [path] SHA256
Get-FileHash .\* -Algorithm SHA256 | Format-List # Hash all files in dir

#######################################################################
####### Set Execution Policy without admin ############################
#######################################################################

Set-ExecutionPolicy -Scope CurrentUser Bypass

#######################################################################
####### Spawn new process #############################################
#######################################################################

Start-Process -FilePath "powershell"

#######################################################################
####### Allow script execution ########################################
#######################################################################

Set-ExecutionPolicy Unrestricted -Scope Process

#######################################################################
####### Hash file #####################################################
#######################################################################

certutil.exe -hashfile [path] SHA256

#######################################################################

## Check Windows version

# Method 1: Simple Product Name
(Get-ComputerInfo).WindowsProductName

# Method 2: Registry (shows ReleaseId, ProductName, EditionID, DisplayVersion, ...)
(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion').ReleaseId

# Method 3: Detailed Licensing (best for edition)
slmgr /dlv

#######################################################################


## Activate Python virtual environment
powershell.exe -ExecutionPolicy Bypass -File .\venv\Scripts\Activate.ps1 

#######################################################################

## List all envrionment variables
Get-ChildItem Env:

#######################################################################


