import os
from dotenv import load_dotenv

# override=True ensures values in backend/.env always win over stray shell
# exports (e.g. an empty ANTHROPIC_API_KEY lingering in the user's terminal).
load_dotenv(override=True)


class Settings:
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")


settings = Settings()
