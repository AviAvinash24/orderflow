from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from app.core.db import close_db, connect_db
from app.core.deps import CurrentUser, get_current_user
from app.routers.auth import router as auth_router
from app.routers.products import router as products_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()
    yield
    await close_db()


app = FastAPI(title="Orderflow", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(products_router)


@app.get("/health")
def health_check():
    return {"status": "Ok"}


@app.get("/me")
async def me(current_user: CurrentUser = Depends(get_current_user)):
    return {"user_id": current_user.id, "email": current_user.email}