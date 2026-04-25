from fastapi import APIRouter, HTTPException, Depends
from app.models import (
    RegisterRequest,
    LoginRequest,
    AuthResponse,
    UserProfile,
    RefreshRequest,
)
from app.auth import get_supabase, get_user_supabase, get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse)
async def register(req: RegisterRequest):
    """
    Register a new user.
    The profile row in public.profiles is created automatically by the
    on_auth_user_created trigger, which reads name/year/subjects from
    raw_user_meta_data. We just pass them as options.data on sign_up.
    """
    supabase = get_supabase()
    try:
        auth_response = supabase.auth.sign_up({
            "email": req.email,
            "password": req.password,
            "options": {
                "data": {
                    "name": req.name,
                    "colegiado_number": req.colegiado_number or "",
                }
            },
        })

        if not auth_response.user:
            raise HTTPException(status_code=400, detail="Registration failed")

        if not auth_response.session:
            # Email confirmation is enabled in Supabase Auth settings.
            # Without a session we have no JWT to return; user must confirm
            # via email, then log in.
            raise HTTPException(
                status_code=400,
                detail=(
                    "Email confirmation required. Check your inbox, confirm "
                    "your email, then log in."
                ),
            )

        return AuthResponse(
            access_token=auth_response.session.access_token,
            refresh_token=auth_response.session.refresh_token,
            user_id=auth_response.user.id,
            email=req.email,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest):
    """Log in an existing user."""
    supabase = get_supabase()
    try:
        auth_response = supabase.auth.sign_in_with_password({
            "email": req.email,
            "password": req.password
        })

        if not auth_response.user:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        return AuthResponse(
            access_token=auth_response.session.access_token,
            refresh_token=auth_response.session.refresh_token,
            user_id=auth_response.user.id,
            email=auth_response.user.email,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.post("/refresh", response_model=AuthResponse)
async def refresh(req: RefreshRequest):
    """
    Exchange a refresh token for a fresh access + refresh token pair.
    This is the mechanism the frontend uses to silently recover from
    expired access tokens (Supabase default is 1 hour) without pushing
    the user back to the login screen.
    """
    supabase = get_supabase()
    try:
        auth_response = supabase.auth.refresh_session(req.refresh_token)
        if not auth_response.session or not auth_response.user:
            raise HTTPException(status_code=401, detail="Refresh failed")
        return AuthResponse(
            access_token=auth_response.session.access_token,
            refresh_token=auth_response.session.refresh_token,
            user_id=auth_response.user.id,
            email=auth_response.user.email,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Refresh failed: {e}")


@router.get("/profile", response_model=UserProfile)
async def get_profile(user=Depends(get_current_user)):
    """Get current user's profile."""
    client = get_user_supabase(user["token"])
    try:
        result = client.table("profiles").select("*").eq("id", user["id"]).single().execute()
        return UserProfile(**result.data)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Profile not found: {str(e)}")


@router.put("/profile", response_model=UserProfile)
async def update_profile(updates: dict, user=Depends(get_current_user)):
    """Update current user's profile."""
    client = get_user_supabase(user["token"])
    allowed_fields = {"name", "colegiado_number"}
    filtered = {k: v for k, v in updates.items() if k in allowed_fields}

    try:
        result = client.table("profiles").update(filtered).eq("id", user["id"]).execute()
        return UserProfile(**result.data[0])
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/account")
async def delete_account(user=Depends(get_current_user)):
    """
    Permanently delete the calling user's account.

    Invokes the `public.delete_user` SECURITY DEFINER RPC in the database,
    which uses `auth.uid()` internally to identify the caller and deletes
    the corresponding row from `auth.users`. The existing `on delete cascade`
    foreign keys take care of `profiles`, `conversations`, and `messages`.
    """
    client = get_user_supabase(user["token"])
    try:
        client.rpc("delete_user", {}).execute()
        return {"status": "deleted"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
