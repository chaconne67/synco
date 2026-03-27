from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.contact import Contact

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/")
async def list_contacts(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Contact)
        .where(Contact.fc_id == current_user.id)
        .order_by(Contact.last_interaction_at.desc().nullslast())
    )
    contacts = result.scalars().all()
    return templates.TemplateResponse(
        request, "pages/contacts.html",
        context={"contacts": contacts, "user": current_user},
    )


@router.post("/")
async def create_contact(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    form = await request.form()
    contact = Contact(
        fc_id=current_user.id,
        name=form.get("name", ""),
        phone=form.get("phone"),
        company_name=form.get("company_name"),
        industry=form.get("industry"),
        region=form.get("region"),
        memo=form.get("memo"),
    )
    db.add(contact)
    await db.commit()
    await db.refresh(contact)

    # HTMX partial response
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            request, "components/contact_card.html",
            context={"contact": contact},
        )
    return templates.TemplateResponse(
        request, "pages/contacts.html",
        context={"contacts": [contact], "user": current_user},
    )
