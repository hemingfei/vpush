# 在已登录 ima 的 Windows 上运行：打包客户端日志/版本，方便 Mac 侧看 get_media 是否带了 2.6.6 身份。
# 不打印 token。zip 默认放到桌面。
#   powershell -ExecutionPolicy Bypass -File ima_win_export_logs.ps1
$ErrorActionPreference = "SilentlyContinue"
$dest = Join-Path ([Environment]::GetFolderPath("Desktop")) ("ima-export-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
New-Item -ItemType Directory -Path $dest | Out-Null

Write-Host "=== processes ==="
Get-Process | Where-Object { $_.Name -match "ima|copilot" } |
    Select-Object Name, Id, Path |
    Tee-Object -FilePath (Join-Path $dest "processes.txt") |
    Format-Table -AutoSize

$roots = @(
    $env:LOCALAPPDATA,
    $env:APPDATA,
    ${env:ProgramFiles},
    ${env:ProgramFiles(x86)},
    "$env:LOCALAPPDATA\Programs"
) | Where-Object { $_ }
$hits = foreach ($root in $roots) {
    Get-ChildItem $root -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match "ima|copilot" }
}
$hits | ForEach-Object { $_.FullName } | Tee-Object -FilePath (Join-Path $dest "dirs.txt")
Write-Host "=== dirs ==="
Get-Content (Join-Path $dest "dirs.txt")

foreach ($exe in @(
        "C:\Program Files\ima.copilot\ima.copilot.exe",
        "C:\Program Files\ima\ima.exe"
    )) {
    if (Test-Path $exe) {
        $v = (Get-Item $exe).VersionInfo
        "path=$exe file=$($v.FileVersion) product=$($v.ProductVersion)" |
            Tee-Object -FilePath (Join-Path $dest "version.txt") -Append
    }
}

foreach ($dir in $hits) {
    $name = $dir.Name
    foreach ($rel in @("logs", "Logs", "log", "User Data\Default")) {
        $src = Join-Path $dir.FullName $rel
        if (Test-Path $src) {
            Copy-Item $src (Join-Path $dest "$name-$($rel -replace '[\\/]','-')") -Recurse -Force
        }
    }
}

$zip = "$dest.zip"
Compress-Archive -Path $dest -DestinationPath $zip -Force
Write-Host "已打包 $zip"
Write-Host "把 zip 拷到 Mac 仓库即可（AirDrop / U盘 / 共享文件夹）。"
