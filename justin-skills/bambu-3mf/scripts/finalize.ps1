# finalize.ps1 x1.0 -- bambu-3mf skill. Run on the Windows PC that has Bambu Studio.
# Purpose: turn the generated 3MF into a Bambu-authored project with the FULL project_settings
# (machine + process + every filament), then slice every plate to prove it, then render plate PNGs.
#
#   powershell -ExecutionPolicy Bypass -File finalize_<ver>.ps1 [-Bundle <dir>] [-BS <bambu-studio.exe>] [-Work <dir>]
#
# Never overwrites: the work folder must not exist (bump the version to rebuild).
# Exit 0 only when bake + slice succeed and the baked file passes the readback checks.
param(
  [string]$Bundle = $PSScriptRoot,
  [string]$BS = "C:\Program Files\Bambu Studio\bambu-studio.exe",
  [string]$Work = "",
  [int]$TimeoutSec = 600
)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.IO.Compression, System.IO.Compression.FileSystem
$man = Get-Content (Join-Path $Bundle "manifest.json") -Raw | ConvertFrom-Json
$tag = $man.tag
if (-not $Work) { $Work = "C:\Temp\bs\$tag" }
if (Test-Path $Work) { throw "Work folder exists: $Work. Existing plates are never overwritten; bump the version." }
New-Item -ItemType Directory -Force $Work | Out-Null
if (-not (Test-Path $BS)) { throw "bambu-studio.exe not found: $BS" }
$res = Join-Path (Split-Path $BS) "resources\profiles\BBL"
$log = Join-Path $Work "finalize_log.txt"
function Log($s) { $s | Tee-Object -FilePath $log -Append }

# ---- 1. full presets: installed *_full system preset + overrides from the bundle
function FullPreset([string]$kind, [string]$sysName, $userJson, [string]$outName) {
  $full = Join-Path $res "${kind}_full\$sysName.json"
  if (-not (Test-Path $full)) { throw "system preset not installed: $full" }
  $cfg = Get-Content $full -Raw | ConvertFrom-Json
  if ($userJson) {
    foreach ($p in $userJson.PSObject.Properties) {
      if ($p.Name -in @("inherits")) { continue }
      if ($cfg.PSObject.Properties[$p.Name]) { $cfg.($p.Name) = $p.Value } else { $cfg | Add-Member -NotePropertyName $p.Name -NotePropertyValue $p.Value }
    }
    if ($cfg.PSObject.Properties["inherits"]) { $cfg.inherits = $sysName } else { $cfg | Add-Member inherits $sysName }
    $cfg.from = "User"
  }
  $out = Join-Path $Work $outName
  [IO.File]::WriteAllText($out, ($cfg | ConvertTo-Json -Depth 20), (New-Object Text.UTF8Encoding($false)))
  return $out
}
$mach = FullPreset "machine" $man.printer.machine $null "machine.json"
$pj = Get-Content (Join-Path $Bundle $man.presets.process) -Raw | ConvertFrom-Json
$proc = FullPreset "process" $man.printer.process $pj "process.json"
$fils = @()
for ($i = 0; $i -lt $man.presets.filaments.Count; $i++) {
  $fj = Get-Content (Join-Path $Bundle $man.presets.filaments[$i]) -Raw | ConvertFrom-Json
  $fils += FullPreset "filament" $fj.inherits $fj ("filament_{0}.json" -f ($i + 1))
}
Log "presets: machine=$($man.printer.machine) process=$($man.printer.process) filaments=$($fils.Count)"

function RunBS([string[]]$a, [string]$label) {
  $q = $a | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } }
  Log "RUN $label : bambu-studio $($q -join ' ')"
  $sw = [Diagnostics.Stopwatch]::StartNew()
  $pr = Start-Process -FilePath $BS -ArgumentList $q -PassThru -NoNewWindow
  if (-not $pr.WaitForExit($TimeoutSec * 1000)) { $pr.Kill(); throw "$label timed out after $TimeoutSec s" }
  Start-Sleep 2
  $rj = Join-Path $Work "result.json"; $r = $null
  if (Test-Path $rj) { $r = Get-Content $rj -Raw | ConvertFrom-Json; Copy-Item $rj (Join-Path $Work "result_$label.json") -Force }
  Log ("{0}: exit {1} in {2:N1}s; return_code={3} error='{4}'" -f $label, $pr.ExitCode, $sw.Elapsed.TotalSeconds, $r.return_code, $r.error_string)
  return @{ exit = $pr.ExitCode; result = $r }
}
$src = Join-Path $Bundle "$tag.3mf"
$common = @("--allow-newer-file", "--load-settings", "$mach;$proc", "--load-filaments", ($fils -join ";"), "--outputdir", $Work)

# ---- 2. bake: load + apply full settings + export project (no G-code)
$bake = RunBS ($common + @("--export-3mf", "${tag}_baked.3mf", $src)) "bake"
# ---- 3. slice every plate (proves the project is printable as specified)
$slice = RunBS ($common + @("--slice", "0", "--export-3mf", "${tag}_sliced.gcode.3mf", $src)) "slice"
# ---- 4. plate renders from Bambu Studio itself (visual inspection)
$png = RunBS ($common + @("--export-png", "0", "--camera_view", "0", $src)) "png"

# ---- 5. readback of the baked project
$ok = $true; $v = [ordered]@{}
$baked = Join-Path $Work "${tag}_baked.3mf"
if (Test-Path $baked) {
  $zip = [IO.Compression.ZipFile]::OpenRead($baked)
  $e = $zip.GetEntry("Metadata/project_settings.config")
  if ($e) {
    $ps = (New-Object IO.StreamReader($e.Open())).ReadToEnd() | ConvertFrom-Json
    $v.project_keys = ($ps.PSObject.Properties | Measure-Object).Count
    $v.printer = $ps.printer_settings_id; $v.process = $ps.print_settings_id
    $v.filaments = $ps.filament_settings_id; $v.colours = $ps.filament_colour
    if ($v.filaments.Count -ne $man.n_filaments) { $ok = $false; Log "FAIL filament count $($v.filaments.Count) != $($man.n_filaments)" }
  } else { $ok = $false; Log "FAIL baked file has no project_settings.config" }
  $ms = $zip.GetEntry("Metadata/model_settings.config")
  $xml = [xml](New-Object IO.StreamReader($ms.Open())).ReadToEnd()
  $v.plates = @($xml.config.plate).Count
  if ($v.plates -ne $man.plates.Count) { $ok = $false; Log "FAIL plates $($v.plates) != $($man.plates.Count)" }
  $zip.Dispose()
} else { $ok = $false; Log "FAIL no baked 3MF" }
if (-not $bake.result -or $bake.result.return_code -ne 0) { $ok = $false }
if (-not $slice.result -or $slice.result.return_code -ne 0) { $ok = $false }
if ($slice.result) {
  $v.sliced = @($slice.result.sliced_plates | ForEach-Object { [ordered]@{ plate = $_.id; seconds = $_.total_predication;
      grams = (($_.filaments | Measure-Object total_used_g -Sum).Sum); warnings = $_.warning_message } })
}
$v.status = $(if ($ok) { "PASS" } else { "FAIL" })
($v | ConvertTo-Json -Depth 8) | Set-Content (Join-Path $Work "verify.json")
Log ($v | ConvertTo-Json -Depth 8)
Log "FINALIZE $($v.status): $Work"
if (-not $ok) { exit 1 }
