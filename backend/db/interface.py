from abc import ABC, abstractmethod
from typing import List
from models.recall_alert import FoodRecallAlert

class FoodRecallAlertsDBInterface(ABC):
    @abstractmethod
    def get_alerts(self) -> List[FoodRecallAlert]:
        pass

    @abstractmethod
    def save_alerts(self, alerts: List[FoodRecallAlert]) -> int:
        pass