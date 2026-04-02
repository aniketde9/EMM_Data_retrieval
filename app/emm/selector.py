import json
import os


BODIES_DIR = os.path.join(os.path.dirname(__file__), "bodies")


def select(cluster: str) -> dict:
    mapping = {
        "Discovery": "discovery.json",
        "Conversion": "conversion.json",
        "Capacity": "capacity.json",
    }
    filename = mapping.get(cluster, "discovery.json")
    with open(os.path.join(BODIES_DIR, filename), "r", encoding="utf-8") as f:
        return json.load(f)
