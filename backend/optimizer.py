from scipy.optimize import linprog


def allocate_resources(locations, inventory):
    """
    Maximize urgency-weighted food and water delivered.

    Each village's food and water are optimized separately.
    This is a simplified model: urgency determines the priority
    weight, while needs and available inventory are hard limits.
    """

    ranked_locations = sorted(
        locations,
        key=lambda village: village.id
    )

    results = []

    # Optimize food and water independently because they use
    # different units and have different available inventories.
    for resource in ("food", "water"):
        needs = [
            getattr(village, f"{resource}_needed")
            for village in ranked_locations
        ]

        available = getattr(inventory, resource)

        # linprog minimizes, so negative urgency maximizes delivery
        # to higher-urgency villages.
        objective = [
            -village.urgency for village in ranked_locations
        ]

        solution = linprog(
            c=objective,
            A_ub=[ [1] * len(needs) ],
            b_ub=[available],
            bounds=[
                (0, need) for need in needs
            ],
            method="highs",
        )

        if not solution.success:
            raise RuntimeError(
                f"Could not optimize {resource}: {solution.message}"
            )

        for index, amount in enumerate(solution.x):
            if resource == "food":
                results.append({
                    "village_id": ranked_locations[index].id,
                    "village_name": ranked_locations[index].name,
                    "urgency": ranked_locations[index].urgency,
                    "food_allocated": int(round(amount)),
                    "water_allocated": 0,
                    "food_unmet": needs[index] - int(round(amount)),
                    "water_unmet": ranked_locations[index].water_needed,
                })
            else:
                rounded_amount = int(round(amount))
                row = next(
                    item for item in results
                    if item["village_id"] == ranked_locations[index].id
                )
                row["water_allocated"] = rounded_amount
                row["water_unmet"] = (
                    needs[index] - rounded_amount
                )

    return {
        "allocations": results,
        "remaining_inventory": {
            resource: getattr(inventory, resource)
            - sum(
                item[f"{resource}_allocated"]
                for item in results
            )
            for resource in ("food", "water")
        },
    }
