from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.db import close_db, connect_db
from app.routers.auth import router as auth_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()
    yield
    await close_db()


app = FastAPI(title="Orderflow", lifespan=lifespan)
app.include_router(auth_router)


@app.get("/health")
def health_check():
    return {"status": "Ok"}