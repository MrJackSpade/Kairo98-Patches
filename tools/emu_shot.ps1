# Boot an HDI in np21w, send keys on a schedule, and capture window screenshots.
#   pwsh tools/emu_shot.ps1 -Hdi X.hdi -Out shots\name -Steps "20:shot,1:enter,3:shot"
# Each step is "<seconds to wait>:<action>"; action = shot | save (emulator state -> <Out>.s00) | lclick | rclick | ldown | lup | mouse=dx;dy | enter | space | esc | up | down | left | right
# | key=<VK decimal>.  Screenshots are <Out>_<n>.png.  Works with the desktop locked (PrintWindow/PostMessage).
param(
    [string]$Hdi = "",
    [string]$Fd1 = "",
    [string]$Fd2 = "",
    [Parameter(Mandatory)] [string]$Out,
    [string]$Steps = "25:shot",
    [string]$Dip = "",   # DIP switch bytes, e.g. "3e f3 7b" (np21w DIPswtch)
    [string]$ClkMult = "",   # CPU clock multiplier (np21w clk_mult; empty: the emulator's default)
    [string]$Exe = "E:\PC98work\emu\bin\np21x64w.exe"
)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System; using System.Runtime.InteropServices;
public static class W {
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint f);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
  [DllImport("user32.dll")] public static extern uint MapVirtualKey(uint c, uint t);
  public struct RECT { public int L, T, R, B; }
}
"@
$bin = Split-Path $Exe
$work = Join-Path $env:TEMP ("np21_" + [guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory $work | Out-Null
$img = ""
if ($Hdi) { $img = Join-Path $work "disk.hdi"; Copy-Item -LiteralPath $Hdi $img }
$fds = @()
foreach ($f in @($Fd1, $Fd2)) {
    if ($f) { $c = Join-Path $work ("fd{0}{1}" -f $fds.Count, [IO.Path]::GetExtension($f)); Copy-Item -LiteralPath $f $c; $fds += $c }
}
$ini = Join-Path $work "np21.ini"
$base = Join-Path $bin "np21x64w.ini"
$lines = @()
if (Test-Path $base) { $lines = Get-Content $base | Where-Object { $_ -notmatch '^(HDD1FILE|IDE1TYPE|WindposX|WindposY|DIPswtch|clk_mult)=' } }
if (-not ($lines -match '^\[NekoProject21\]')) { $lines = @("[NekoProject21]") + $lines }
$out2 = @()
foreach ($l in $lines) { $out2 += $l; if ($l -match '^\[NekoProject21\]') { $out2 += "HDD1FILE=$img"; $out2 += "IDE1TYPE=1"; $out2 += "WindposX=100"; $out2 += "WindposY=100"; if ($Dip) { $out2 += "DIPswtch=$Dip" }; if ($ClkMult) { $out2 += "clk_mult=$ClkMult" } } }
Set-Content $ini $out2
$argv = @("-i$ini") + ($fds | ForEach-Object { '"' + $_ + '"' })
$started = Get-Date
$vk = @{ enter = 13; space = 32; esc = 27; up = 38; down = 40; left = 37; right = 39 }
# reject a malformed step before the emulator starts
foreach ($s in $Steps.Split(",")) {
    $wait, $act = $s.Split(":", 2)
    if (-not ($act -match '^(shot|save|lclick|rclick|ldown|lup|mouse=-?\d+;-?\d+|key=\d+)$' -or $vk.ContainsKey($act))) { throw "bad step: $s" }
}
$p = Start-Process $Exe -ArgumentList $argv -WorkingDirectory $bin -PassThru
Start-Sleep 3
$p.Refresh(); $h = $p.MainWindowHandle
$n = 0
New-Item -ItemType Directory -Force (Split-Path $Out) | Out-Null
try {
foreach ($s in $Steps.Split(",")) {
    $wait, $act = $s.Split(":", 2)
    Start-Sleep -Milliseconds ([int]([double]$wait * 1000))
    $p.Refresh(); $h = $p.MainWindowHandle
    if ($act -like "mouse=*") {
        # move the emulated mouse (our np21w build's test message WM_USER+0x7A0, signed deltas)
        $dxy = $act.Substring(6).Split(";")
        [W]::PostMessage($h, 0xBA0, [IntPtr][int]$dxy[0], [IntPtr][int]$dxy[1]) | Out-Null
        continue
    }
    if ($act -eq "lclick" -or $act -eq "rclick") {
        # PC-98 mouse button (our np21w build's test message WM_USER+0x7A1: button mask)
        $mask = if ($act -eq "lclick") { 1 } else { 2 }
        [W]::PostMessage($h, 0xBA1, [IntPtr]$mask, [IntPtr]0) | Out-Null
        Start-Sleep -Milliseconds 500  # held long enough for games that sample the button slowly
        [W]::PostMessage($h, 0xBA1, [IntPtr]0, [IntPtr]0) | Out-Null
        continue
    }
    if ($act -eq "ldown" -or $act -eq "lup") {
        # hold / release the left button
        $mask = if ($act -eq "ldown") { 1 } else { 0 }
        [W]::PostMessage($h, 0xBA1, [IntPtr]$mask, [IntPtr]0) | Out-Null
        continue
    }
    if ($act -eq "save") {
        # emulator state (raw main memory inside), kept as <Out>.s00
        [W]::PostMessage($h, 0x111, [IntPtr]40201, [IntPtr]0) | Out-Null
        continue
    }
    if ($act -eq "shot") {
        $r = New-Object W+RECT; [W]::GetWindowRect($h, [ref]$r) | Out-Null
        $bmp = New-Object System.Drawing.Bitmap ($r.R - $r.L), ($r.B - $r.T)
        $g = [System.Drawing.Graphics]::FromImage($bmp); $dc = $g.GetHdc()
        [W]::PrintWindow($h, $dc, 2) | Out-Null; $g.ReleaseHdc($dc)
        $n++; $f = "{0}_{1}.png" -f $Out, $n; $bmp.Save($f); $g.Dispose(); $bmp.Dispose()
        Write-Output "shot $f"
    } else {
        $code = if ($act -like "key=*") { [int]$act.Substring(4) } else { $vk[$act] }
        $sc = [W]::MapVirtualKey($code, 0)
        [W]::PostMessage($h, 0x100, [IntPtr]$code, [IntPtr](1 -bor ($sc -shl 16))) | Out-Null
        Start-Sleep -Milliseconds 120
        [W]::PostMessage($h, 0x101, [IntPtr]$code, [IntPtr](1 -bor ($sc -shl 16) -bor (3 -shl 30))) | Out-Null
    }
}
} finally {
    # always close the emulator, even when a step fails
    $p.CloseMainWindow() | Out-Null; Start-Sleep 1; if (-not $p.HasExited) { $p.Kill() }
}
$state = Get-ChildItem -Path $work, $bin -Filter *.S00 -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -ge $started } | Sort-Object LastWriteTime | Select-Object -Last 1
if ($state) { Move-Item -Force $state.FullName ("{0}.s00" -f $Out); Write-Output ("state {0}.s00" -f $Out) }
Remove-Item -Recurse -Force $work
