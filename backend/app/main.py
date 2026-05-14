from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.alerts import router as alerts_router
from app.api.v1.auth import router as auth_router
from app.api.v1.billing import router as billing_router
from app.api.v1.contracts import router as contracts_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.imports import router as imports_router
from app.api.v1.organizations import router as organizations_router
from app.api.v1.registry import router as registry_router
from app.api.v1.users import router as users_router

app = FastAPI(title="CEO24", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(alerts_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(billing_router, prefix="/api/v1")
app.include_router(contracts_router, prefix="/api/v1")
app.include_router(dashboard_router, prefix="/api/v1")
app.include_router(imports_router, prefix="/api/v1")
app.include_router(organizations_router, prefix="/api/v1")
app.include_router(registry_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
