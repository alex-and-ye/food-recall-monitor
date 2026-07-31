from abc import ABC, abstractmethod

from models.pipeline_warning import PipelineWarning, PipelineWarningCreate

class PipelineWarningsDBInterface(ABC):
    @abstractmethod
    def create(self, warning: PipelineWarningCreate) -> PipelineWarning:
        pass

    @abstractmethod
    def list_warnings(self, *, acknowledged: bool | None = None) -> list[PipelineWarning]:
        pass

    @abstractmethod
    def get_warning(self, warning_id: str) -> PipelineWarning | None:
        pass

    @abstractmethod
    def acknowledge(self, warning_id: str) -> PipelineWarning | None:
        pass

    @abstractmethod
    def acknowledge_all(self) -> int:
        pass

    @abstractmethod
    def count_unacknowledged(self) -> int:
        pass

    @abstractmethod
    def delete(self, warning_id: str) -> bool:
        pass
