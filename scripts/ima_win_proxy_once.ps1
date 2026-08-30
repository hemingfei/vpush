# 一次性：把本机系统代理指到 Mac 上的 mitmproxy，方便抓 ima 打开文件的请求。
# 在已登录的 Windows ima 机器上、以当前用户运行。结束后会清掉代理。
#
# 用法（先在 Mac 上启动 mitmdump）：
#   powershell -ExecutionPolicy Bypass -File ima_win_proxy_once.ps1 -ProxyHost 192.168.5.172 -ProxyPort 8080
param(
    [string]$ProxyHost = "192.168.5.172",
    [int]$ProxyPort = 8080
)

$proxy = "http://${ProxyHost}:${ProxyPort}"
Write-Host "ima 进程："
Get-Process | Where-Object { $_.Name -match "ima|copilot" } | Select-Object Name, Id, Path | Format-Table -AutoSize
Write-Host "准备把系统代理设为 $proxy"
Write-Host "请先确认 Mac 上 mitmdump 已在听 ${ProxyPort}。"
Write-Host "若 HTTPS 失败：用系统浏览器打开 http://mitm.it 安装证书，再重开 ima。"
Pause
netsh winhttp set proxy "${ProxyHost}:${ProxyPort}"
$reg = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
Set-ItemProperty -Path $reg -Name ProxyEnable -Value 1
Set-ItemProperty -Path $reg -Name ProxyServer -Value "${ProxyHost}:${ProxyPort}"
Write-Host "代理已开。现在去 ima 打开「Z哥策略」里任意一个 txt，看到内容后回到这里按回车。"
Pause
netsh winhttp reset proxy
Set-ItemProperty -Path $reg -Name ProxyEnable -Value 0
Write-Host "代理已关。"
