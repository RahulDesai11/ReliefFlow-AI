
from backend.models import Village, Inventory
from backend.optimizer import allocate_resources


def test_allocation_never_exceeds_inventory():
    locations = [
        Village(
            id="V001",
            name="Village A",
            urgency=5,
            people_affected=500,
            food_needed=100,
            water_needed=200,
        ),
        Village(
            id="V002",
            name="Village B",
            urgency=3,
            people_affected=300,
            food_needed=150,
            water_needed=100,
        ),
    ]

    inventory = Inventory(food=120, water=250)

    result = allocate_resources(locations, inventory)

    total_food = sum(
        item["food_allocated"] for item in result["allocations"]
    )
    total_water = sum(
        item["water_allocated"] for item in result["allocations"]
    )

    assert total_food <= inventory.food
    assert total_water <= inventory.water


def test_allocation_never_exceeds_village_needs():
    locations = [
        Village(
            id="V001",
            name="Village A",
            urgency=5,
            people_affected=500,
            food_needed=100,
            water_needed=200,
        )
    ]

    result = allocate_resources(
        locations,
        Inventory(food=500, water=500),
    )

    allocation = result["allocations"][0]

    assert allocation["food_allocated"] <= 100
    assert allocation["water_allocated"] <= 200
