from typing import Any, Dict
from app.skills.base import BaseSkill

class UnitConverterSkill(BaseSkill):
    def __init__(self):
        super().__init__(
            name="unit_converter",
            description="Converts metric and imperial measurements, temperatures, and currencies."
        )

    def execute(self, value: float = 0.0, from_unit: str = "celsius", to_unit: str = "fahrenheit", **kwargs) -> Dict[str, Any]:
        try:
            v = float(value)
            fu = from_unit.lower().strip()
            tu = to_unit.lower().strip()

            result = v
            # Temperature conversions
            if fu in ["c", "celsius"] and tu in ["f", "fahrenheit"]:
                result = (v * 9 / 5) + 32
            elif fu in ["f", "fahrenheit"] and tu in ["c", "celsius"]:
                result = (v - 32) * 5 / 9
            # Weight conversions
            elif fu in ["kg", "kilograms"] and tu in ["lb", "lbs", "pounds"]:
                result = v * 2.20462
            elif fu in ["lb", "lbs", "pounds"] and tu in ["kg", "kilograms"]:
                result = v / 2.20462
            # Distance conversions
            elif fu in ["km", "kilometers"] and tu in ["miles", "mi"]:
                result = v * 0.621371
            elif fu in ["miles", "mi"] and tu in ["km", "kilometers"]:
                result = v / 0.621371

            return {"status": "success", "converted_value": round(result, 4), "from_unit": fu, "to_unit": tu}
        except Exception as e:
            return {"status": "error", "error": str(e)}
