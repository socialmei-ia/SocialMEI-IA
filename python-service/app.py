from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from shared_data import database_health_payload, router as shared_data_router
from client_import import router as client_import_router

app = FastAPI(title="SocialME Python Service")
app.include_router(shared_data_router)
app.include_router(client_import_router)


class TextInput(BaseModel):
    # Mantém o contrato usado pelo workflow n8n.
    text: str = Field(alias="texto")


@app.get("/")
def root():
    return {"status": "ok", "service": "socialmei-python"}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/health/db")
def health_db():
    try:
        return database_health_payload()
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PostgreSQL indisponível para a persistência compartilhada.",
        ) from error


@app.post("/processar")
def process_text(payload: TextInput):
    text = payload.text
    return {
        "original": text,
        "maiusculo": text.upper(),
        "quantidade_caracteres": len(text),
    }
