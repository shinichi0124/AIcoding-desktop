Option Explicit
' Hidden launcher for the Start Menu / taskbar shortcut. WindowStyle 0 = no console.
Dim fso, sh, root, py, bridge
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
root = fso.GetParentFolderName(WScript.ScriptFullName)

py = "C:\ProgramData\anaconda3\pythonw.exe"
If Not fso.FileExists(py) Then py = "C:\ProgramData\anaconda3\python.exe"
If Not fso.FileExists(py) Then py = "C:\ProgramData\xraylarch\pythonw.exe"
If Not fso.FileExists(py) Then py = "C:\ProgramData\xraylarch\python.exe"
If Not fso.FileExists(py) Then
  MsgBox "Python not found (Anaconda / xraylarch).", 16, "AI Coding Desktop"
  WScript.Quit 1
End If

bridge = root & "\sources\windows\app\bridge"
If Not fso.FolderExists(bridge) Then
  MsgBox "Missing " & bridge, 16, "AI Coding Desktop"
  WScript.Quit 1
End If

sh.CurrentDirectory = bridge
sh.Run """" & py & """ supervisor.py", 0, False
