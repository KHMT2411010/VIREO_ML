"""Local demo accounts and cookie sessions; all users share the VIREO workspace."""
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime, timezone
import sqlite3, hashlib, hmac, secrets, time, re
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

AUTH_DB=Path(__file__).resolve().parent/'data'/'accounts.sqlite3'
COOKIE='vireo_session'
LIFETIME=8*60*60
router=APIRouter(prefix='/api/auth',tags=['accounts'])

@contextmanager
def connect():
    AUTH_DB.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(AUTH_DB,timeout=30);c.row_factory=sqlite3.Row
    try:
        c.executescript('''CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,name TEXT NOT NULL,email TEXT UNIQUE NOT NULL,role TEXT NOT NULL,salt TEXT NOT NULL,password_hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL,expires REAL NOT NULL);''')
        yield c
        c.commit()
    finally:c.close()

def digest(password,salt):
    return hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),210000).hex()

def safe_user(row):return {k:row[k] for k in ('id','name','email','role')}

def current_user(request):
    token=request.cookies.get(COOKIE)
    if not token:return None
    with connect() as c:
        c.execute('DELETE FROM sessions WHERE expires<?',(time.time(),))
        row=c.execute('SELECT users.* FROM sessions JOIN users ON users.id=sessions.user_id WHERE token_hash=? AND expires>?',(hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
        return safe_user(row) if row else None

def revoke(request,c):
    token=request.cookies.get(COOKIE)
    if token:c.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(token.encode()).hexdigest(),))

def start_session(request,response,user):
    token=secrets.token_urlsafe(32)
    with connect() as c:
        revoke(request,c)
        c.execute('INSERT INTO sessions VALUES (?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),user['id'],time.time()+LIFETIME))
    response.set_cookie(COOKIE,token,httponly=True,samesite='strict',secure=request.url.scheme=='https',max_age=LIFETIME,path='/')
    return {'user':user}

class Register(BaseModel):
    name:str=Field(min_length=2,max_length=70)
    email:str=Field(min_length=3,max_length=120)
    password:str=Field(min_length=8,max_length=128)
    role:str='staff'
class Login(BaseModel):
    email:str=Field(max_length=120)
    password:str=Field(max_length=128)

def normalized_email(email):
    value=email.strip().lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',value):raise HTTPException(422,'Email không hợp lệ.')
    return value

@router.post('/register',status_code=201)
def register(payload:Register):
    email=normalized_email(payload.email);name=payload.name.strip()
    if len(name)<2:raise HTTPException(422,'Vui lòng nhập họ tên hợp lệ.')
    if payload.role not in ('staff','manager'):raise HTTPException(422,'Vai trò không hợp lệ.')
    if email=='nhanvien@vireo.demo':raise HTTPException(409,'Email này dành cho tài khoản trải nghiệm demo.')
    salt=secrets.token_hex(16);user={'id':secrets.token_hex(12),'name':name,'email':email,'role':payload.role}
    try:
        with connect() as c:c.execute('INSERT INTO users VALUES (?,?,?,?,?,?)',(user['id'],name,email,payload.role,salt,digest(payload.password,salt)))
    except sqlite3.IntegrityError:raise HTTPException(409,'Email này đã được đăng ký.')
    return {'user':user,'message':'Tạo tài khoản thành công. Vui lòng đăng nhập.'}

@router.post('/login')
def login(payload:Login,request:Request,response:Response):
    email=normalized_email(payload.email)
    with connect() as c:row=c.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
    if not row or not hmac.compare_digest(digest(payload.password,row['salt']),row['password_hash']):
        raise HTTPException(401,'Email hoặc mật khẩu không chính xác.')
    return start_session(request,response,safe_user(row))

@router.post('/demo')
def demo(request:Request,response:Response):
    with connect() as c:
        row=c.execute('SELECT * FROM users WHERE id=?',('_demo_staff',)).fetchone()
        if not row:
            salt=secrets.token_hex(16)
            c.execute('INSERT INTO users VALUES (?,?,?,?,?,?)',('_demo_staff','Nhân viên','nhanvien@vireo.demo','staff',salt,digest(secrets.token_urlsafe(32),salt)))
            row=c.execute('SELECT * FROM users WHERE id=?',('_demo_staff',)).fetchone()
    return start_session(request,response,safe_user(row))

@router.get('/me')
def me(request:Request):
    user=current_user(request)
    if not user:raise HTTPException(401,'Vui lòng đăng nhập.')
    return {'user':user}

@router.post('/logout')
def logout(request:Request,response:Response):
    with connect() as c:revoke(request,c)
    response.delete_cookie(COOKIE,path='/',samesite='strict',httponly=True)
    return {'logged_out':True}
