param(
    [Parameter(Mandatory=$true)][ValidateSet('nvidia','amd')][string]$Vendor,
    [string]$InstallRoot
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
if (-not $InstallRoot) { $InstallRoot = Join-Path $PSScriptRoot '../..' }
$root = [IO.Path]::GetFullPath($InstallRoot)
$profiles = Join-Path $root 'portable_config/profiles'
$active = Join-Path $root 'animejanai/animejanai.conf'
$statePath = Join-Path $profiles 'active-bank.json'
function Hash-File([string]$Path) {
    if (Test-Path -LiteralPath $Path -PathType Leaf) { return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash }
    return $null
}
# Serialize activation and saving the Manager's edits across player launches.
$sha = [Security.Cryptography.SHA256]::Create()
$id = ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($root.ToLowerInvariant())))).Replace('-','')
$sha.Dispose()
$mutex = [Threading.Mutex]::new($false, "Local\AnimeJaNaiProfileBank-$id")
$locked = $false
try {
    try { $locked = $mutex.WaitOne(10000) } catch [Threading.AbandonedMutexException] { $locked = $true }
    if (-not $locked) { throw 'Profile bank activation timed out' }
    $selected = Join-Path $profiles "$Vendor/animejanai.conf"
    if (-not (Test-Path -LiteralPath $selected -PathType Leaf)) { throw "Missing profile bank: $selected" }
    $state = $null
    if (Test-Path -LiteralPath $statePath) {
        $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
        if ($state.vendor -notin @('nvidia','amd') -or -not $state.hash) { throw 'Invalid profile bank state' }
    }
    $activeHash = Hash-File $active
    if ($state -and $activeHash -and $activeHash -ne $state.hash) {
        $previous = Join-Path $profiles "$($state.vendor)/animejanai.conf"
        $bankHash = Hash-File $previous
        if ($bankHash -ne $state.hash -and $bankHash -ne $activeHash) {
            throw "Conflicting edits: $active and $previous. Both files are preserved; reconcile them before restarting."
        }
        if ($bankHash -ne $activeHash) { Copy-Item -LiteralPath $active -Destination $previous }
    }
    $selectedHash = Hash-File $selected
    if ($activeHash -ne $selectedHash) { Copy-Item -LiteralPath $selected -Destination $active }
    if (-not $state -or $state.vendor -ne $Vendor -or $state.hash -ne $selectedHash) {
        $json = @{vendor=$Vendor;hash=$selectedHash} | ConvertTo-Json -Compress
        [IO.File]::WriteAllText($statePath, $json, [Text.UTF8Encoding]::new($false))
    }
    @{conf=$active;bank=$selected;vendor=$Vendor} | ConvertTo-Json -Compress
} finally {
    if ($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
