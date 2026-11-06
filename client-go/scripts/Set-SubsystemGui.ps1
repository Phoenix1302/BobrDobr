param(
    [Parameter(Mandatory=$true)]
    [string]$Path
)

$resolved = Resolve-Path $Path
$bytes = [System.IO.File]::ReadAllBytes($resolved)
$pe = [System.BitConverter]::ToInt32($bytes, 0x3C)
$subPos = $pe + 0x5C
$oldSub = [System.BitConverter]::ToInt16($bytes, $subPos)

Write-Host "File: $resolved"
Write-Host "Current PE Subsystem: $oldSub"

if ($oldSub -ne 2) {
    # 2 = IMAGE_SUBSYSTEM_WINDOWS_GUI
    $bytes[$subPos] = [byte]2
    $bytes[$subPos + 1] = [byte]0
    [System.IO.File]::WriteAllBytes($resolved, $bytes)
    Write-Host "Successfully patched Subsystem to 2 (IMAGE_SUBSYSTEM_WINDOWS_GUI - no console window)!" -ForegroundColor Green
} else {
    Write-Host "Subsystem is already 2 (IMAGE_SUBSYSTEM_WINDOWS_GUI)." -ForegroundColor Yellow
}
