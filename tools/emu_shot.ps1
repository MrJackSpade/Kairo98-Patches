# Boot an HDI in np21w, send keys on a schedule, and capture window screenshots.
#   pwsh tools/emu_shot.ps1 -Hdi X.hdi -Out shots\name -Steps "20:shot,1:enter,3:shot"
# Each step is "<seconds to wait>:<action>"; action = shot | enter | space | esc | up | down | left | right
# | key=<VK decimal>.  Screenshots are <Out>_<n>.png.  Works with the desktop locked (PrintWindow/PostMessage).
param(
    [Parameter(Mandatory)] [string]$Hdi,
    [Parameter(Mandatory)] [string]$Out,
    [string]$Steps = "25:shot",
    [string]$Exe = "C:\PC98work\emu\bin\np21x64w.exe"
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
$img = Join-Path $work "disk.hdi"
Copy-Item $Hdi $img
$ini = Join-Path $work "np21.ini"
$base = Join-Path $bin "np21x64w.ini"
$lines = @()
if (Test-Path $base) { $lines = Get-Content $base | Where-Object { $_ -notmatch '^(HDD1FILE|IDE1TYPE|WindposX|WindposY)=' } }
if (-not ($lines -match '^\[NekoProject21\]')) { $lines = @("[NekoProject21]") + $lines }
$out2 = @()
foreach ($l in $lines) { $out2 += $l; if ($l -match '^\[NekoProject21\]') { $out2 += "HDD1FILE=$img"; $out2 += "IDE1TYPE=1"; $out2 += "WindposX=100"; $out2 += "WindposY=100" } }
Set-Content $ini $out2
$p = Start-Process $Exe -ArgumentList "-i$ini" -WorkingDirectory $bin -PassThru
Start-Sleep 3
$p.Refresh(); $h = $p.MainWindowHandle
$vk = @{ enter = 13; space = 32; esc = 27; up = 38; down = 40; left = 37; right = 39 }
$n = 0
New-Item -ItemType Directory -Force (Split-Path $Out) | Out-Null
foreach ($s in $Steps.Split(",")) {
    $wait, $act = $s.Split(":", 2)
    Start-Sleep -Milliseconds ([int]([double]$wait * 1000))
    $p.Refresh(); $h = $p.MainWindowHandle
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
$p.CloseMainWindow() | Out-Null; Start-Sleep 1; if (-not $p.HasExited) { $p.Kill() }
Remove-Item -Recurse -Force $work
