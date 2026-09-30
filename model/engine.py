import pandas as pd
from typing import Dict, Any
from model.detect import score_reading
class DecisionEngine:
    @staticmethod
    def decide(reading: dict, 
               station_history: pd.DataFrame, 
               peer_snapshot: dict, 
               model_artifact: dict, 
               state: Any = None,
               precomputed_features: pd.Series = None,
               precomputed_neighbors: dict = None,
               precomputed_history_featured: pd.DataFrame = None,
               include_evaluation_diagnostics: bool = False) -> dict:
        verdict = score_reading(reading, station_history, model_artifact, peer_snapshot, state, 
                                precomputed_features=precomputed_features, 
                                precomputed_neighbors=precomputed_neighbors,
                                precomputed_history_featured=precomputed_history_featured,
                                include_evaluation_diagnostics=include_evaluation_diagnostics)
        return verdict
