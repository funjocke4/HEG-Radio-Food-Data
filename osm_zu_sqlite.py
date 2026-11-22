#!/usr/bin/env python3
"""Convert one or more Geofabrik .osm.pbf files into a compact SQLite database.
Dependency: pip install osmium (pyosmium); works offline once the PBF files exist.
"""
import argparse
from pathlib import Path
import re
import sqlite3
import sys

try:
    import osmium
except ImportError:
    sys.exit('Fehlt: pyosmium. Installiere im venv mit: python -m pip install osmium')

ap = argparse.ArgumentParser()
ap.add_argument('pbf', nargs='+', type=Path)
ap.add_argument('--ausgabe', required=True, type=Path)
a = ap.parse_args()
a.ausgabe.parent.mkdir(parents=True, exist_ok=True)

conn = sqlite3.connect(str(a.ausgabe))
conn.execute('DROP TABLE IF EXISTS places')
conn.execute('CREATE TABLE places (osm_key TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL, address TEXT NOT NULL, hours TEXT NOT NULL, phone TEXT NOT NULL, lat REAL NOT NULL, lon REAL NOT NULL)')

class FoodExtractor(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.count = 0
    def store(self, obj, typ, lat, lon):
        tags = obj.tags
        amenity = tags.get('amenity', '')
        if amenity not in ('restaurant', 'fast_food', 'cafe', 'food_court', 'biergarten'):
            return
        name = (tags.get('name') or tags.get('brand') or '').strip()
        if not name or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return
        cuisine = (tags.get('cuisine') or '').lower()
        category = 'Imbiss' if amenity == 'fast_food' else ('Café' if amenity == 'cafe' else 'Restaurant')
        if re.search(r'döner|doner|doener|kebab|pita|gyros|shawarma', name.lower()+' '+cuisine):
            category = 'Döner / Pita'
        elif 'pizza' in name.lower()+' '+cuisine: category = 'Pizza'
        elif 'burger' in name.lower()+' '+cuisine: category = 'Burger'
        elif 'mcdonald' in name.lower(): category = "McDonald's"
        elif 'burger king' in name.lower(): category = 'Burger King'
        street = tags.get('addr:street') or ''
        number = tags.get('addr:housenumber') or ''
        city = tags.get('addr:city') or ''
        address = ', '.join(p for p in [' '.join(x for x in (street, number) if x), city] if p)
        phone = (tags.get('contact:phone') or tags.get('phone') or '').split(';')[0].strip()
        # Sanitize public business telephone numbers; no synthetic numbers.
        if not re.fullmatch(r'[+0-9() /.-]{5,35}', phone) or not 5 <= len(re.sub(r'\D', '', phone)) <= 18:
            phone = ''
        row = (f'{typ}{obj.id}', name[:90], category, address[:150],
               (tags.get('opening_hours') or '')[:150], phone, round(lat, 7), round(lon, 7))
        conn.execute('INSERT OR REPLACE INTO places VALUES (?,?,?,?,?,?,?,?)', row)
        self.count += 1
        if self.count % 10000 == 0:
            conn.commit()
    def node(self, n):
        if n.location.valid():
            self.store(n, 'n', n.location.lat, n.location.lon)
    def way(self, w):
        coords = [(n.lat, n.lon) for n in w.nodes if n.location.valid()]
        if coords:
            self.store(w, 'w', sum(p[0] for p in coords) / len(coords),
                       sum(p[1] for p in coords) / len(coords))

handler = FoodExtractor()
for pbf in a.pbf:
    if not pbf.is_file(): sys.exit(f'Datei nicht gefunden: {pbf}')
    print('Verarbeite:', pbf, flush=True)
    handler.apply_file(str(pbf), locations=True, idx='flex_mem')
    conn.commit()
conn.execute('CREATE INDEX places_lat_lon ON places(lat,lon)')
conn.commit()
conn.execute('VACUUM')
print('Einträge:', conn.execute('SELECT COUNT(*) FROM places').fetchone()[0])
print('Mit Telefonnummer:', conn.execute("SELECT COUNT(*) FROM places WHERE phone <> ''").fetchone()[0])
print('Datenbank:', a.ausgabe, 'Größe:', round(a.ausgabe.stat().st_size/1024/1024,2), 'MB')
conn.close()
