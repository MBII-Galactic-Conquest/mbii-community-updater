pyinstaller --noconsole --onefile ^
  --icon "icon.ico" ^
  --add-data "background.png;." ^
  --add-data "background.jpg;." ^
  --add-data "icon.ico;." ^
  --add-data "music.mp3;." ^
  mbupdater.py
echo Press enter to exit
set /p input=