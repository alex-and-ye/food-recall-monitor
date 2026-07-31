from db.warnings_interface import PipelineWarningsDBInterface
from models.pipeline_warning import (
    MAX_WARNING_MESSAGE_LENGTH,
    PipelineWarning,
    PipelineWarningCreate,
    PipelineWarningsSummary,
    WarningCategory,
)

class WarningsService:
    def __init__(self, db: PipelineWarningsDBInterface) -> None:
        self.db = db

    def emit(
        self,
        *,
        category: WarningCategory,
        message: str,
        source: str | None = None,
        run_id: str | None = None,
    ) -> PipelineWarning:
        return self.db.create(
            PipelineWarningCreate(
                category=category,
                message=_truncate_message(message),
                source=source,
                run_id=run_id,
            )
        )

    def list_warnings(self, *, acknowledged: bool | None = None) -> list[PipelineWarning]:
        return self.db.list_warnings(acknowledged=acknowledged)

    def get_summary(self) -> PipelineWarningsSummary:
        return PipelineWarningsSummary(unacknowledged_count=self.db.count_unacknowledged())

    def acknowledge(self, warning_id: str) -> PipelineWarning | None:
        return self.db.acknowledge(warning_id)

    def acknowledge_all(self) -> int:
        return self.db.acknowledge_all()

def _truncate_message(message: str) -> str:
    text = " ".join(message.strip().split())
    if not text:
        return "Pipeline warning"
    if len(text) <= MAX_WARNING_MESSAGE_LENGTH:
        return text
    return text[: MAX_WARNING_MESSAGE_LENGTH - 1].rstrip() + "…"
