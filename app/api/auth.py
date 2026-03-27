from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

from app.core.config import settings
from app.core.database import get_db
from app.core.security import TOKEN_COOKIE, create_access_token, get_current_user
from app.models.user import User

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

KAKAO_AUTH_URL = "https://kauth.kakao.com/oauth/authorize"
KAKAO_TOKEN_URL = "https://kauth.kakao.com/oauth/token"
KAKAO_USER_URL = "https://kapi.kakao.com/v2/user/me"


@router.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse(request, "pages/login.html")


@router.get("/kakao")
async def kakao_login():
    params = {
        "client_id": settings.kakao_client_id,
        "redirect_uri": settings.kakao_redirect_uri,
        "response_type": "code",
    }
    url = f"{KAKAO_AUTH_URL}?{'&'.join(f'{k}={v}' for k, v in params.items())}"
    return RedirectResponse(url)


@router.get("/kakao/callback")
async def kakao_callback(code: str, db: AsyncSession = Depends(get_db)):
    # Exchange code for token
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            KAKAO_TOKEN_URL,
            data={
                k: v for k, v in {
                    "grant_type": "authorization_code",
                    "client_id": settings.kakao_client_id,
                    "client_secret": settings.kakao_client_secret or None,
                    "redirect_uri": settings.kakao_redirect_uri,
                    "code": code,
                }.items() if v
            },
        )
        token_data = token_resp.json()
        if "access_token" not in token_data:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=400,
                content={"error": "카카오 로그인 실패", "detail": token_data},
            )
        access_token = token_data["access_token"]

        # Get user info
        user_resp = await client.get(
            KAKAO_USER_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        user_data = user_resp.json()

    kakao_id = str(user_data["id"])
    kakao_account = user_data.get("kakao_account", {})
    profile = kakao_account.get("profile", {})

    # Find or create user
    result = await db.execute(select(User).where(User.kakao_id == kakao_id))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            kakao_id=kakao_id,
            name=profile.get("nickname", ""),
            profile_image=profile.get("profile_image_url"),
            email=kakao_account.get("email"),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    jwt_token = create_access_token(user.id)

    # Redirect based on role
    if user.role is None:
        redirect_url = "/auth/select-role"
    else:
        redirect_url = "/dashboard"

    response = RedirectResponse(redirect_url)
    response.set_cookie(
        key=TOKEN_COOKIE,
        value=jwt_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=settings.jwt_expire_minutes * 60,
    )
    return response


@router.get("/select-role")
async def select_role_page(request: Request, current_user: User = Depends(get_current_user)):
    return templates.TemplateResponse(
        request, "pages/select_role.html", context={"user": current_user}
    )


@router.post("/select-role")
async def select_role(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    form = await request.form()
    role = form.get("role")
    if role not in ("fc", "ceo"):
        return RedirectResponse("/auth/select-role", status_code=303)

    current_user.role = role
    await db.commit()

    return RedirectResponse("/dashboard", status_code=303)
