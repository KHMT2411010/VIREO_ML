"""VIREO local academic API with cookie sessions and pre-trained IF/ECOD models."""
from pathlib import Path
from io import BytesIO, StringIO
import sqlite3
import os
from contextlib import contextmanager
from threading import RLock
from uuid import uuid4
from fastapi.responses import StreamingResponse
from fastapi import Query
import csv
import json
import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI,UploadFile,File,HTTPException,Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from ml_core import transform_source,parse_transaction_datetime,REQUIRED,validate_calibration,THRESHOLD_METHOD

ROOT=Path(__file__).resolve().parent
WEB=ROOT.parent/'frontend'
MODELS=ROOT/'models'
app=FastAPI(title='VIREO Academic ML API',version='1.0')
# Serve the shared logo before the broader frontend asset mount.
@app.get('/assets/vireo-logo.png',include_in_schema=False)
def vireo_logo():
    return FileResponse(WEB/'assets'/'vireo-logo.png',media_type='image/png')

app.mount('/assets',StaticFiles(directory=WEB),name='assets')
from auth_api import router as auth_router, current_user
from fastapi.responses import JSONResponse
app.include_router(auth_router)

@app.middleware('http')
async def session_guard(request:Request,call_next):
    path=request.url.path
    if request.method in ('POST','PUT','PATCH','DELETE'):
        origin=request.headers.get('origin')
        if origin and origin.rstrip('/')!=str(request.base_url).rstrip('/'):
            return JSONResponse({'detail':'Nguồn gửi yêu cầu không hợp lệ.'},status_code=403)
    public=path.startswith('/api/auth/') or path in ('/api/health','/api/metrics')
    if path.startswith('/api/') and not public:
        user=current_user(request)
        if not user:return JSONResponse({'detail':'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.'},status_code=401)
        request.state.user=user
    return await call_next(request)


class Records(BaseModel):
    records:list[dict]

state={}
ML_LOCK=RLock()
BULK_LOCK=RLock()

def load_models():
    try:
        state['pre']=joblib.load(MODELS/'preprocessor.joblib')
        state['if']=joblib.load(MODELS/'isolation_forest.joblib')
        state['ecod']=joblib.load(MODELS/'ecod_pyod.joblib')
        state['meta']=json.loads((MODELS/'metrics.json').read_text(encoding='utf-8'))
        from pyod.models.ecod import ECOD
        from sklearn.ensemble import IsolationForest
        if not isinstance(state['ecod'],ECOD) or not isinstance(state['if'],IsolationForest):
            raise RuntimeError('Mô hình không đúng loại sklearn IsolationForest + PyOD ECOD')
        validate_calibration(state['meta'])
    except Exception as exc:
        raise RuntimeError('Không tải được mô hình PyOD chính thức. Chạy backend/train.py trước. '+str(exc)) from exc

@app.on_event('startup')
async def startup():load_models()

@app.get('/')
def home():return FileResponse(WEB/'index.html',headers={'Cache-Control':'no-store, max-age=0'})

@app.get('/sample.csv')
def sample_csv():return FileResponse(ROOT.parent/'sample'/'Bank_Transaction_2000_Goc.csv', filename='Bank_Transaction_2000_Goc.csv',media_type='text/csv')

@app.get('/api/health')
def health():return {'status':'ok','model_type':state['meta']['method_ecod'],'trained_rows':state['meta']['trained_rows'],'pipeline_id':state['meta']['pipeline_id']}

@app.get('/api/metrics')
def metrics():return state['meta']

def make_result(df, max_rows=2000):
    if len(df)==0 or len(df)>max_rows:raise HTTPException(422,f'Chỉ nhận 1–{max_rows:,} giao dịch/lần')
    try:
        X=transform_source(df)
        z=state['pre'].transform(X).astype('float32')
        with ML_LOCK:
            a=-state['if'].score_samples(z)
            b=state['ecod'].decision_function(z)
    except (ValueError,KeyError,TypeError) as e:raise HTTPException(422,str(e)) from e
    t1=state['meta']['models']['if']['threshold'];t2=state['meta']['models']['ecod']['threshold']
    parsed_dates, parsed_times = parse_transaction_datetime(df)
    result=[]
    for k,(i,j) in enumerate(zip(a,b)):
        ia=bool(i>=t1);ea=bool(j>=t2)
        row=df.iloc[k]
        dt=parsed_dates.iloc[k].strftime('%Y-%m-%d')+'T'+parsed_times.iloc[k].strftime('%H:%M')
        result.append({'id':str(row.get('Transaction_ID',f'ROW-{k+1}')),'customer':str(row.get('Customer_Name',row.get('Customer_ID', 'Khách hàng'))),'amount':float(row['Transaction_Amount']),'balance':float(row['Account_Balance']),'datetime':dt,'type':str(row['Transaction_Type']),'location':str(row['Transaction_Location']),'device':str(row['Transaction_Device']),'currency':str(row['Transaction_Currency']),'ifScore':round(float(i),6),'ecodScore':round(float(j),6),'ifAlert':ia,'ecodAlert':ea,'level':'high' if ia and ea else 'medium' if ia or ea else 'normal'})
    counts={level:sum(r['level']==level for r in result) for level in ('normal','medium','high')}
    return {'results':result,'counts':counts,
            'thresholds':{'if':t1,'ecod':t2},
            'threshold_selection':{'method':THRESHOLD_METHOD,
                                  'validation_f1':{name:state['meta']['models'][name]['val_f1']
                                                   for name in ('if','ecod')}},
            'method':state['meta']['method_ecod'],'currency':'INR'}

@app.post('/api/predict')
def predict(payload:Records):
    if not 1<=len(payload.records)<=2000:raise HTTPException(422,'Chỉ nhận 1–2.000 giao dịch/lần')
    return make_result(pd.DataFrame(payload.records))

@app.post('/api/predict-csv')
async def predict_csv(file:UploadFile=File(...)):
    if not file.filename.lower().endswith('.csv'):raise HTTPException(422,'Chỉ chấp nhận CSV')
    raw=await file.read(3*1024*1024+1)
    if len(raw)>3*1024*1024:raise HTTPException(413,'Tệp vượt 3 MB')
    # Excel exports on Windows may use CP1252 or CP1258 instead of UTF-8.
    # Always prefer strict UTF-8 decoding; do not silently replace damaged bytes.
    df = None
    encoding_used = None
    decode_errors = []
    for encoding in ('utf-8-sig', 'cp1252', 'cp1258'):
        try:
            decoded = raw.decode(encoding, errors='strict')
        except UnicodeDecodeError as exc:
            decode_errors.append(f'{encoding}: {exc}')
            continue
        try:
            candidate = pd.read_csv(BytesIO(decoded.encode('utf-8')), low_memory=False)
        except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeError, ValueError) as exc:
            raise HTTPException(422, f'CSV không đọc được (đã giải mã bằng {encoding}): {exc}') from exc
        df, encoding_used = candidate, encoding
        break
    if df is None:
        raise HTTPException(422, 'Không xác định được bảng mã CSV. Hãy lưu lại tệp dưới dạng CSV UTF-8 trong Excel.')
    outcome=make_result(df)
    outcome['eda']={'encoding':encoding_used,'rows':int(len(df)),'columns':int(len(df.columns)),'missing_cells':int(df.isna().sum().sum()),'duplicate_rows':int(df.duplicated().sum()),'label_distribution':({str(k):int(v) for k,v in df['Is_Fraud'].value_counts(dropna=False).items()} if 'Is_Fraud' in df else None)}
    return outcome


# Large CSV analysis: local single-user demo database, never a production multi-tenant service.
# This DOES NOT refit the models or recalculate their Validation F1 thresholds.
BULK_DB = ROOT / 'vireo_bulk_results.sqlite3'
BULK_LIMIT = 200000
BULK_BYTES = 110 * 1024 * 1024

@contextmanager
def _bulk_conn():
    with BULK_LOCK:
        conn=sqlite3.connect(BULK_DB, timeout=30)
        conn.row_factory=sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

def _bulk_setup(conn):
    conn.executescript('''CREATE TABLE transactions (
      seq INTEGER PRIMARY KEY, id TEXT, customer TEXT, amount REAL, balance REAL,
      datetime TEXT, type TEXT, location TEXT, device TEXT, currency TEXT,
      ifScore REAL, ecodScore REAL, ifAlert INTEGER, ecodAlert INTEGER,
      level TEXT, review TEXT
    );
    CREATE INDEX idx_level ON transactions(level);
    CREATE INDEX idx_type ON transactions(type);
    CREATE INDEX idx_id ON transactions(id);
    ''')
    conn.execute('CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT)')

def _bulk_where(search='',status='all',kind='all', pending=False, model='all'):
    clauses=[]; values=[]
    if search:
        clauses.append('(id LIKE ? OR customer LIKE ?)')
        escaped=search.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
        clauses[-1]=clauses[-1].replace('LIKE ?', "LIKE ? ESCAPE '\\'")
        values.extend(['%'+escaped+'%']*2)
    if status=='alert': clauses.append("level != 'normal' AND review IS NULL")
    elif status=='normal': clauses.append("level = 'normal' AND review IS NULL")
    elif status in ('high','medium'): clauses.append('level = ?');values.append(status)
    elif status=='reviewed':clauses.append('review IS NOT NULL')
    elif status in ('verified','fraud'):
        clauses.append("json_extract(review,'$.decision') = ?");values.append(status)
    if kind!='all':
        mapped={'transfer':'Transfer','payment':'Bill Payment','withdraw':'Withdrawal','deposit':'__no_deposit_in_dataset__'}.get(kind,kind)
        clauses.append('type = ?');values.append(mapped)
    if model == 'if':
        clauses.append('ifAlert = 1')
    elif model == 'ecod':
        clauses.append('ecodAlert = 1')
    elif model == 'if_safe':
        clauses.append('ifAlert = 0')
    elif model == 'ecod_safe':
        clauses.append('ecodAlert = 0')
    if pending:clauses.append("level != 'normal' AND review IS NULL")
    return (' WHERE '+' AND '.join('('+x+')' for x in clauses)) if clauses else '',values

def _bulk_row(row):
    item=dict(row)
    item['ifAlert']=bool(item['ifAlert']);item['ecodAlert']=bool(item['ecodAlert'])
    item['review']=json.loads(item['review']) if item['review'] else None
    item['_seq']=item.pop('seq')
    return item

def _bulk_summary(conn):
    raw=conn.execute(
        'SELECT level, COUNT(*) AS n, SUM(ifAlert) AS if_count, '
        'SUM(ecodAlert) AS ecod_count FROM transactions GROUP BY level'
    ).fetchall()
    levels={'normal':0,'medium':0,'high':0}
    for r in raw:levels[r['level']]=r['n']
    pending_types={r['level']:r['n'] for r in conn.execute("SELECT level,COUNT(*) AS n FROM transactions WHERE review IS NULL GROUP BY level")}
    reviewed=conn.execute("SELECT COUNT(*) FROM transactions WHERE review IS NOT NULL").fetchone()[0]
    verified=conn.execute("SELECT COUNT(*) FROM transactions WHERE json_extract(review,'$.decision')='verified'").fetchone()[0]
    fraud=conn.execute("SELECT COUNT(*) FROM transactions WHERE json_extract(review,'$.decision')='fraud'").fetchone()[0]
    return {'total':sum(levels.values()),'normal':levels['normal'],'medium':levels['medium'],
            'high':levels['high'],'if_alert':sum(r['if_count'] for r in raw),
            'ecod_alert':sum(r['ecod_count'] for r in raw),'reviewed':reviewed,'verified':verified,'fraud':fraud,
            'pending':pending_types.get('medium',0)+pending_types.get('high',0),
            'pending_high':pending_types.get('high',0),'pending_medium':pending_types.get('medium',0)}

def _bulk_trend(conn):
    count=conn.execute('SELECT COUNT(*) FROM transactions').fetchone()[0]
    if not count:return [{'day':i+1,'normal':0,'alert':0} for i in range(6)]
    # Six equally sized contiguous row-order groups in the uploaded file, NOT calendar dates.
    groups=[{'day':i+1,'normal':0,'alert':0} for i in range(6)]
    for r in conn.execute('SELECT seq,level FROM transactions'):
        i=min(5,(r['seq']-1)*6//count)
        groups[i]['normal' if r['level']=='normal' else 'alert']+=1
    return groups

@app.post('/api/bulk/import')
async def bulk_import(file:UploadFile=File(...)):
    if not (file.filename or '').lower().endswith('.csv'):
        raise HTTPException(422,'Chỉ hỗ trợ file .csv')
    raw=await file.read(BULK_BYTES+1)
    if len(raw)>BULK_BYTES:raise HTTPException(413,'CSV vượt giới hạn 110 MB')
    decoded=None; encoding_used=None
    for enc in ('utf-8-sig','cp1252','cp1258'):
        try:decoded=raw.decode(enc,'strict');encoding_used=enc;break
        except UnicodeDecodeError:pass
    if decoded is None:raise HTTPException(422,'Không xác định được bảng mã CSV')
    tmp=BULK_DB.with_name(f'{BULK_DB.stem}.{uuid4().hex}.pending.sqlite3')
    conn=sqlite3.connect(tmp,timeout=30)
    conn.row_factory=sqlite3.Row
    row_count=0; columns=0; missing=0; labels={}; sampled=[]
    try:
        _bulk_setup(conn)
        try:
            frame=pd.read_csv(StringIO(decoded),low_memory=False)
            if len(frame)==0 or len(frame)>BULK_LIMIT:
                raise HTTPException(422,'CSV cần có từ 1 đến 200.000 giao dịch')
            # Score ECOD once for the full uploaded file, as in the notebook.
            scored_rows=make_result(frame,max_rows=BULK_LIMIT)['results']
            for start in range(0,len(frame),1000):
                chunk=frame.iloc[start:start+1000]
                if row_count+len(chunk)>BULK_LIMIT:
                    raise HTTPException(422,'Tệp có hơn 200.000 giao dịch')
                if row_count==0:columns=len(chunk.columns)
                missing+=int(chunk.isna().sum().sum())
                if 'Is_Fraud' in chunk:
                    for k,v in chunk['Is_Fraud'].value_counts(dropna=False).items():
                        label=str(k);labels[label]=labels.get(label,0)+int(v)
                rows=scored_rows[start:start+len(chunk)]
                batch=[]
                for i,r in enumerate(rows):
                    batch.append((row_count+i+1, r['id'],r['customer'],r['amount'],r['balance'],r['datetime'],r['type'],r['location'],r['device'],r['currency'],r['ifScore'],r['ecodScore'],int(r['ifAlert']),int(r['ecodAlert']),r['level'],None))
                conn.executemany('INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',batch)
                if len(sampled)<50:sampled.extend(rows[:50-len(sampled)])
                row_count+=len(chunk)
            if not row_count:raise HTTPException(422,'CSV không có giao dịch')
        except (pd.errors.ParserError,pd.errors.EmptyDataError,UnicodeError,ValueError,KeyError,TypeError) as exc:
            raise HTTPException(422,'Không đọc hoặc dự đoán được CSV: '+str(exc)) from exc
        eda={'encoding':encoding_used,'rows':row_count,'columns':columns,'missing_cells':missing,
             'label_distribution':labels or None,'duplicate_rows':None}
        conn.execute('INSERT INTO metadata VALUES (?,?)',('eda',json.dumps(eda,ensure_ascii=False)))
        conn.execute('INSERT INTO metadata VALUES (?,?)',('filename',file.filename))
        conn.commit()
        totals=_bulk_summary(conn)
        trend=_bulk_trend(conn)
    except Exception:
        conn.close()
        if tmp.exists():tmp.unlink()
        raise
    conn.close()
    try:
        with BULK_LOCK:
            # Preserve existing transactions and reviews, including manually entered rows.
            if BULK_DB.exists():
                merged=sqlite3.connect(tmp)
                try:
                    merged.execute('ATTACH DATABASE ? AS previous',(str(BULK_DB),))
                    offset=merged.execute('SELECT COALESCE(MAX(seq),0) FROM previous.transactions').fetchone()[0]
                    merged.execute('DELETE FROM transactions WHERE id IN (SELECT id FROM previous.transactions)')
                    merged.execute('UPDATE transactions SET seq=-seq')
                    merged.execute('UPDATE transactions SET seq=-seq+?',(offset,))
                    merged.execute('INSERT INTO transactions SELECT * FROM previous.transactions')
                    merged.commit()
                    merged.row_factory=sqlite3.Row
                    totals=_bulk_summary(merged);trend=_bulk_trend(merged)
                    sampled=[_bulk_row(r) for r in merged.execute('SELECT * FROM transactions ORDER BY seq LIMIT 50')]
                finally:
                    merged.close()
            os.replace(tmp,BULK_DB)
    finally:
        if tmp.exists():tmp.unlink()
    return {'total':row_count,'counts':totals,'trend':trend,'results':sampled,'eda':eda,'thresholds':{
        'if':state['meta']['models']['if']['threshold'],
        'ecod':state['meta']['models']['ecod']['threshold']},
        'validation_rows':state['meta']['validation_rows'],
        'threshold_source':THRESHOLD_METHOD}

@app.get('/api/bulk/status')
def bulk_status():
    if not BULK_DB.exists():return {'active':False}
    with _bulk_conn() as conn:
        meta={r['key']:r['value'] for r in conn.execute('SELECT key,value FROM metadata')}
        return {'active':True,'counts':_bulk_summary(conn),'trend':_bulk_trend(conn),'eda':json.loads(meta.get('eda','{}')),
                'filename':meta.get('filename','')}

@app.get('/api/bulk/transactions')
def bulk_transactions(page:int=Query(1,ge=1),size:int=Query(50,ge=1,le=100),search:str='',status:str='all',kind:str='all',pending:bool=False,model:str='all'):
    if not BULK_DB.exists():return {'total':0,'page':page,'size':size,'results':[]}
    where,vals=_bulk_where(search,status,kind,pending,model)
    with _bulk_conn() as conn:
        total=conn.execute('SELECT COUNT(*) FROM transactions'+where,vals).fetchone()[0]
        order=' ORDER BY CASE WHEN level="high" THEN 0 ELSE 1 END, seq' if pending else ' ORDER BY seq'
        records=conn.execute('SELECT * FROM transactions'+where+order+' LIMIT ? OFFSET ?',vals+[size,(page-1)*size]).fetchall()
        return {'total':total,'page':page,'size':size,'results':[_bulk_row(r) for r in records]}

class BulkReview(BaseModel):
    decision:str
    by:str
    role:str='Nhân viên'
    note:str

@app.post('/api/bulk/review/{seq_id}')
def bulk_review(seq_id:int,payload:BulkReview):
    if not BULK_DB.exists():raise HTTPException(404,'Không có dữ liệu')
    if payload.decision not in ('verified','fraud') or len(payload.note.strip())<8:raise HTTPException(422,'Kết luận hoặc ghi chú không hợp lệ')
    from datetime import datetime, timezone
    with _bulk_conn() as conn:
        r=conn.execute('SELECT * FROM transactions WHERE seq=?',(seq_id,)).fetchone()
        if not r:raise HTTPException(404,'Không tìm thấy giao dịch')
        if r['review']:raise HTTPException(409,'Giao dịch đã xác minh')
        result={'id':r['id'],'customer':r['customer'],'decision':payload.decision,'by':payload.by,
                'role':payload.role,'note':payload.note.strip(),'at':datetime.now(timezone.utc).isoformat()}
        conn.execute('UPDATE transactions SET review=? WHERE seq=?',(json.dumps(result,ensure_ascii=False),seq_id))
        conn.commit()
        return result

@app.delete('/api/bulk/clear')
def bulk_clear():
    with BULK_LOCK:
        BULK_DB.unlink(missing_ok=True)
    return {'cleared':True}

@app.get('/api/bulk/export')
def bulk_export():
    if not BULK_DB.exists():raise HTTPException(404,'Không có dữ liệu')
    def stream():
        cols=['id','customer','amount','balance','datetime','type','location','device','ifScore','ecodScore','level','review']
        output=StringIO();writer=csv.writer(output)
        writer.writerow(cols);yield '\ufeff'+output.getvalue();output.seek(0);output.truncate(0)
        with _bulk_conn() as conn:
            for row in conn.execute('SELECT '+','.join(cols)+' FROM transactions ORDER BY seq'):
                writer.writerow([row[x] for x in cols]);yield output.getvalue();output.seek(0);output.truncate(0)
    return StreamingResponse(stream(),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="vireo_200000_results.csv"'})

@app.post('/api/bulk/manual')
def append_manual(payload:Records):
    if len(payload.records)!=1:
        raise HTTPException(422,'Chỉ nhập một giao dịch thủ công mỗi lần')
    record=payload.records[0]
    validate_manual(record)
    result=make_result(pd.DataFrame(payload.records))
    r=result['results'][0]
    with _bulk_conn() as conn:
        _bulk_setup(conn) if not conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='transactions'").fetchone() else None
        if conn.execute('SELECT 1 FROM transactions WHERE id=?',(r['id'],)).fetchone():
            raise HTTPException(409,'Mã giao dịch đã tồn tại. Hãy nhập mã khác.')
        seq=conn.execute('SELECT COALESCE(MAX(seq),0)+1 FROM transactions').fetchone()[0]
        conn.execute('INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (seq,r['id'],r['customer'],r['amount'],r['balance'],r['datetime'],r['type'],r['location'],r['device'],r['currency'],r['ifScore'],r['ecodScore'],int(r['ifAlert']),int(r['ecodAlert']),r['level'],None))
        conn.commit()
        result['results'][0]['_seq']=seq
    return result


def validate_manual(record):
    import re
    from datetime import datetime, timezone, timedelta
    options=json.loads((ROOT/'manual_options.json').read_text(encoding='utf-8'))
    for column, values in options.items():
        if record.get(column) not in values:
            raise HTTPException(422,f'{column}: phải chọn một mục trong danh sách cho phép.')
    age=str(record.get('Age',''))
    if not re.fullmatch(r'[0-9]+',age) or not 0<=int(age)<150:
        raise HTTPException(422,'Tuổi phải là số nguyên từ 0 đến 149, không có dấu chấm hoặc phẩy.')
    try:
        amount=float(record.get('Transaction_Amount'))
        if not np.isfinite(amount) or amount<0:raise ValueError()
    except (TypeError,ValueError):
        raise HTTPException(422,'Số tiền phải là số không âm.')
    try:
        day,hour=parse_transaction_datetime(pd.DataFrame([record]))
        entered=day.iloc[0].to_pydatetime().replace(hour=hour.iloc[0].hour,minute=hour.iloc[0].minute,second=hour.iloc[0].second)
    except (ValueError,KeyError,TypeError) as exc:
        raise HTTPException(422,str(exc))
    if not 2020<=entered.year<=2026:
        raise HTTPException(422,'Năm giao dịch thủ công phải từ 2020 đến 2026.')
    now=datetime.now(timezone(timedelta(hours=7))).replace(tzinfo=None)
    if entered>now:
        raise HTTPException(422,'Ngày giờ giao dịch không được vượt quá hiện tại (giờ Việt Nam).')
