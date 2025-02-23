import json, os, psycopg2, psycopg2.extensions, psycopg2.extras
from discord import Embed, Color


DATABASE_SETTINGS = os.getenv("DATABASE_SETTINGS", default="test_settings")
psycopg2.extensions.register_adapter(dict, psycopg2.extras.Json)

class RandomColorEmbed(Embed):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, color=Color.random(), **kwargs)

def read_json(file_name: str, *path: list[str | int]):
    """Read JSON object data from a file."""
    
    with open(file_name, "r") as file:
        position = json.load(file)
    for key in path:
        if key is None:
            return None
        position = position.get(str(key), None)
    return position

def read_sql(table_name: str, guild_id: int, column_name: str):
    """Read data from a single cell in a SQL table."""
    
    database_url = os.getenv("DATABASE_URL")
    query = f"SELECT {column_name} FROM {table_name} WHERE guild_id={guild_id};"

    try:
        with psycopg2.connect(database_url, sslmode="require") as conn:
            with conn.cursor() as cursor:
                cursor.execute(query)
                results = cursor.fetchall()
    finally:
        conn.close()

    return None if results == [] else results[0][0]

def write_sql(table_name: str, guild_id: int, column_name: str, value: any):
    """Write data to a single cell in a SQL table."""
    
    database_url = os.getenv("DATABASE_URL")
    query = f"INSERT INTO {table_name} (guild_id, {column_name}) VALUES (%(guild_id)s, %(value)s) ON CONFLICT (guild_id) DO UPDATE SET {column_name}=%(value)s;"
    if isinstance(value, list) and all(isinstance(x, dict) for x in value):
        query = query.replace(r"%(value)s", r"%(value)s::json[]")

    try:
        with psycopg2.connect(database_url, sslmode="require") as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, {"guild_id": guild_id, "value": value})
            conn.commit()
    finally:
        conn.close()