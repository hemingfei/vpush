' MX collector guard launcher (hidden window): schtasks -> wscript -> python guard.
' Keep this file ASCII-only: wscript reads ANSI and CJK comments break parsing.
' Task registration (one-time):
'   schtasks /Create /TN "MXCollectorGuard" /SC MINUTE /MO 1 /TR "wscript.exe
'   \"C:\Users\hemin\Documents\vpush\scripts\mx_collector_guard.vbs\"" /F
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "C:\Users\hemin\Documents\vpush"
sh.Run """C:\Users\hemin\Documents\vpush\.venv\Scripts\pythonw.exe"" ""C:\Users\hemin\Documents\vpush\scripts\mx_collector_guard.py""", 0, False
