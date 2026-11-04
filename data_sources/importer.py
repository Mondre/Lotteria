import csv
import io
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from database.store import Store
from games.models import Draw

MAX_BYTES = 25 * 1024 * 1024
MAX_ROWS = 100000
REQUIRED = {"game", "variant", "draw_id", "occurred_at", "numbers"}


@dataclass
class ImportReport:
    inserted: int = 0
    duplicates: int = 0
    rejected: int = 0
    errors: list[str] = field(default_factory=list)


def read_records(content: bytes, format: str) -> list[dict[str, Any]]:
    if len(content) > MAX_BYTES:
        raise ValueError("Archivio oltre il limite di 25 MiB")
    if format == "json":
        records = json.loads(content.decode("utf-8-sig"))
        if not isinstance(records, list):
            raise ValueError("JSON: è richiesta una lista di oggetti")
    elif format == "csv":
        text = content.decode("utf-8-sig")
        try:
            dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(io.StringIO(text), dialect=dialect)
        if not REQUIRED.issubset(set(reader.fieldnames or [])):
            raise ValueError("CSV: intestazioni richieste mancanti")
        records = list(reader)
    elif format == "xlsx":
        try:
            from openpyxl import load_workbook
        except ImportError as error:
            raise RuntimeError("Installare openpyxl da requirements.txt per importare Excel") from error
        # Limita anche la dimensione decompressa, prima di aprire un archivio XLSX.
        from zipfile import ZipFile
        with ZipFile(io.BytesIO(content)) as archive:
            if sum(info.file_size for info in archive.infolist()) > 100 * 1024 * 1024:
                raise ValueError("Excel decompresso oltre il limite di 100 MiB")
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        try:
            rows = workbook.active.iter_rows(values_only=True)
            headers = next(rows, ())
            if len(set(headers)) != len(headers) or not REQUIRED.issubset(set(headers)):
                raise ValueError("Excel: intestazioni mancanti o duplicate")
            records = []
            for row in rows:
                if any(value is not None for value in row):
                    records.append(dict(zip(headers, row)))
                if len(records) > MAX_ROWS:
                    raise ValueError("Archivio oltre il limite di 100.000 righe")
        finally:
            workbook.close()
    else:
        raise ValueError("Formato non supportato: usare csv, json o xlsx")
    if len(records) > MAX_ROWS:
        raise ValueError("Archivio oltre il limite di 100.000 righe")
    return records


def parse_record(record: dict[str, Any], source: str, synthetic: bool) -> Draw:
    if not isinstance(record, dict) or not REQUIRED.issubset(record):
        raise ValueError("Campi richiesti mancanti")
    marker = record.get("synthetic", False)
    if isinstance(marker, str):
        if marker.strip().lower() not in ("true", "false", "1", "0", ""):
            raise ValueError("synthetic deve essere un booleano")
        marker = marker.strip().lower() in ("true", "1")
    if type(marker) is not bool:
        raise ValueError("synthetic deve essere un booleano")
    if marker and not synthetic:
        raise ValueError("Dati marcati sintetici: selezionare l'archivio sintetico")
    numbers = record["numbers"]
    if isinstance(numbers, str):
        numbers = numbers.strip()
        if numbers.startswith("["):
            numbers = json.loads(numbers)
        else:
            numbers = [int(value) for value in numbers.replace(",", " ").split()]
    if not isinstance(numbers, list) or any(type(n) is not int for n in numbers):
        raise ValueError("numbers deve essere una lista di interi")
    extras = record.get("extras", {})
    if extras is None or extras == "":
        extras = {}
    if isinstance(extras, str):
        extras = json.loads(extras)
    if not isinstance(extras, dict):
        raise ValueError("extras deve essere un oggetto JSON")
    for key in ("game", "variant", "draw_id", "occurred_at"):
        if not isinstance(record[key], str) or not record[key].strip():
            raise ValueError(f"{key} deve essere testo non vuoto")
    wheel = record.get("wheel") or ""
    if not isinstance(wheel, str):
        raise ValueError("wheel deve essere testo")
    return Draw(record["game"].strip(), record["variant"].strip(), record["draw_id"].strip(),
                datetime.fromisoformat(record["occurred_at"].strip()), tuple(numbers),
                wheel.strip(), extras, synthetic, source)


def import_content(store: Store, content: bytes, format: str, source: str,
                   synthetic: bool = False) -> ImportReport:
    report = ImportReport()
    try:
        records = read_records(content, format)
    except Exception as error:
        store.log("ERROR", f"Lettura archivio fallita ({type(error).__name__})")
        raise
    with store.batch():
        for index, record in enumerate(records, start=1):
            try:
                draw = parse_record(record, source, synthetic)
                if store.add_draw(draw):
                    report.inserted += 1
                else:
                    report.duplicates += 1
            except (ValueError, TypeError, OverflowError) as error:
                report.rejected += 1
                message = f"Riga {index}: {error}"
                if len(report.errors) < 100:
                    report.errors.append(message)
                store.log("WARNING", message)
        store.log("INFO", f"Importazione terminata: {report.inserted} aggiunte, "
                  f"{report.duplicates} duplicate, {report.rejected} rifiutate")
    return report


def import_file(store: Store, path: Path, synthetic: bool = False) -> ImportReport:
    with path.open("rb") as stream:
        content = stream.read(MAX_BYTES + 1)
    return import_content(store, content, path.suffix.lower().lstrip("."),
                          f"file:{path.name}", synthetic)
