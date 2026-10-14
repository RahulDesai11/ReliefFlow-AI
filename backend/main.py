from fastapi import FastAPI

app = FastAPI(
    title="ReliefFlow AI",
    description="Flood relief resource allocation system",
    version="0.1.0",
)


@app.get("/")
def home():
    return {
        "project": "ReliefFlow AI",
        "status": "running",
        "scenario": "Flood-affected villages",
        "message": "Disaster relief allocation backend is ready."
    }


@app.get("/health")
def health_check():
    return {"status": "healthy"}
