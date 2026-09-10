"""Migra una base SQLite de Centro Operativo a un PostgreSQL vacío."""
import argparse
import os
from pathlib import Path

import psycopg
from psycopg import sql

from app.postgres_server import SCHEMA
from tools.sqlite_to_postgres.migration_core import TABLES, counts, load_sqlite


def target_must_be_empty(database):
    occupied = {}
    for table in TABLES:
        total = database.execute(sql.SQL("SELECT count(*) FROM {}" ).format(sql.Identifier(table))).fetchone()[0]
        if total:
            occupied[table] = total
    if occupied:
        details = ", ".join(f"{table}={total}" for table, total in occupied.items())
        raise RuntimeError(f"El destino no está vacío ({details}). No se modificó PostgreSQL.")


def migrate(source_path, database_url):
    dataset = load_sqlite(source_path)
    with psycopg.connect(database_url) as database:
        database.execute(SCHEMA)
        target_must_be_empty(database)
        for table in TABLES:
            columns = dataset[table]["columns"]
            records = dataset[table]["rows"]
            if not records:
                continue
            statement = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                sql.Identifier(table),
                sql.SQL(",").join(map(sql.Identifier, columns)),
                sql.SQL(",").join(sql.Placeholder() for _ in columns),
            )
            with database.cursor() as cursor:
                cursor.executemany(statement, [[record[column] for column in columns] for record in records])
        for table in TABLES:
            if "id" not in dataset[table]["columns"]:
                continue
            sequence = database.execute("SELECT pg_get_serial_sequence(%s,'id')", (table,)).fetchone()[0]
            if sequence:
                maximum = max((record["id"] for record in dataset[table]["rows"]), default=0)
                database.execute("SELECT setval(%s,%s,%s)", (sequence, max(maximum, 1), maximum > 0))
    return counts(dataset)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Ruta a centro_operativo.db")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"), help="URL PostgreSQL; por defecto usa DATABASE_URL")
    args = parser.parse_args()
    if not args.database_url:
        parser.error("Falta --database-url o la variable DATABASE_URL")
    result = migrate(args.source, args.database_url)
    print("Migración completada y confirmada:")
    for table, total in result.items():
        print(f"  {table}: {total}")


if __name__ == "__main__":
    main()
