import os
import chromadb
from chromadb.api.types import Metadata
from typing import List, cast
from db.interface import FoodRecallAlertsDBInterface
from backend.models.recall_alert import FoodRecallAlert

class FoodRecallAlertsChromaClient(FoodRecallAlertsDBInterface):
    def __init__(self):
        db_path = os.path.join(os.path.dirname(__file__), "..", ".chroma_data")
        self.client = chromadb.PersistentClient(path=db_path)

        self.collection = self.client.get_or_create_collection(name="food_recall_alerts_collection")

    def save_alerts(self, alerts: List[FoodRecallAlert]) -> int:
        if not alerts:
            return 0

        incoming_ids = [alert.get_id() for alert in alerts]

        existing_records = self.collection.get(ids=incoming_ids, include=[])
        existing_ids = set(existing_records["ids"])

        new_alerts = [alert for alert in alerts if alert.get_id() not in existing_ids]
        if not new_alerts:
            return 0

        insert_ids = [alert.get_id() for alert in new_alerts]
        insert_documents = [alert.to_document() for alert in new_alerts]
        insert_metadatas = [cast(Metadata, alert.to_metadata()) for alert in new_alerts]

        self.collection.add(
            ids=insert_ids,
            documents=insert_documents,
            metadatas=insert_metadatas
        )

        return len(new_alerts)

    def get_alerts(self) -> List[FoodRecallAlert]:
        results = self.collection.get(include=["metadatas"])
        metadatas = results.get("metadatas")
        if not metadatas:
            return []
        
        parsed_alerts = []
        for metadata in metadatas:
            if metadata is not None:
                safe_metadata = dict(metadata)
                parsed_alerts.append(FoodRecallAlert.from_metadata(safe_metadata))
                
        parsed_alerts.sort(key=lambda x: x.recall_date, reverse=True)
        
        return parsed_alerts