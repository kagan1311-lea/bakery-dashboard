"""Shared fixtures: a throwaway Postgres schema per test, so tests never touch real tables."""

import os
import uuid
from pathlib import Path

import psycopg2
import pytest
from dotenv import load_dotenv

load_dotenv(".env")
TEST_URL = os.environ.get("TEST_DATABASE_URL")
SCHEMA_SQL = Path(__file__).parent.parent / "schema.sql"


@pytest.fixture
def pg_schema():
    """Name of an empty schema that is dropped after the test."""
    if not TEST_URL:
        pytest.skip("TEST_DATABASE_URL not set")
    name = f"test_{uuid.uuid4().hex[:8]}"
    admin = psycopg2.connect(TEST_URL, connect_timeout=15)
    admin.autocommit = True
    admin.cursor().execute(f"CREATE SCHEMA {name}")
    yield name
    admin.cursor().execute(f"DROP SCHEMA {name} CASCADE")
    admin.close()


@pytest.fixture
def conn(pg_schema):
    c = psycopg2.connect(TEST_URL, connect_timeout=15, options=f"-c search_path={pg_schema}")
    yield c
    c.close()


@pytest.fixture
def schema_url(pg_schema):
    """TEST_DATABASE_URL pointed at the throwaway schema, for code that connects by URL."""
    sep = "&" if "?" in TEST_URL else "?"
    return f"{TEST_URL}{sep}options=-csearch_path%3D{pg_schema}"


def create_tables(conn):
    with conn, conn.cursor() as cur:
        cur.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
