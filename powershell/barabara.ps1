<#
CODEPILLS-META-BEGIN
schema: codepills.tool/v1
name: barabara
version: 1.0.0
author: octanima-labs
description: Split large files into chunks and join them back with hash verification.
repo: https://github.com/octanima-labs/codepills/blob/main/powershell/barabara.ps1
license: MIT
usage: pwsh -NoProfile -File powershell/barabara.ps1 split PATH
tags:
  - powershell
  - cli
  - files
requires:
  - PowerShell
platforms:
  - Windows
  - Linux
  - macOS
CODEPILLS-META-END
#>

<#
Notes:
    - SPLIT creates a folder like: bigfile.parts
        - chunks are stored inside that folder as: bigfile.part.000, .001, .002 ...
        - split also creates inside that folder: bigfile.sha256
    - JOIN expects the .parts folder (including the original hash) and recreates the file inside it
#>

param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ArgsFromCli
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$script:LogLevels = @{
    error   = 0
    warn    = 1
    success = 2
    info    = 3
    debug   = 4
}

$script:CurrentLogLevel = $script:LogLevels.success

function Write-Log {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet('error', 'warn', 'success', 'info', 'debug')]
        [string]$Level,

        [Parameter(Mandatory = $true)]
        [string]$Message,

        [switch]$NoNewline
    )

    if ($script:LogLevels[$Level] -gt $script:CurrentLogLevel) {
        return
    }

    $prefix = ''
    $color = 'White'

    switch ($Level) {
        'error' {
            $prefix = '[!]'
            $color = 'Red'
        }
        'warn' {
            $prefix = '[-]'
            $color = 'Yellow'
        }
        'success' {
            $prefix = '[+]'
            $color = 'Green'
        }
        'info' {
            $prefix = '[*]'
            $color = 'Cyan'
        }
        'debug' {
            $prefix = '[#]'
            $color = 'Magenta'
        }
    }

    Write-Host "$prefix $Message" -ForegroundColor $color -NoNewline:$NoNewline
}

function Show-Usage {
    Write-Host ""
    Write-Host "Usage:"
    Write-Host "  .\barabara.ps1 [-v|-vv] split [-S|--size X[B|KB|MB|GB|TB]] PATH"
    Write-Host "  .\barabara.ps1 [-v|-vv] join PATH"
    Write-Host ""
    Write-Host "Examples:"
    Write-Host "  .\barabara.ps1 split C:\data\bigfile"
    Write-Host "  .\barabara.ps1 -v split C:\data\bigfile"
    Write-Host "  .\barabara.ps1 split --size 700MB C:\data\bigfile"
    Write-Host "  .\barabara.ps1 -vv join C:\data\bigfile.parts"
    Write-Host "  .\barabara.ps1 join C:\data\bigfile.parts"
    Write-Host ""

}

function Parse-Size {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Text
    )

    $trimmed = $Text.Trim().ToUpperInvariant()

    if ($trimmed -notmatch '^(\d+)(B|KB|MB|GB|TB)$') {
        throw "Invalid size format: '$Text'. Expected something like 1GB, 700MB, 1024KB, etc."
    }

    $value = [int64]$matches[1]
    $unit  = $matches[2]

    switch ($unit) {
        'B'  { return $value }
        'KB' { return $value * 1KB }
        'MB' { return $value * 1MB }
        'GB' { return $value * 1GB }
        'TB' { return $value * 1TB }
        default { throw "Unsupported size unit: '$unit'" }
    }
}

function Format-Bytes {
    param(
        [Parameter(Mandatory = $true)]
        [Int64]$Bytes
    )

    if ($Bytes -ge 1TB) { return "{0:N2} TB" -f ($Bytes / 1TB) }
    if ($Bytes -ge 1GB) { return "{0:N2} GB" -f ($Bytes / 1GB) }
    if ($Bytes -ge 1MB) { return "{0:N2} MB" -f ($Bytes / 1MB) }
    if ($Bytes -ge 1KB) { return "{0:N2} KB" -f ($Bytes / 1KB) }
    return "$Bytes B"
}

function Get-Sha256Hex {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $hash = Get-FileHash -LiteralPath $Path -Algorithm SHA256
    return $hash.Hash.ToUpperInvariant()
}

function Write-HashFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$HashFilePath,

        [Parameter(Mandatory = $true)]
        [string]$OriginalFileName,

        [Parameter(Mandatory = $true)]
        [string]$Sha256
    )

    $content = @(
        "# barabara SHA256 file"
        "File=$OriginalFileName"
        "SHA256=$Sha256"
    )

    Set-Content -LiteralPath $HashFilePath -Value $content -Encoding ASCII
}

function Read-HashFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$HashFilePath
    )

    if (-not (Test-Path -LiteralPath $HashFilePath -PathType Leaf)) {
        throw "Hash file not found: $HashFilePath"
    }

    $lines = Get-Content -LiteralPath $HashFilePath -Encoding ASCII
    $fileName = $null
    $sha256 = $null

    foreach ($line in $lines) {
        if ($line -match '^File=(.*)$') {
            $fileName = $matches[1]
            continue
        }
        if ($line -match '^SHA256=([0-9A-Fa-f]{64})$') {
            $sha256 = $matches[1].ToUpperInvariant()
            continue
        }
    }

    if (-not $fileName) {
        throw "Hash file is invalid: missing File= entry in $HashFilePath"
    }

    if (-not $sha256) {
        throw "Hash file is invalid: missing SHA256= entry in $HashFilePath"
    }

    return @{
        FileName = $fileName
        SHA256   = $sha256
    }
}

function Split-File {
    param(
        [Parameter(Mandatory = $true)]
        [string]$InputPath,

        [Parameter(Mandatory = $true)]
        [Int64]$ChunkSize
    )

    $resolvedInput = (Resolve-Path -LiteralPath $InputPath).Path

    if (-not (Test-Path -LiteralPath $resolvedInput -PathType Leaf)) {
        throw "Input file not found: $InputPath"
    }

    if ($ChunkSize -le 0) {
        throw "Chunk size must be greater than 0."
    }

    $fileItem = Get-Item -LiteralPath $resolvedInput
    $fileSize = [int64]$fileItem.Length
    $partsDir = "$resolvedInput.parts"
    $hashFilePath = Join-Path -Path $partsDir -ChildPath "$($fileItem.Name).sha256"

    if (Test-Path -LiteralPath $partsDir) {
        $response = Read-Host "[?] Output folder already exists: $partsDir`nDelete it and continue? [y/N]"
        if ($response -match '^(?i:y|yes)$') {
            Remove-Item -LiteralPath $partsDir -Recurse -Force
        }
        else {
            throw "Delete or rename previous output"
        }
    }

    Write-Log -Level info -Message "Slicing file ($(Format-Bytes $fileSize)): $resolvedInput"
    Write-Log -Level debug -Message "Chunk size: $(Format-Bytes $ChunkSize)"
    Write-Log -Level debug -Message "Output folder: $partsDir"

    New-Item -ItemType Directory -Path $partsDir | Out-Null

    try {
        Write-Log -Level info -Message "Hashing file..."
        $originalHash = Get-Sha256Hex -Path $resolvedInput

        Write-Log -Level success -Message "Original SHA-256: $originalHash"
        
        Write-HashFile -HashFilePath $hashFilePath -OriginalFileName $fileItem.Name -Sha256 $originalHash

        $bufferSize = 4MB
        if ($bufferSize -gt $ChunkSize) {
            $bufferSize = [int]$ChunkSize
        }
        if ($bufferSize -le 0) {
            $bufferSize = 1MB
        }

        $inputStream = [System.IO.File]::OpenRead($resolvedInput)
        $partIndex = 0
        $bytesRemaining = $fileSize
        $totalWritten = [int64]0

        try {
            while ($bytesRemaining -gt 0) {
                $partFileName = "$($fileItem.Name).part.{0:D3}" -f $partIndex
                $partPath = Join-Path -Path $partsDir -ChildPath $partFileName
                $bytesToWriteThisPart = [Math]::Min($ChunkSize, $bytesRemaining)

                $outputStream = [System.IO.File]::Create($partPath)
                $writtenThisPart = [int64]0

                try {
                    $buffer = New-Object byte[] $bufferSize

                    while ($writtenThisPart -lt $bytesToWriteThisPart) {
                        $remainingForThisPart = $bytesToWriteThisPart - $writtenThisPart
                        $toRead = [Math]::Min($buffer.Length, $remainingForThisPart)

                        $read = $inputStream.Read($buffer, 0, [int]$toRead)
                        if ($read -le 0) {
                            throw "Unexpected end of file while slicing."
                        }

                        $outputStream.Write($buffer, 0, $read)
                        $writtenThisPart += $read
                        $totalWritten += $read

                        $percent = [math]::Round(($totalWritten / $fileSize) * 100)
                        Write-Progress -Id 0 -Activity "Slicing" -Status "Chunk $($partIndex + 1) - $(Format-Bytes $totalWritten) / $(Format-Bytes $fileSize)" -PercentComplete $percent
                    }
                }
                finally {
                    $outputStream.Close()
                }

                $bytesRemaining -= $writtenThisPart
                $partIndex++
            }

            Write-Progress -Id 0 -Activity "Slicing" -Completed
            Write-Log -Level success -Message "All chunks written."
            Write-Log -Level success -Message "File sliced successfully."
        }
        finally {
            $inputStream.Close()
        }

        Write-Log -Level debug -Message "Saving original hash"
        Write-Log -Level info -Message "$partIndex chunk(s) generated ($partsDir)"
    }
    catch {
        Write-Log -Level warn -Message "Slice failed. Removing incomplete output folder: $partsDir"
        if (Test-Path -LiteralPath $partsDir) {
            Remove-Item -LiteralPath $partsDir -Recurse -Force -ErrorAction SilentlyContinue
        }
        throw
    }
}

function Join-File {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PartsDirPath
    )

    $resolvedPartsDir = (Resolve-Path -LiteralPath $PartsDirPath).Path

    if (-not (Test-Path -LiteralPath $resolvedPartsDir -PathType Container)) {
        throw "Parts folder not found: $PartsDirPath"
    }

    $partsDirName = Split-Path -Path $resolvedPartsDir -Leaf
    if ($partsDirName -notmatch '^(.*)\.parts$') {
        throw "Input must be a folder ending in .parts, for example: bigfile.zip.parts"
    }

    $baseFileName = $matches[1]
    $hashFilePath = Join-Path -Path $resolvedPartsDir -ChildPath "$baseFileName.sha256"
    $outputPath = Join-Path -Path $resolvedPartsDir -ChildPath $baseFileName

    Write-Log -Level debug -Message "Using parts folder: $resolvedPartsDir"
    
    $hashInfo = Read-HashFile -HashFilePath $hashFilePath
    $expectedHash = $hashInfo.SHA256

    if ($hashInfo.FileName -ne $baseFileName) {
        throw "Hash file refers to '$($hashInfo.FileName)' but parts folder name implies '$baseFileName'"
    }

    $chunkFiles = @(
        Get-ChildItem -LiteralPath $resolvedPartsDir -File |
            Where-Object { $_.Name -match ('^{0}\.part\.(\d+)$' -f [Regex]::Escape($baseFileName)) } |
            Sort-Object Name
    )

    if (-not $chunkFiles -or $chunkFiles.Count -eq 0) {
        throw "No chunk files found in folder: $resolvedPartsDir"
    }
    
    $expectedIndex = 0
    foreach ($chunk in $chunkFiles) {
        if ($chunk.Name -notmatch '\.part\.(\d+)$') {
            throw "Invalid chunk name encountered: $($chunk.FullName)"
        }

        $actualIndex = [int]$matches[1]
        if ($actualIndex -ne $expectedIndex) {
            throw "Missing or out-of-order chunk. Expected index $expectedIndex but found $actualIndex ($($chunk.Name))"
        }

        $expectedIndex++
    }

    if (Test-Path -LiteralPath $outputPath) {
        $response = Read-Host "[?] Output file already exists: $outputPath`nDelete it and continue? [y/N]"
        if ($response -match '^(?i:y|yes)$') {
            Remove-Item -LiteralPath $outputPath -Force
        }
        else {
            throw "Delete or rename previous output"
        }
    }

    Write-Log -Level info -Message "Joining $($chunkFiles.Count) chunk(s)..."

    $outputStream = [System.IO.File]::Create($outputPath)
    $totalWritten = [int64]0
    $bufferSize = 4MB

    try {
        for ($index = 0; $index -lt $chunkFiles.Count; $index++) {
            $chunk = $chunkFiles[$index]
            $percent = [math]::Round((($index + 1) / $chunkFiles.Count) * 100)
            Write-Progress -Id 0 -Activity "Joining..." -Status "Chunk $($index + 1) / $($chunkFiles.Count)" -PercentComplete $percent

            $inputStream = [System.IO.File]::OpenRead($chunk.FullName)
            try {
                $buffer = New-Object byte[] $bufferSize

                while (($read = $inputStream.Read($buffer, 0, $buffer.Length)) -gt 0) {
                    $outputStream.Write($buffer, 0, $read)
                    $totalWritten += $read
                }
            }
            finally {
                $inputStream.Close()
            }
        }
        Write-Progress -Id 0 -Activity "Joining..." -Completed
        Write-Log -Level success -Message "File reassembled"
    }
    catch {
        if (Test-Path -LiteralPath $outputPath) {
            Remove-Item -LiteralPath $outputPath -Force -ErrorAction SilentlyContinue
        }
        throw
    }
    finally {
        $outputStream.Close()
    }

    Write-Log -Level info -Message "Hashing file..."
    $actualHash = Get-Sha256Hex -Path $outputPath

    Write-Log -Level debug -Message "Reassembled SHA-256: $actualHash"
    Write-Log -Level debug -Message "Expected    SHA-256: $expectedHash"
    if ($actualHash -ne $expectedHash) {
        throw "Integrity check failed. Expected SHA-256 $expectedHash but got $actualHash"
    }

    Write-Log -Level success -Message "Integrity check passed"
    Write-Log -Level success -Message "Join complete ($(Format-Bytes $totalWritten)): $outputPath"
    
}

function Main {
    param(
        [string[]]$CliArgs
    )

    if (-not $CliArgs -or $CliArgs.Count -eq 0) {
        Show-Usage
        exit 1
    }

    if ($CliArgs[0] -eq '-v') {
        $script:CurrentLogLevel = $script:LogLevels.info
        if ($CliArgs.Count -gt 1) {
            $CliArgs = $CliArgs[1..($CliArgs.Count - 1)]
        }
        else {
            $CliArgs = @()
        }
    }
    elseif ($CliArgs[0] -eq '-vv') {
        $script:CurrentLogLevel = $script:LogLevels.debug
        if ($CliArgs.Count -gt 1) {
            $CliArgs = $CliArgs[1..($CliArgs.Count - 1)]
        }
        else {
            $CliArgs = @()
        }
    }

    if (-not $CliArgs -or $CliArgs.Count -eq 0) {
        Show-Usage
        exit 1
    }

    $command = $CliArgs[0].ToLowerInvariant()

    switch ($command) {
        'split' {
            $sizeText = "1GB"
            $path = $null
            $i = 1

            while ($i -lt $CliArgs.Count) {
                $arg = $CliArgs[$i]

                switch ($arg) {
                    '-S' {
                        $i++
                        if ($i -ge $CliArgs.Count) {
                            throw "Missing value after -S"
                        }
                        $sizeText = $CliArgs[$i]
                    }
                    '--size' {
                        $i++
                        if ($i -ge $CliArgs.Count) {
                            throw "Missing value after --size"
                        }
                        $sizeText = $CliArgs[$i]
                    }
                    default {
                        if ($path) {
                            throw "Unexpected extra argument: $arg"
                        }
                        $path = $arg
                    }
                }

                $i++
            }

            if (-not $path) {
                throw "Missing PATH for split command."
            }

            $chunkSize = Parse-Size -Text $sizeText
            Split-File -InputPath $path -ChunkSize $chunkSize
        }

        'join' {
            if ($CliArgs.Count -ne 2) {
                throw "Usage: .\barabara.ps1 join PATH"
            }

            $path = $CliArgs[1]
            Join-File -PartsDirPath $path
        }

        '-h' { Show-Usage }
        '--help' { Show-Usage }
        'help' { Show-Usage }

        default {
            throw "Unknown command: $command"
        }
    }
}

try {
    Main -CliArgs $ArgsFromCli
}
catch {
    Write-Log -Level error -Message $_.Exception.Message
    exit 1
}
