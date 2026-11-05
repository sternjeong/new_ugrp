"""Display aggregate guide activity from a local service database."""
import argparse
import sqlite3

parser = argparse.ArgumentParser()
parser.add_argument('database')
args = parser.parse_args()
db = sqlite3.connect(f'file:{args.database}?mode=ro', uri=True)
for day, variant, event, count in db.execute(
        'SELECT day, variant, event, count FROM guide_variant_counts ORDER BY day, variant, event'):
    print(f'{day}\t{variant}\t{event}\t{count}')
