@echo off
setlocal

echo Building Discord Role Whitelist Generator EXE...
echo.

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller

pyinstaller --onefile --windowed --name DiscordRoleWhitelistGenerator discord_role_whitelist_generator.py

echo.
echo Done.
echo Your EXE should be in the dist folder.
pause
