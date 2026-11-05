"""Smoke del pacchetto Windows in una directory dati temporanea e isolata."""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('executable', type=Path)
    executable = parser.parse_args().executable.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix='lottopredict-package-') as folder:
        environment = {**os.environ, 'LOTTOPREDICT_DATA_DIR': folder, 'QT_QPA_PLATFORM': 'offscreen'}
        for option in ('--check', '--smoke-test'):
            subprocess.run([str(executable), option], cwd=folder, env=environment, check=True, timeout=90)
        database = Path(folder) / 'lottopredict.sqlite3'
        if not database.is_file():
            raise RuntimeError('Il pacchetto non ha creato il database di test')
        with closing(sqlite3.connect(database)) as connection:
            if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Database del pacchetto non integro')
        print(json.dumps({'package_check': 'ok', 'database_integrity': 'ok'}))


if __name__ == '__main__':
    main()
