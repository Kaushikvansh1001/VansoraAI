import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analytics import Dataset, DatasetAnalysis


class AnalystRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_datasets(self, organization_id: uuid.UUID) -> list[Dataset]:
        return list(
            self.db.scalars(
                select(Dataset).where(Dataset.organization_id == organization_id).order_by(Dataset.created_at.desc())
            ).all()
        )

    def get_dataset(self, organization_id: uuid.UUID, dataset_id: uuid.UUID) -> Dataset | None:
        return self.db.scalar(
            select(Dataset).where(Dataset.id == dataset_id, Dataset.organization_id == organization_id)
        )

    def list_analyses(self, organization_id: uuid.UUID, dataset_id: uuid.UUID) -> list[DatasetAnalysis]:
        return list(
            self.db.scalars(
                select(DatasetAnalysis)
                .where(
                    DatasetAnalysis.organization_id == organization_id,
                    DatasetAnalysis.dataset_id == dataset_id,
                )
                .order_by(DatasetAnalysis.created_at.desc())
            ).all()
        )

    def get_analysis(self, organization_id: uuid.UUID, analysis_id: uuid.UUID) -> DatasetAnalysis | None:
        return self.db.scalar(
            select(DatasetAnalysis).where(
                DatasetAnalysis.id == analysis_id,
                DatasetAnalysis.organization_id == organization_id,
            )
        )
