from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from openai import AzureOpenAI
import requests
import psycopg2
from resources import RESOURCES
import os
from dotenv import load_dotenv

# ======================
# LOAD ENV
# ======================
load_dotenv()

app = FastAPI()

# ======================
# CORS
# ======================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ======================
# AZURE OPENAI
# ======================
client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_KEY"),
    api_version="2024-02-15-preview",
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
)

# ======================
# FETCH SERVERS
# ======================
def get_all_servers():
    results = []

    for s in RESOURCES["servers"]:
        try:
            res = requests.get(s["url"], timeout=3)

            if res.status_code == 200:
                data = res.json()
                data["name"] = s["name"]
                results.append(data)
            else:
                results.append({
                    "name": s["name"],
                    "status": "down",
                    "error": f"status {res.status_code}"
                })

        except Exception as e:
            results.append({
                "name": s["name"],
                "status": "down",
                "error": str(e)
            })

    return results


# ======================
# FETCH DATABASES
# ======================
def get_all_databases():
    db_results = []

    for db in RESOURCES["databases"]:
        if db["type"] == "postgres":
            try:
                conn = psycopg2.connect(
                    host=db["host"],
                    user=db["user"],
                    password=db["password"],
                    dbname=db["dbname"],
                    sslmode="require"
                )

                cur = conn.cursor()

                # connections
                cur.execute("SELECT count(*) FROM pg_stat_activity;")
                connections = cur.fetchone()[0]

                # table scans
                cur.execute("""
                    SELECT relname, seq_scan
                    FROM pg_stat_user_tables
                    ORDER BY seq_scan DESC
                    LIMIT 3;
                """)
                tables = cur.fetchall()

                # active queries
                cur.execute("""
                    SELECT state, count(*)
                    FROM pg_stat_activity
                    GROUP BY state;
                """)
                activity = cur.fetchall()

                db_results.append({
                    "name": db["name"],
                    "status": "running",
                    "connections": connections,
                    "table_activity": tables,
                    "activity": activity
                })

                conn.close()

            except Exception as e:
                db_results.append({
                    "name": db["name"],
                    "status": "down",
                    "error": str(e)
                })

    return db_results


# ======================
# ROOT
# ======================
@app.get("/")
def home():
    return {"message": "Server-Orch running 🚀"}


# ======================
# MAIN AI ENDPOINT
# ======================
@app.get("/ask")
def ask(q: str):
    try:
        servers = get_all_servers()
        databases = get_all_databases()

        context = f"""
        Servers:
        {servers}

        Databases:
        {databases}
        """

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """
You are an expert DevOps + Database AI assistant.

Rules:
- Answer short and clear
- Explain WHY issues happen
- Use server + DB data
- Do NOT dump raw data
"""
                },
                {
                    "role": "user",
                    "content": f"{context}\n\nQuestion: {q}"
                }
            ]
        )

        return {
            "servers": servers,
            "databases": databases,
            "answer": response.choices[0].message.content
        }

    except Exception as e:
        return {
            "error": "Something failed",
            "details": str(e)
        }