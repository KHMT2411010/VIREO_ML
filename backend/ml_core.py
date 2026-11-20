"""VIREO ML core: feature construction and threshold selection.

The two models are sklearn.ensemble.IsolationForest and pyod.models.ecod.ECOD.
"""
import numpy as np
import pandas as pd

PIPELINE_ID = 'frequency_13_max_f1_validation_v1'
THRESHOLD_METHOD = 'max_f1_validation'


def validate_calibration(meta):
    if (meta.get('pipeline_id') != PIPELINE_ID
            or meta.get('threshold_method') != THRESHOLD_METHOD
            or meta.get('method_ecod') != 'PyOD ECOD (official)'
            or meta.get('trained_rows') != 200000
            or meta.get('features') != 13
            or meta.get('encoding') != 'Frequency Encoding'):
        raise ValueError('Cần huấn luyện bộ 200.000 dòng bằng pipeline F1 Validation hiện tại.')
    for name in ('if', 'ecod'):
        model = meta['models'][name]
        if not np.isfinite(float(model['threshold'])) or not 0 <= float(model['val_f1']) <= 1:
            raise ValueError('Ngưỡng hoặc F1 Validation không hợp lệ: ' + name)


NUM = ['Transaction_Amount','Account_Balance','Age','Transaction_Hour','Transaction_Day','Transaction_Month']
CAT = ['Transaction_Type','Merchant_Category','Transaction_Device','Transaction_Location','Device_Type','Account_Type','Transaction_Currency']
FEATURES = NUM + CAT
REQUIRED = ['Transaction_Amount','Account_Balance','Age','Transaction_Date','Transaction_Time']+CAT

def parse_transaction_datetime(frame:pd.DataFrame):
    """Interpret dates as day/month/year even when Excel switches '-' to '/'.

    The original research dataset is dd-mm-YYYY (e.g. 08-01-2025).
    Excel may export the same value as 8/1/2025; this is **8 January**,
    not 1 August. Accept ISO dates as well, without guessing other formats.
    """
    missing=[c for c in ('Transaction_Date','Transaction_Time') if c not in frame]
    if missing: raise ValueError('Thiếu cột cần thiết: '+', '.join(missing))
    date_raw=frame['Transaction_Date'].astype('string').str.strip()
    time_raw=frame['Transaction_Time'].astype('string').str.strip()

    # Explicit formats prevent Pandas from interpreting d/m/YYYY as m/d/YYYY.
    dmy=date_raw.str.fullmatch(r'\d{1,2}[-/]\d{1,2}[-/]\d{4}',na=False)
    iso=date_raw.str.fullmatch(r'\d{4}-\d{1,2}-\d{1,2}',na=False)
    date_parsed=pd.Series(pd.NaT,index=frame.index,dtype='datetime64[ns]')
    if dmy.any():
        normalized=date_raw.loc[dmy].str.replace('/','-',regex=False)
        date_parsed.loc[dmy]=pd.to_datetime(normalized,format='%d-%m-%Y',errors='coerce')
    if iso.any():
        date_parsed.loc[iso]=pd.to_datetime(date_raw.loc[iso],format='%Y-%m-%d',errors='coerce')

    # Excel may omit leading zeros and seconds (2:55:05 / 2:55).
    hms=time_raw.str.fullmatch(r'\d{1,2}:\d{1,2}:\d{1,2}',na=False)
    hm=time_raw.str.fullmatch(r'\d{1,2}:\d{1,2}',na=False)
    time_parsed=pd.Series(pd.NaT,index=frame.index,dtype='datetime64[ns]')
    if hms.any():
        time_parsed.loc[hms]=pd.to_datetime(time_raw.loc[hms],format='%H:%M:%S',errors='coerce')
    if hm.any():
        time_parsed.loc[hm]=pd.to_datetime(time_raw.loc[hm],format='%H:%M',errors='coerce')

    if date_parsed.isna().any() or time_parsed.isna().any():
        invalid=frame.loc[date_parsed.isna()|time_parsed.isna(), ['Transaction_Date','Transaction_Time']].head(3)
        examples='; '.join(f'dòng {i+2}: {r.Transaction_Date!s} / {r.Transaction_Time!s}' for i,r in invalid.iterrows()) if isinstance(frame.index,pd.RangeIndex) else '; '.join(f'{r.Transaction_Date!s} / {r.Transaction_Time!s}' for _,r in invalid.iterrows())
        raise ValueError('Ngày/giờ không hợp lệ. Hỗ trợ dd-mm-YYYY, d/m/YYYY, YYYY-mm-dd và H:M:S hoặc H:M. Ví dụ lỗi: '+examples)
    return date_parsed,time_parsed


def transform_source(frame:pd.DataFrame):
    missing=[c for c in REQUIRED if c not in frame]
    if missing: raise ValueError('Thiếu cột cần thiết: '+', '.join(missing))
    d=frame.copy()
    dt,tm=parse_transaction_datetime(d)
    d['Transaction_Day']=dt.dt.day.astype(float)
    d['Transaction_Month']=dt.dt.month.astype(float)
    d['Transaction_Hour']=tm.dt.hour.astype(float)
    for col in NUM:
        d[col]=pd.to_numeric(d[col], errors='coerce')
    for col in CAT:
        d[col]=d[col].astype('object').where(d[col].notna(),np.nan)
    return d[FEATURES]

def optimize_threshold(y, scores):
    from sklearn.metrics import precision_recall_curve
    precision,recall,thresholds=precision_recall_curve(y,scores)
    if not len(thresholds): raise ValueError('Không tính được ngưỡng')
    f1=(2*precision[:-1]*recall[:-1])/(precision[:-1]+recall[:-1]+1e-12)
    index=int(np.argmax(f1))
    return float(thresholds[index]),float(f1[index])
