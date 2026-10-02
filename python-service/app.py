from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="SocialME Python Service")


class TextoEntrada(BaseModel):
    texto: str


@app.get("/")
def root():
    return {
        "status": "ok",
        "service": "socialmei-python"
    }


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/processar")
def processar(dados: TextoEntrada):
    texto = dados.texto

    return {
        "original": texto,
        "maiusculo": texto.upper(),
        "quantidade_caracteres": len(texto)
    }
