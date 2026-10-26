from fastapi import FastAPI, HTTPException, status
from pdf_knowledge import router as pdf_knowledge_router
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import JSONResponse
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
from account_auth import AccountMiddleware, router as account_auth_router
from account_recovery import router as account_recovery_router
from account_sessions import router as account_sessions_router
from operations_readiness import router as operations_readiness_router
from instagram_simulation import router as instagram_simulation_router
from instagram_provider_lab import router as instagram_provider_lab_router
from instagram_persistent_oauth import router as instagram_persistent_oauth_router
from waha_ingress import router as waha_ingress_router
from instagram_direct_outbox import router as instagram_direct_router
from instagram_meta_ingress import WebhookQueryPrivacy, router as instagram_meta_ingress_router
from workspace_profile import router as workspace_profile_router
from message_enrichment import router as message_enrichment_router, internal_router as enrichment_internal_router
from content_preparation import router as content_preparation_router
from channel_ingress import router as channel_ingress_router, internal_router as channel_ingress_internal_router
from opportunities import router as opportunities_router
from integration_setup import router as integration_setup_router
from settings import cors_origins as configured_cors_origins

from instagram_runtime import runtime_lifespan, router as integration_readiness_router
from instagram_publishing import router as instagram_publishing_router
from instagram_media import InstagramMediaPrivacy, router as instagram_media_router

app = FastAPI(title="SocialME Python Service", lifespan=runtime_lifespan)
app.include_router(integration_readiness_router)
app.include_router(instagram_publishing_router)
app.include_router(instagram_media_router)
app.add_middleware(AccountMiddleware)
cors_origins = configured_cors_origins()
if cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Accept"],
        allow_credentials=False,
    )
app.include_router(pdf_knowledge_router)
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
app.include_router(account_auth_router)
app.include_router(account_recovery_router)
app.include_router(account_sessions_router)
app.include_router(operations_readiness_router)
app.include_router(instagram_simulation_router)
app.include_router(instagram_provider_lab_router)
app.include_router(instagram_persistent_oauth_router)
app.include_router(instagram_meta_ingress_router)
app.include_router(instagram_direct_router)
app.include_router(waha_ingress_router)
app.include_router(workspace_profile_router)
app.include_router(message_enrichment_router)
app.include_router(enrichment_internal_router)
app.include_router(content_preparation_router)
app.include_router(channel_ingress_router)
app.include_router(channel_ingress_internal_router)
app.include_router(opportunities_router)
app.include_router(integration_setup_router)


@app.middleware("http")
async def internal_response_privacy(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(("/internal/waha", "/internal/message-enrichment", "/internal/channel-ingress", "/api/v1/content/preparation", "/api/v1/channel-lab", "/api/v1/opportunities", "/api/v1/integrations/setup")):
        response.headers["Cache-Control"] = "no-store"
    if request.url.path.startswith("/internal/waha"):
        response.headers["X-Content-Type-Options"] = "nosniff"
    return response


app.add_middleware(InstagramMediaPrivacy)
app.add_middleware(WebhookQueryPrivacy)


@app.exception_handler(RequestValidationError)
async def private_validation_error(request, error):
    # FastAPI's default validation response includes submitted values, including passwords.
    if request.url.path.startswith(
        ("/api/v1/auth/", "/api/v1/admin/", "/api/v1/instagram/", "/api/v1/workspace-profile", "/api/v1/message-enrichment", "/internal/message-enrichment", "/api/v1/channel-lab", "/internal/channel-ingress", "/api/v1/content/preparation", "/api/v1/opportunities", "/api/v1/integrations/setup")
    ):
        return JSONResponse(
            {"detail": "Confira os campos informados."},
            status_code=422,
            headers={"Cache-Control": "no-store"},
        )
    return await request_validation_exception_handler(request, error)


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
            detail="Persistência compartilhada ou autenticação indisponível neste ambiente.",
        ) from error


@app.post("/processar")
def process_text(payload: TextInput):
    text = payload.text
    return {
        "original": text,
        "maiusculo": text.upper(),
        "quantidade_caracteres": len(text),
    }
