import json, os, psycopg2

def read(file_name: str, *path: list[str | int]):
    with open(file_name, "r") as file:
        position = json.load(file)
    for key in path:
        if key is None:
            return None
        position = position.get(str(key), None)
    return position

def read_sql(table_name: str, guild_id: int, setting: str):
    database_url = os.getenv("DATABASE_URL")
    with psycopg2.connect(database_url, sslmode="require") as conn:
        exists_query = f"SELECT EXISTS(SELECT 1 FROM {table_name} WHERE guild_id = {guild_id})";
        query = f"SELECT {setting} FROM {table_name} WHERE guild_id = {guild_id};"
        with conn.cursor() as cursor:
            cursor.execute(exists_query)
            if cursor.fetchall() == []:
                return None
            cursor.execute(query)
            results = cursor.fetchall()[0][0]
    return results

def write(file_name: str, value: any, *path: list[str | int]):
    with open(file_name, "r+") as file:
        file_json = json.load(file)
        position = file_json
        for key in path:
            if position.get(str(key)) is None:
                position[str(key)] = dict()
            previous_position = position
            position = position.get(str(key))

        previous_position[str(key)] = value
        file.seek(0)
        json.dump(file_json, file, indent=2)
        file.truncate()

def write_sql(table_name: str, guild_id: int, column_name: str, value: any):
    database_url = os.getenv("DATABASE_URL")
    with psycopg2.connect(database_url, sslmode="require") as conn:
        query = f"INSERT INTO {table_name} (guild_id, {column_name}) VALUES ({guild_id}, {value}) ON CONFLICT (guild_id) DO UPDATE SET {column_name}={value};"
        with conn.cursor() as cursor:
            cursor.execute(query)
            conn.commit()