"""
Looks up packaged products in the Open Food Facts database, either by
barcode (most reliable) or by fuzzy name search (fallback when Gemini
identifies a product but no barcode is visible).
"""
import httpx
from app.core.config import get_settings


class OpenFoodFactsService:
    def __init__(self):
        settings = get_settings()
        self.base_url = settings.off_base_url
        self.search_url = settings.off_search_url

    async def lookup_by_barcode(self, barcode: str) -> dict | None:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{self.base_url}/product/{barcode}.json")
            if resp.status_code != 200:
                return None
            data = resp.json()
            if data.get("status") != 1:
                return None
            return data.get("product")

    async def search_by_name(self, name: str, brand: str | None = None, limit: int = 5) -> list[dict]:
        query = f"{name} {brand}".strip() if brand else name
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                self.search_url,
                params={
                    "search_terms": query,
                    "search_simple": 1,
                    "action": "process",
                    "json": 1,
                    "page_size": limit,
                },
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            return data.get("products", [])

    @staticmethod
    def extract_nutrition(product: dict) -> dict:
        """Normalizes an OFF product payload into our internal nutrition shape (per 100g)."""
        n = product.get("nutriments", {})
        nova_group = product.get("nova_group")
        return {
            "calories": n.get("energy-kcal_100g", 0) or 0,
            "protein": n.get("proteins_100g", 0) or 0,
            "carbs": n.get("carbohydrates_100g", 0) or 0,
            "fat": n.get("fat_100g", 0) or 0,
            "fiber": n.get("fiber_100g", 0) or 0,
            "sugar": n.get("sugars_100g", 0) or 0,
            "added_sugar": n.get("sugars_100g", 0) or 0,  # OFF doesn't separate added sugar
            "sodium": (n.get("sodium_100g", 0) or 0) * 1000,  # g -> mg
            "saturated_fat": n.get("saturated-fat_100g", 0) or 0,
            "trans_fat": n.get("trans-fat_100g", 0) or 0,
            "cholesterol": n.get("cholesterol_100g", 0) or 0,
            "potassium": n.get("potassium_100g", 0) or 0,
            "additives": product.get("additives_tags", []),
            "allergens": [
                a.replace("en:", "").replace("-", " ").title()
                for a in product.get("allergens_tags", [])
            ],
            "is_ultra_processed": (nova_group == 4) if nova_group else False,
            "ingredients_text": product.get("ingredients_text", ""),
            "product_name": product.get("product_name", ""),
            "brand": product.get("brands", "").split(",")[0].strip() if product.get("brands") else None,
            "image_url": product.get("image_url"),
        }


_off_service: OpenFoodFactsService | None = None


def get_off_service() -> OpenFoodFactsService:
    global _off_service
    if _off_service is None:
        _off_service = OpenFoodFactsService()
    return _off_service
