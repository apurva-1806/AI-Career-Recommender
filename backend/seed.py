"""Initialise the database and load the career dataset.

    python seed.py            # create tables, load careers if the table is empty
    python seed.py --reset    # drop every table (including saved profiles) and reload

The API also seeds automatically on first start, so this script is mainly for
resetting after you edit data/careers.csv.
"""
from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import func, select

import database as db
from config import get_settings


async def run(reset: bool) -> None:
    settings = get_settings()
    db.init_engine(settings)
    await db.create_tables(drop_first=reset)
    async with db.get_sessionmaker()() as session:
        loaded = await db.seed_database(session, settings.careers_csv, force=reset)
        careers = (await session.execute(select(func.count()).select_from(db.Career))).scalar_one()
        skills = (await session.execute(select(func.count()).select_from(db.Skill))).scalar_one()
    await db.dispose_engine()
    action = f"Loaded {loaded} careers." if loaded else "Careers already present; nothing loaded."
    print(f"{action} Database now holds {careers} careers and {skills} taxonomy skills.")
    print(f"Database: {settings.database_url.split('@')[-1]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create tables and seed the career dataset.")
    parser.add_argument("--reset", action="store_true", help="Drop all tables first (deletes saved profiles).")
    asyncio.run(run(parser.parse_args().reset))
