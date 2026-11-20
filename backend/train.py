"""Train on original 24-column CSV; save reproducible pipeline & validation thresholds.
Run: python train.py --csv path/to/Bank_Transaction_Fraud_Detection.csv
"""
import argparse,json
from pathlib import Path
import joblib,numpy as np,pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.impute import SimpleImputer
from frequency_encoder import FrequencyEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.ensemble import IsolationForest
from sklearn.metrics import precision_score,recall_score,f1_score,roc_auc_score,average_precision_score,confusion_matrix
from ml_core import NUM,CAT,FEATURES,PIPELINE_ID,THRESHOLD_METHOD,transform_source,optimize_threshold
from pyod.models.ecod import ECOD
import sklearn, pyod, sys

ROOT=Path(__file__).resolve().parent

def train(csv):
    df=pd.read_csv(csv,low_memory=False)
    if df.shape != (200000,24):
        raise ValueError(f'Bộ dữ liệu không đúng quy mô notebook: {df.shape}, cần (200000, 24)')
    if 'Is_Fraud' not in df or int(pd.to_numeric(df['Is_Fraud'],errors='coerce').eq(1).sum())!=10088:
        raise ValueError('Bộ dữ liệu không đúng 10.088 giao dịch gắn nhãn Is_Fraud=1')
    print('EDA:', {'rows':len(df),'columns':len(df.columns),'missing_cells':int(df.isna().sum().sum()),'duplicate_rows':int(df.duplicated().sum())},flush=True)
    df=df.drop_duplicates().copy()
    if 'Is_Fraud' not in df: raise ValueError('Thiếu nhãn Is_Fraud để chọn ngưỡng')
    y=pd.to_numeric(df['Is_Fraud'],errors='coerce')
    if y.isna().any() or not y.isin([0,1]).all():
        raise ValueError('Is_Fraud phải có nhãn 0/1 hợp lệ ở mọi dòng')
    y=y.astype(int).reset_index(drop=True)
    X=transform_source(df)
    xtrain,xtmp,ytrain,ytmp=train_test_split(X,y,test_size=.30,random_state=42,stratify=y)
    xval,xtest,yval,ytest=train_test_split(xtmp,ytmp,test_size=.5,random_state=42,stratify=ytmp)
    pre=ColumnTransformer([('num',SimpleImputer(strategy='median'),NUM),('cat',Pipeline([('fill',SimpleImputer(strategy='most_frequent')),('frequency',FrequencyEncoder())]),CAT)], remainder='drop', sparse_threshold=0)
    print('Preprocessing...',flush=True)
    ztrain=pre.fit_transform(xtrain).astype('float32');zval=pre.transform(xval).astype('float32');ztest=pre.transform(xtest).astype('float32')
    print('Shapes:',ztrain.shape,zval.shape,ztest.shape,flush=True)
    if not all(np.isfinite(z).all() for z in (ztrain,zval,ztest)):raise RuntimeError('Dữ liệu sau tiền xử lý có NaN hoặc inf')
    if_model=IsolationForest(n_estimators=100,max_samples='auto',contamination=0.05,random_state=42,n_jobs=-1)
    # Use the official ECOD implementation from PyOD, matching the Colab approach.
    ecod_model=ECOD(contamination=0.05,n_jobs=1)
    if_model.fit(ztrain);print('Isolation Forest trained',flush=True)
    ecod_model.fit(ztrain);print('Official PyOD ECOD trained',flush=True)
    result={}
    for name,model in [('if',if_model),('ecod',ecod_model)]:
        val=-model.score_samples(zval) if name=='if' else model.decision_function(zval)
        test=-model.score_samples(ztest) if name=='if' else model.decision_function(ztest)
        threshold,val_f1=optimize_threshold(yval,val)
        pred=(test>=threshold).astype('int8')
        tn,fp,fn,tp=map(int,confusion_matrix(ytest,pred,labels=[0,1]).ravel())
        result[name]={'threshold':threshold,'val_f1':val_f1,'test':{'precision':float(precision_score(ytest,pred,zero_division=0)),'recall':float(recall_score(ytest,pred,zero_division=0)),'f1':float(f1_score(ytest,pred,zero_division=0)),'roc_auc':float(roc_auc_score(ytest,test)),'average_precision':float(average_precision_score(ytest,test)),'tn':tn,'fp':fp,'fn':fn,'tp':tp}}
    out=ROOT/'models';out.mkdir(exist_ok=True)
    joblib.dump(pre,out/'preprocessor.joblib',compress=3)
    joblib.dump(if_model,out/'isolation_forest.joblib',compress=3)
    for attr in ('U_l','U_r','U_skew','O'):
        ecod_model.__dict__.pop(attr, None)
    joblib.dump(ecod_model,out/'ecod_pyod.joblib',compress=3)
    encoder=pre.named_transformers_['cat'].named_steps['frequency']
    cardinalities={c:len(m) for c,m in zip(CAT,encoder.freq_maps_)}
    assert ztrain.shape[1] == zval.shape[1] == ztest.shape[1] == 13
    meta={'pipeline_id':PIPELINE_ID,'threshold_method':THRESHOLD_METHOD,'training_note':'Đồng bộ notebook Do_an_IF_ECOD_13_dac_trung_Frequency_Encoding (1)(1).ipynb','encoding':'Frequency Encoding',
          'raw_columns':int(len(df.columns)),'source_positive_labels':int(y.sum()),'feature_columns':FEATURES,
          'num_features':NUM,'categorical_features':CAT,'category_cardinalities':cardinalities,
          'contamination':0.05,'model_setup':{'if':{'n_estimators':100,'max_samples':'auto','contamination':0.05,'random_state':42},'ecod':{'contamination':0.05,'n_jobs':1}},
          'selection_note':'F1 tối đa trên Validation có nhãn, Test chỉ đánh giá; bất thường không đồng nghĩa gian lận',
          'test_label_prevalence':float(ytest.mean()),
          'trained_rows':int(len(df)),'train_rows':len(xtrain),'validation_rows':len(xval),'test_rows':len(xtest),'features':int(ztrain.shape[1]),'method_ecod':'PyOD ECOD (official)', 'models':result,'currency':'INR','seed':42,'python_version':sys.version.split()[0],'sklearn_version':sklearn.__version__,'pyod_version':__import__('importlib.metadata',fromlist=['version']).version('pyod'), 'if_score_direction':'-score_samples (higher = more abnormal)', 'ecod_score_direction':'decision_function (higher = more abnormal)'}
    (out/'metrics.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Training completed:',json.dumps(meta,ensure_ascii=False,indent=2),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--csv',required=True);args=p.parse_args();train(args.csv)
