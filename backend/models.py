from pydantic import BaseModel, Field
from typing import List


class Village(BaseModel):
    id: str
    name: str
    urgency: int = Field(ge=1, le=5)
    people_affected: int = Field(ge=0)
    food_needed: int = Field(ge=0)
    water_needed: int = Field(ge=0)


class Inventory(BaseModel):
    food: int = Field(ge=0)
    water: int = Field(ge=0)


class AllocationRequest(BaseModel):
    locations: List[Village]
    inventory: Inventory