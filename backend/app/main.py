from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="ByteSmiths — Personal Finance Copilot API",
    version="0.1.0",
    description="Deterministic cash flow, financial goal feasibility, and scenario testing engine.",
)

# Enable CORS for local React development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check():
    """Health check endpoint to verify backend service readiness."""
    return {
        "status": "ok",
        "app": "ByteSmiths Finance Copilot",
        "version": "0.1.0",
    }
