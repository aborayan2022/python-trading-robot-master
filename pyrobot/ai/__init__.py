"""AI & Machine Learning quantitative intelligence package."""

from pyrobot.ai.calibration import IsotonicCalibrator
from pyrobot.ai.context import (
    LexiconSentimentEngine,
    LLMContextEngine,
    NewsEventType,
    SentimentAnalysis,
)
from pyrobot.ai.drift import DriftDetector, DriftReport
from pyrobot.ai.ensemble import EnsembleSignalEngine
from pyrobot.ai.labels import LabelBuilder
from pyrobot.ai.models import (
    BaseQuantModel,
    GBDTDirectionClassifier,
    LogisticDirectionModel,
    VolatilityForecaster,
    model_class_for_type,
)
from pyrobot.ai.registry import (
    ArtifactIntegrityError,
    ModelMetadata,
    ModelRegistry,
    ModelStatus,
)
from pyrobot.ai.training import (
    TrainingGateConfig,
    accuracy_metric,
    build_training_frame,
    train_direction_champion_candidate,
)

__all__ = [
    "ModelRegistry",
    "ModelMetadata",
    "ModelStatus",
    "ArtifactIntegrityError",
    "BaseQuantModel",
    "LogisticDirectionModel",
    "GBDTDirectionClassifier",
    "VolatilityForecaster",
    "model_class_for_type",
    "EnsembleSignalEngine",
    "DriftDetector",
    "DriftReport",
    "LabelBuilder",
    "IsotonicCalibrator",
    "TrainingGateConfig",
    "accuracy_metric",
    "build_training_frame",
    "train_direction_champion_candidate",
    "LexiconSentimentEngine",
    "LLMContextEngine",
    "SentimentAnalysis",
    "NewsEventType",
]
