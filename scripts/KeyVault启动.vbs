' KeyVault 静默启动（不弹黑窗口）
' 双击本文件，或由桌面快捷方式指向本文件
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
root = fso.GetParentFolderName(scriptDir)
' 统一走 PowerShell 启动器（与桌面快捷方式相同）
ps1 = root & "\scripts\KeyVault-start.ps1"
If Not fso.FileExists(ps1) Then
  MsgBox "找不到启动脚本：" & vbCrLf & ps1, 16, "KeyVault"
  WScript.Quit 1
End If
sh.CurrentDirectory = root
cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File """ & ps1 & """"
' 0=隐藏窗口；True=等待结束
sh.Run cmd, 0, True
