@echo off
rem Run this once. It puts a "Video Prep Studio" shortcut on your Desktop.
set "APPDIR=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$d=[Environment]::GetFolderPath('Desktop'); $s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d 'Video Prep Studio.lnk')); $s.TargetPath=(Join-Path $env:APPDIR 'run.bat'); $s.WorkingDirectory=$env:APPDIR; $s.Description='Video Prep Studio'; $s.IconLocation='shell32.dll,115'; $s.Save(); Write-Host ('Shortcut created: ' + (Join-Path $d 'Video Prep Studio.lnk'))"
if errorlevel 1 echo Could not create the shortcut.
pause
