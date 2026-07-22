import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from db.chroma_early_warning_client import InMemoryEarlyWarningIncidentStore
from dependencies import get_early_warning_incident_service
from models.early_warning_incident import EarlyWarningIncidentCreate, IncidentType
from routes.incidents import router
from services.early_warning.incidents import EarlyWarningIncidentService


class IncidentsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = EarlyWarningIncidentService(InMemoryEarlyWarningIncidentStore())
        self.incident = self.service.save_incident(
            EarlyWarningIncidentCreate(
                incident_type=IncidentType.INVESTIGATION,
                product_name="Sample salad",
                summary="Authorities are investigating reported illnesses.",
                country="Canada",
                primary_source_url="https://example.test/investigation",
            )
        )
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_early_warning_incident_service] = lambda: self.service
        self.client = TestClient(app)

    def test_list_detail_stats_and_version(self) -> None:
        listing = self.client.get("/api/incidents", params={"search": "salad"})
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["incidents"][0]["incident_id"], self.incident.incident_id)

        detail = self.client.get(f"/api/incidents/{self.incident.incident_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["incident_type"], "investigation")

        stats = self.client.get("/api/incidents/stats").json()
        self.assertEqual(stats["pending"], 1)
        version = self.client.get("/api/incidents/version").json()
        self.assertEqual(version["count"], 1)
        self.assertEqual(len(version["fingerprint"]), 64)


if __name__ == "__main__":
    unittest.main()
