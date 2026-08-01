"""NFS-e SP: API REST, servidor MCP e frontend estatico."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import auth, certificado, chaves, config, notas
from app.core.db import init_db
from app.mcp_server import ciclo_de_vida_mcp, montagem_mcp

FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # O servidor MCP precisa do proprio ciclo de vida para servir streamable
    # HTTP; sem isso a primeira chamada em /mcp falha.
    async with ciclo_de_vida_mcp():
        yield


app = FastAPI(title="NFS-e SP", docs_url=None, redoc_url=None, lifespan=lifespan)

app.include_router(auth.router)
app.include_router(notas.router)
app.include_router(config.router)
app.include_router(certificado.router)
app.include_router(chaves.router)

# Servidor MCP para LLMs. Autenticado por chave de API no proprio app montado.
app.mount("/mcp", montagem_mcp)


@app.get("/api/health")
def health():
    return {"ok": True}


if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{caminho:path}")
    def spa(caminho: str):
        arquivo = FRONTEND_DIST / caminho
        if caminho and arquivo.is_file():
            return FileResponse(arquivo)
        return FileResponse(FRONTEND_DIST / "index.html")
