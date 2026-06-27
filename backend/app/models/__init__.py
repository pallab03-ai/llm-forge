"""ORM models package.

All domain models are imported here so Alembic's autogenerate can discover
them via `Base.metadata`. Importing them at module load time ensures the
metadata is fully populated before migrations run.
"""

from app.models.dataset import Dataset, DatasetVersion  # noqa: F401
from app.models.deployment import Deployment  # noqa: F401
from app.models.evaluation import Evaluation  # noqa: F401
from app.models.model import Model, ModelVersion  # noqa: F401
from app.models.training_job import TrainingJob  # noqa: F401
from app.models.user import User  # noqa: F401

__all__ = [
    "Dataset",
    "DatasetVersion",
    "Deployment",
    "Evaluation",
    "Model",
    "ModelVersion",
    "TrainingJob",
    "User",
]
