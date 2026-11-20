# -*- coding: utf-8 -*-
"""Verify official PyOD ECOD and saved 200k-trained model before launching VIREO."""
from pathlib import Path
import json,sys,joblib
from sklearn.ensemble import IsolationForest
from pyod.models.ecod import ECOD
from ml_core import validate_calibration
p=Path(__file__).resolve().parent/'models'
required=['preprocessor.joblib','isolation_forest.joblib','ecod_pyod.joblib','metrics.json']
missing=[name for name in required if not (p/name).is_file()]
if missing:
    print('MISSING:', ', '.join(missing), flush=True)
    sys.exit(2)
try:
    d=json.loads((p/'metrics.json').read_text(encoding='utf-8'))
    validate_calibration(d)
    if not isinstance(joblib.load(p/'isolation_forest.joblib'),IsolationForest):
        raise TypeError('Not a scikit-learn IsolationForest')
    if not isinstance(joblib.load(p/'ecod_pyod.joblib'),ECOD):
        raise TypeError('Not an official PyOD ECOD')
    pre=joblib.load(p/'preprocessor.joblib')
    from frequency_encoder import FrequencyEncoder
    if not isinstance(pre.named_transformers_['cat'].named_steps['frequency'],FrequencyEncoder):
        raise TypeError('Expected Frequency Encoding pipeline')
    import sklearn
    if d.get('sklearn_version') != sklearn.__version__:
        raise ValueError('Model sklearn version differs; retraining required')
    for name in ('if', 'ecod'):
        model = d['models'][name]
        print(f"{name}: threshold={model['threshold']:.8f}; validation F1={model['val_f1']:.4f}")
    print('PASS: 200000-row models with Validation F1 calibration', flush=True)
except Exception as exc:
    print('INVALID MODEL:',exc,flush=True)
    sys.exit(3)
