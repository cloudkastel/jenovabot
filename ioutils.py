import json, os, psycopg2


def read_json(file_name: str, *path: list[str | int]):
    """A function for reading JSON object data from a file."""
    
    with open(file_name, "r") as file:
        position = json.load(file)
    for key in path:
        if key is None:
            return None
        position = position.get(str(key), None)
    return position

def read_sql(table_name: str, guild_id: int, column_name: str):
    """A function for reading data from a single cell in a SQL table."""
    
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
    """A function for writing data to a single cell in a SQL table."""
    
    database_url = os.getenv("DATABASE_URL")
    query = f"INSERT INTO {table_name} (guild_id, {column_name}) VALUES ({guild_id}, {value}) ON CONFLICT (guild_id) DO UPDATE SET {column_name}={value};"

    try:
        with psycopg2.connect(database_url, sslmode="require") as conn:
            with conn.cursor() as cursor:
                cursor.execute(query)
            conn.commit()
    finally:
        conn.close()