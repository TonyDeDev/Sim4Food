import os

# TEMP: placeholder pointing at a local Docker Postgres.
# The real URL comes from the POSTGRES_URL env var once the Docker DB owner shares it.
TEMP_POSTGRES_URL = "postgresql://postgres:postgres@localhost:5432/sim4food"

POSTGRES_URL = os.getenv("POSTGRES_URL", TEMP_POSTGRES_URL)

# Frontend origins allowed by CORS (comma separated).
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]
