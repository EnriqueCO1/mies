from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from supabase import create_client
from app.config import settings

security = HTTPBearer()


def get_supabase():
    """Get an anon-key Supabase client (no user session attached)."""
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)


def get_user_supabase(token: str):
    """
    Get a Supabase client authenticated as the caller.
    All PostgREST queries made with this client run under the user's JWT,
    so RLS sees `auth.uid() = <user_id>` and row-level policies apply.
    """
    client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
    client.postgrest.auth(token)
    return client


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Validate JWT token and return user info."""
    token = credentials.credentials
    try:
        supabase = get_supabase()
        user_response = supabase.auth.get_user(token)
        if not user_response or not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {
            "id": user_response.user.id,
            "email": user_response.user.email,
            "token": token
        }
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")
