from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.core.config import settings
from app.core.database import engine, get_db
from app.core.security import get_current_user
from app.models import base  # noqa: F401 — ensure models are registered
from app.models.user import User
from app.api import auth, contacts, meetings, interactions, briefs, matches


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    yield
    # shutdown
    await engine.dispose()


app = FastAPI(
    title="synco",
    description="AI CRM & Business Matching",
    version="0.1.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# API routes
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(contacts.router, prefix="/contacts", tags=["contacts"])
app.include_router(meetings.router, prefix="/meetings", tags=["meetings"])
app.include_router(interactions.router, prefix="/interactions", tags=["interactions"])
app.include_router(briefs.router, prefix="/briefs", tags=["briefs"])
app.include_router(matches.router, prefix="/matches", tags=["matches"])


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(request, "pages/index.html")


@app.get("/dashboard")
async def dashboard(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    return templates.TemplateResponse(
        request, "pages/dashboard.html",
        context={"user": current_user, "active_nav": "briefing"},
    )
