import os
import time
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

# Configure logging to stdout for OpenShift log scraping
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

app = FastAPI(
    title="SafeKeeper API",
    description="Encrypted text notes manager running on OpenShift 4.22",
    version="1.0.0"
)

# Pydantic Schemas for Request/Response validation
class NoteCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255, example="Secret Note")
    content: str = Field(..., min_length=1, example="Top secret payload content")

class NoteResponse(BaseModel):
    id: int
    title: str
    content: str

# Database Connection Helper with retry logic during container startup
def get_db_connection():
    db_user = os.getenv("DB_USER", "postgres")
    db_pass = os.getenv("DB_PASSWORD", "postgres")
    db_name = os.getenv("DB_NAME", "safekeeper")
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")

    retries = 10
    while retries > 0:
        try:
            conn = psycopg2.connect(
                host=db_host,
                port=db_port,
                dbname=db_name,
                user=db_user,
                password=db_pass,
                connect_timeout=3
            )
            return conn
        except psycopg2.OperationalError as e:
            logging.warning(f"Database connection waiting... ({11 - retries}/10 attempts)")
            retries -= 1
            time.sleep(2)
            if retries == 0:
                logging.error("Could not establish connection to PostgreSQL.")
                raise e

# Initialize Table Schema on startup
@app.on_event("startup")
def startup_event():
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS notes (
                    id SERIAL PRIMARY KEY,
                    title VARCHAR(255) NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()
        conn.close()
        logging.info("Successfully connected to PostgreSQL and verified database schema.")
    except Exception as e:
        logging.error(f"Failed to initialize database on startup: {e}")

# GET /health - Readiness & Liveness Probe Endpoint
@app.get("/health", status_code=status.HTTP_200_OK)
def health_check():
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT 1;")
        conn.close()
        return {"status": "HEALTHY", "database": "connected"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "UNHEALTHY", "error": str(e)}
        )

# POST /notes - Create a new note
@app.post("/notes", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
def create_note(note: NoteCreate):
    try:
        conn = get_db_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "INSERT INTO notes (title, content) VALUES (%s, %s) RETURNING id, title, content;",
                (note.title, note.content)
            )
            new_note = cur.fetchone()
            conn.commit()
        conn.close()
        return new_note
    except Exception as e:
        logging.error(f"Error creating note: {e}")
        raise HTTPException(status_code=500, detail="Failed to write note to database")

# GET /notes/{note_id} - Retrieve a note by ID
@app.get("/notes/{note_id}", response_model=NoteResponse)
def get_note(note_id: int):
    try:
        conn = get_db_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id, title, content FROM notes WHERE id = %s;", (note_id,))
            note = cur.fetchone()
        conn.close()
        
        if not note:
            raise HTTPException(status_code=404, detail="Note not found")
        
        return note
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error reading note ID {note_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to read note from database")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
