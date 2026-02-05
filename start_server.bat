@echo off
echo Starting Plant Doctor System...
start "Plant Doctor Server" run_server.bat
start "Ngrok Tunnel" start_ngrok.bat
echo Both services have been requested to start in new windows.
pause
