' KeyVault 静默启动（不弹黑窗口）
' 双击本文件，或由桌面快捷方式指向本文件
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
root = fso.GetParentFolderName(scriptDir)
bat = root & "\scripts\KeyVault启动.bat"
If Not fso.FileExists(bat) Then
  MsgBox "找不到启动脚本：" & bat, 16, "KeyVault"
  WScript.Quit 1
End If
sh.CurrentDirectory = root
' 0=隐藏窗口，False=不等待结束
sh.Run """" & bat & """", 0, False
