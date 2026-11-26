# Execute the packaged diagnostic as a disposable non-administrator on the Windows CI runner.
param([Parameter(Mandatory=$true)][string]$Candidate,
      [Parameter(Mandatory=$true)][string]$Mode,
      [Parameter(Mandatory=$true)][string]$Report)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($Mode -notin @('--diagnostics','--live-self-test')) { throw 'Invalid diagnostic mode' }
$Candidate = (Resolve-Path -LiteralPath $Candidate).Path
$Report = [System.IO.Path]::GetFullPath($Report)
$id = [Guid]::NewGuid().ToString('N').Substring(0,12)
$user = "PDFTest_$id"
$root = Join-Path $env:ProgramData "PDFResearchCI-$id"
$created = $false
$proc = $null
$raw = [Guid]::NewGuid().ToString('N') + 'aA1!'
$secret = ConvertTo-SecureString $raw -AsPlainText -Force
$raw = $null
try {
    $account = New-LocalUser -Name $user -Password $secret -Description 'Disposable standard user for PDF Research Engine CI' -AccountNeverExpires
    $created = $true
    $sid = $account.SID.Value
    $users = Get-LocalGroup -SID 'S-1-5-32-545'
    if (-not (Get-LocalGroupMember -Group $users.Name | Where-Object { $_.SID.Value -eq $sid })) {
        Add-LocalGroupMember -Group $users.Name -Member $account
    }
    $admins = Get-LocalGroup -SID 'S-1-5-32-544'
    if (Get-LocalGroupMember -Group $admins.Name | Where-Object { $_.SID.Value -eq $sid }) { throw 'CI test account is unexpectedly an administrator' }
    New-Item -ItemType Directory -Path $root | Out-Null
    & icacls.exe $root /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' "*$($sid):(OI)(CI)RX" | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Failed to set isolated CI test directory permissions' }
    $out = Join-Path $root 'output'
    New-Item -ItemType Directory -Path $out | Out-Null
    & icacls.exe $out /grant:r "*$($sid):(OI)(CI)M" | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Failed to set CI report directory permissions' }
    $testExe = Join-Path $root 'PDFResearchEngine.exe'
    Copy-Item -LiteralPath $Candidate -Destination $testExe
    if ((Get-FileHash -LiteralPath $testExe).Hash -ne (Get-FileHash -LiteralPath $Candidate).Hash) { throw 'CI executable copy mismatch' }
    $reportFile = Join-Path $out 'diagnostics.json'
    if ((Get-Service -Name seclogon).Status -ne 'Running') { Start-Service -Name seclogon }
    $credential = [PSCredential]::new("$env:COMPUTERNAME\$user",$secret)
    Write-Host 'Launching exact compiled executable as a disposable standard user.'
    $proc = Start-Process -FilePath $testExe -ArgumentList @($Mode, ('"' + $reportFile + '"')) -Credential $credential -LoadUserProfile -WorkingDirectory $root -PassThru
    if (-not $proc.WaitForExit(900000)) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue; throw 'Standard-user diagnostic timed out' }
    $proc.Refresh()
    if (Test-Path -LiteralPath $reportFile) { Copy-Item -LiteralPath $reportFile -Destination $Report -Force; Get-Content -Raw -LiteralPath $Report | Write-Host }
    if ($proc.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $Report)) { throw "Standard-user diagnostic failed (exit $($proc.ExitCode))" }
    if ((Get-Content -Raw -LiteralPath $Report | ConvertFrom-Json).status -ne 'passed') { throw 'Standard-user diagnostic report did not pass' }
    Write-Host 'Standard-user packaged diagnostic passed.'
} finally {
    if ($null -ne $proc) { $proc.Dispose() }
    if ($created) { Remove-LocalUser -Name $user -ErrorAction SilentlyContinue }
    if (Test-Path -LiteralPath $root) { Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue }
}
