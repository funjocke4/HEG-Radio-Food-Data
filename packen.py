#!/usr/bin/env python3
import datetime, gzip, hashlib, json, shutil, sqlite3, sys
from pathlib import Path
if len(sys.argv) != 4:
    sys.exit('Aufruf: packen.py quelle.sqlite ziel.sqlite.gz info.json')
source, dest, manifest = map(Path, sys.argv[1:])
if not source.is_file():
    sys.exit(f'FEHLER: nicht vorhanden: {source}')
con = sqlite3.connect(f'file:{source}?mode=ro', uri=True)
try:
    if con.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
        sys.exit('FEHLER: SQLite beschädigt')
    n = con.execute('SELECT COUNT(*) FROM places').fetchone()[0]
    phones = con.execute("SELECT COUNT(*) FROM places WHERE phone <> ''").fetchone()[0]
    regions = con.execute('SELECT COUNT(*) FROM imported_regions').fetchone()[0]
    con.execute('SELECT osm_key,name,category,address,hours,phone,lat,lon FROM places LIMIT 1').fetchone()
    if regions != 16 or n < 100000:
        sys.exit(f'FEHLER: unvollständige Datenbank: {regions}/16 Bundesländer, {n} Treffer')
finally:
    con.close()
with source.open('rb') as r, dest.open('wb') as dest_file:
    with gzip.GzipFile(filename='',mode='wb',fileobj=dest_file, compresslevel=6,mtime=0) as gz:
        shutil.copyfileobj(r,gz)
h = hashlib.sha256(dest.read_bytes()).hexdigest()
manifest.write_text(json.dumps({'updated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'regions':regions,'places':n,'phones':phones,'file':dest.name,'sha256':h,'source':'© OpenStreetMap contributors','license':'ODbL 1.0','license_url':'https://www.openstreetmap.org/copyright'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(f'Geprüft: {regions} Bundesländer, {n} Betriebe, {phones} Telefonnummern; ZIP/GZIP: {dest.stat().st_size/1048576:.1f} MiB')
