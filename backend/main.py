from fastapi import FastAPI
from backend.models import AllocationRequest
from backend.optimizer import allocate_resources
import json
from pathlib import Path

from backend.models import Village, Inventory

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

@app.post("/allocate")
def allocate(request: AllocationRequest):
    result = allocate_resources(
        request.locations,
        request.inventory
    )
    return result


@app.get("/scenario")
def get_scenario():
    data_dir = Path(__file__).resolve().parent.parent / "data"

    with open(data_dir / "villages.json", encoding="utf-8") as file:
        villages = json.load(file)

    with open(data_dir / "inventory.json", encoding="utf-8") as file:
        inventory = json.load(file)

    return {
        "locations": villages,
        "inventory": inventory,
    }


@app.post("/allocate-scenario")
def allocate_scenario():
    scenario = get_scenario()

    request = AllocationRequest(
        locations=scenario["locations"],
        inventory=scenario["inventory"]
    )

    return allocate_resources(
        request.locations,
        request.inventory
    )
