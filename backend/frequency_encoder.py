import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin

class FrequencyEncoder(BaseEstimator, TransformerMixin):
    """Mỗi cột phân loại -> 1 cột tần suất, fit CHỈ trên Train; unknown -> 0."""
    def fit(self, X, y=None):
        a = np.asarray(X, dtype=object)
        if a.ndim != 2:
            raise ValueError("X phải có 2 chiều")
        self.n_features_in_ = a.shape[1]
        self.freq_maps_ = [pd.Series(a[:, j], dtype="object").astype(str)
                           .value_counts(normalize=True).to_dict()
                           for j in range(a.shape[1])]
        return self

    def transform(self, X):
        if not hasattr(self, "freq_maps_"):
            raise ValueError("FrequencyEncoder chưa fit trên Train")
        a = np.asarray(X, dtype=object)
        if a.ndim != 2 or a.shape[1] != self.n_features_in_:
            raise ValueError("Số cột phân loại không khớp khi transform")
        return np.column_stack([
            pd.Series(a[:, j], dtype="object").astype(str).map(self.freq_maps_[j])
              .fillna(0.0).to_numpy(dtype=np.float32)
            for j in range(self.n_features_in_)
        ]).astype(np.float32)

    def get_feature_names_out(self, input_features=None):
        if input_features is None:
            input_features = [f"x{j}" for j in range(self.n_features_in_)]
        return np.asarray(input_features, dtype=object)
