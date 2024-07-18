VERSION=11
tail -n +2 "server.py" > "server.py.tmp" && mv "server.py.tmp" "server.py"
sed -i '$ d' server.py
CONTENT=`cat server.py`
rm server.py
echo "print('START VERSION: $VERSION')" > server.py
echo "$CONTENT" >> server.py
echo "print('END VERSION: $VERSION')" >> server.py

nssm stop WMFService

pyinstaller --noconfirm --onefile --console --name "WheresMyFlight" --add-data "C:/Users/shuch/WMF-Server/.env;." --add-data "C:/Users/shuch/WMF-Server/pytextnow;pytextnow/"  "C:/Users/shuch/WMF-Server/server.py"

mv dist/WheresMyFlight.exe "WheresMyFlight.exe"
rm -rf dist build
rm WheresMyFlight.spec

nssm start WMFService

echo "Version $VERSION built successfully"