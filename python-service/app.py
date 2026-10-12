import os

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from shared_data import database_health_payload, router as shared_data_router
from client_import import router as client_import_router
from catalog_data import router as catalog_router
from product_import import router as product_import_router
from sales_data import router as sales_router
from sale_import import router as sale_import_router

from finance_data import router as finance_router
from finance_import import router as finance_import_router

from workspace_transfer import router as transfer_router
from n8n_read import router as n8n_read_router

app = FastAPI(title="SocialME Python Service")
cors_origins = [
    origin.strip()
    for origin in os.getenv("SOCIALMEI_CORS_ORIGINS", "").split(",")
    if origin.strip()
]
if cors_origins:
    if "*" in cors_origins:
        raise RuntimeError("Configure origens CORS explícitas, sem wildcard.")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Accept"],
        allow_credentials=False,
    )
app.include_router(shared_data_router)
app.include_router(client_import_router)
app.include_router(catalog_router)
app.include_router(product_import_router)
app.include_router(sales_router)
app.include_router(sale_import_router)
app.include_router(finance_router)
app.include_router(finance_import_router)
app.include_router(transfer_router)
app.include_router(n8n_read_router)


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
