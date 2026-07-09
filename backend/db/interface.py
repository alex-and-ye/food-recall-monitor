from abc import ABC, abstractmethod
from typing import List, Optional

from models.food_recall_alert import FoodRecallAlert, FoodRecallAlertCreate, FoodRecallAlertsVersion

class FoodRecallAlertsDBInterface(ABC):
    @abstractmethod
    def get_alerts(self) -> List[FoodRecallAlert]:
        pass

    @abstractmethod
    def get_alert_by_id(self, alert_id: str) -> Optional[FoodRecallAlert]:
        pass

    @abstractmethod
    def search_alerts(self, search: str | None = None, risk_level: str | None = None, country_source: str | None = None) -> List[FoodRecallAlert]:
        pass

    @abstractmethod
    def save_alerts(self, alerts: List[FoodRecallAlertCreate]) -> int:
        pass

    @abstractmethod
    def get_alerts_version(self) -> FoodRecallAlertsVersion:
        pass