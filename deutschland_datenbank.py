#!/usr/bin/env python3
"""Create a resumable nationwide restaurant SQLite using Geofabrik region extracts."""
from pathlib import Path
import argparse
import shutil
import sqlite3
import subprocess
import sys

REGIONS = (
 'baden-wuerttemberg','bayern','berlin','brandenburg','bremen','hamburg',
 'hessen','mecklenburg-vorpommern','niedersachsen','nordrhein-westfalen',
 'rheinland-pfalz','saarland','sachsen','sachsen-anhalt','schleswig-holstein','thueringen'
)
BASE = 'https://download.geofabrik.de/europe/germany'
SCHEMA = '''CREATE TABLE IF NOT EXISTS places (
 osm_key TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL,
 address TEXT NOT NULL, hours TEXT NOT NULL, phone TEXT NOT NULL,
 lat REAL NOT NULL, lon REAL NOT NULL)'''

def connect(db):
    dbh=sqlite3.connect(db,timeout=120)
    dbh.execute(SCHEMA)
    dbh.execute('CREATE TABLE IF NOT EXISTS imported_regions (name TEXT PRIMARY KEY)')
    dbh.commit()
    return dbh

def merge(master, region_db, region):
    # Attach, import and record completed region in a single transaction.
    master.execute('ATTACH DATABASE ? AS regional', (str(region_db),))
    try:
        master.execute('BEGIN')
        master.execute('INSERT OR REPLACE INTO places SELECT * FROM regional.places')
        master.execute('INSERT OR REPLACE INTO imported_regions VALUES (?)', (region,))
        master.commit()
    except Exception:
        master.rollback()
        raise
    finally:
        master.execute('DETACH DATABASE regional')

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--arbeit',type=Path,required=True)
    p.add_argument('--konverter',type=Path,required=True)
    p.add_argument('--python',type=Path,default=Path(sys.executable))
    a=p.parse_args()
    a.arbeit.mkdir(parents=True, exist_ok=True)
    master_path=a.arbeit/'heg_food_deutschland.sqlite'
    master=connect(master_path)
    try:
        for idx, region in enumerate(REGIONS,1):
            if master.execute('SELECT 1 FROM imported_regions WHERE name=?',(region,)).fetchone():
                print(f'[{idx}/16] {region}: bereits importiert',flush=True)
                continue
            pbf=a.arbeit/f'{region}-latest.osm.pbf'
            # Reuse the previous Schleswig-Holstein download if available.
            if region=='schleswig-holstein' and not pbf.exists():
                prev=Path.home()/'Downloads/HEG-Radio-Offline-Imbisse/schleswig-holstein-latest.osm.pbf'
                if prev.exists() and prev.stat().st_size>10_000_000:
                    pbf=prev
            if not pbf.exists() or pbf.stat().st_size<10_000_000:
                url=f'{BASE}/{region}/{region}-latest.osm.pbf'
                temp=a.arbeit/f'{region}-latest.osm.pbf.part'
                print(f'[{idx}/16] Lade {region}: {url}', flush=True)
                subprocess.run(['curl','--fail','--location','--retry','3',
                                '--connect-timeout','20','--continue-at','-',
                                '--output',str(temp),url],check=True)
                if temp.stat().st_size<10_000_000:
                    raise RuntimeError(f'Download {region} zu klein')
                temp.rename(a.arbeit/f'{region}-latest.osm.pbf')
                pbf=a.arbeit/f'{region}-latest.osm.pbf'
            region_db=a.arbeit/f'{region}.sqlite'
            print(f'[{idx}/16] Verarbeite {region}',flush=True)
            subprocess.run([str(a.python),str(a.konverter),str(pbf),
                            '--ausgabe',str(region_db)],check=True)
            merge(master,region_db,region)
            region_db.unlink()
            # Keep the previous Schleswig-Holstein raw file; remove only this script's copies.
            if pbf.parent==a.arbeit:
                pbf.unlink()
            total=master.execute('SELECT COUNT(*) FROM places').fetchone()[0]
            print(f'[{idx}/16] Fertig: {region} / insgesamt {total} Einträge',flush=True)
        master.execute('CREATE INDEX IF NOT EXISTS places_lat_lon ON places(lat,lon)')
        master.commit()
        master.execute('VACUUM')
        total=master.execute('SELECT COUNT(*) FROM places').fetchone()[0]
        phones=master.execute("SELECT COUNT(*) FROM places WHERE phone <> ''").fetchone()[0]
        print(f'FERTIG: {len(REGIONS)} Regionen | {total} Einträge | {phones} Telefonnummern',flush=True)
        print(f'DATENBANK: {master_path} ({master_path.stat().st_size/1048576:.1f} MB)',flush=True)
    finally:
        master.close()
if __name__=='__main__': main()
