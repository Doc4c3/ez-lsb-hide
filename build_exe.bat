@echo off
pyinstaller --onefile --noconsole --clean --collect-all tkinterdnd2 --name LSBStegTool lsb_gui.py
pause
