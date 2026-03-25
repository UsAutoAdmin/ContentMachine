from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import TEMPLATES_DIR

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/", response_class=HTMLResponse)
async def home():
    return templates.TemplateResponse("dashboard.html", {"request": {}})


@router.get("/content-lab", response_class=HTMLResponse)
async def content_lab():
    return templates.TemplateResponse("content_lab.html", {"request": {}})


@router.get("/performance", response_class=HTMLResponse)
async def performance():
    return templates.TemplateResponse("performance.html", {"request": {}})


@router.get("/teleprompter", response_class=HTMLResponse)
async def teleprompter():
    return templates.TemplateResponse("teleprompter.html", {"request": {}})


@router.get("/bulk", response_class=HTMLResponse)
async def bulk_page():
    return templates.TemplateResponse("bulk.html", {"request": {}})
