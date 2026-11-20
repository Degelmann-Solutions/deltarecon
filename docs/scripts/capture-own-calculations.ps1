# Renews the Windows captures of the page "Your own calculations on the
# reference model": runs the commands the present capture files name, in
# their order, and writes each step's file anew, in UTF-8 with LF line ends.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File capture-own-calculations.ps1 -Source <folder> -Target <folder>
#
# Run it in Windows PowerShell in the package folder of the released package,
# unpacked into a fresh folder, after `.\quickstart.cmd --lang en --no-pause`.
# The source folder is a copy of `src\captures\v<version>\own-calculations\`;
# the target folder must not exist. `order.txt` of the source folder names
# the steps in the order they run; `<step>-windows.txt` holds, per command,
# the line `command: <as typed>`, its output (standard output and standard
# error), and the line `exit status: <n>`. Only the `command:` lines are
# read. Every command runs in this session, as a reader types it, so a
# variable of one step is there in the next.
param(
  [Parameter(Mandatory = $true)][string]$Source,
  [Parameter(Mandatory = $true)][string]$Target
)
$ErrorActionPreference = 'Continue'
if (-not (Test-Path -LiteralPath (Join-Path $Source 'order.txt'))) {
  [Console]::Error.WriteLine('capture-own-calculations: no order.txt in the source folder')
  exit 2
}
if (Test-Path -LiteralPath $Target) {
  [Console]::Error.WriteLine('capture-own-calculations: the target folder exists already')
  exit 2
}
New-Item -ItemType Directory -Path $Target | Out-Null
$captureTarget = (Resolve-Path -LiteralPath $Target).Path
$captureEncoding = New-Object System.Text.UTF8Encoding($false)

foreach ($captureStep in Get-Content -LiteralPath (Join-Path $Source 'order.txt')) {
  if ($captureStep.Trim() -eq '') { continue }
  $captureLines = New-Object System.Collections.Generic.List[string]
  foreach ($captureEntry in Get-Content -LiteralPath (Join-Path $Source "$captureStep-windows.txt") -Encoding UTF8) {
    if (-not $captureEntry.StartsWith('command: ')) { continue }
    $captureCommand = $captureEntry.Substring(9)
    $captureLines.Add("command: $captureCommand")
    $global:LASTEXITCODE = 0
    $captureStatus = $null
    try {
      # The block runs in this scope (dot-sourced), so that a variable the
      # command sets stays, and its error stream joins its output.
      $captureOutput = Invoke-Expression ". { $captureCommand } 2>&1"
    } catch {
      $captureOutput = $_
      $captureStatus = 1
    }
    foreach ($captureItem in $captureOutput) {
      if ($captureItem -is [System.Management.Automation.ErrorRecord]) {
        $captureLines.Add($captureItem.Exception.Message)
      } else {
        $captureLines.Add("$captureItem")
      }
    }
    if ($null -eq $captureStatus) { $captureStatus = $LASTEXITCODE }
    $captureLines.Add("exit status: $captureStatus")
  }
  [System.IO.File]::WriteAllText(
    (Join-Path $captureTarget "$captureStep-windows.txt"),
    (($captureLines -join "`n") + "`n"),
    $captureEncoding)
  [Console]::Out.WriteLine("capture-own-calculations: $captureStep written")
}
