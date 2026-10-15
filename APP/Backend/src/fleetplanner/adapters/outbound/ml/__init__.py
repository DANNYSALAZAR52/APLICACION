"""Adaptadores de ML con scikit-learn detrás de los puertos de la aplicación."""

from fleetplanner.adapters.outbound.ml.anomaly import SklearnAnomalyDetector
from fleetplanner.adapters.outbound.ml.delay import SklearnDelayRiskPredictor
from fleetplanner.adapters.outbound.ml.demand import SklearnDemandForecaster
from fleetplanner.adapters.outbound.ml.segments import SklearnPatternMiner

__all__ = [
    "SklearnAnomalyDetector",
    "SklearnDelayRiskPredictor",
    "SklearnDemandForecaster",
    "SklearnPatternMiner",
]
