' KeyVault silent launcher (no console window)
' Desktop shortcut should point here.
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
root = fso.GetParentFolderName(scriptDir)
ps1 = root & "\scripts\KeyVault-start.ps1"
If Not fso.FileExists(ps1) Then
  MsgBox "找不到启动脚本：" & vbCrLf & ps1, 16, "KeyVault"
  WScript.Quit 1
End If
sh.CurrentDirectory = root
cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File """ & ps1 & """"
' 0=hidden window; True=wait so MessageBox from ps1 can finish cleanly
sh.Run cmd, 0, True
