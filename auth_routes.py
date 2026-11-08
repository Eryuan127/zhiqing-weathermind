import secrets,re,sqlite3,io,hashlib
from PIL import Image,UnidentifiedImageError
from flask import Blueprint,request,jsonify,session,Response
from werkzeug.security import generate_password_hash,check_password_hash
from services.agent_store import connect

auth_api=Blueprint('auth_api',__name__)
def schema(db):
    db.execute('CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, nickname TEXT NOT NULL, password TEXT NOT NULL)')
    columns={r[1] for r in db.execute('PRAGMA table_info(users)')}
    for name,kind in [('login_name','TEXT'),('avatar','BLOB')]:
        if name not in columns:db.execute(f'ALTER TABLE users ADD COLUMN {name} {kind}')
    db.execute('CREATE UNIQUE INDEX IF NOT EXISTS users_login_name ON users(login_name COLLATE NOCASE)')

def valid_name(value):
    return isinstance(value,str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{2,31}',value.strip())

def occupied(db,name,uid=''):
    return db.execute('SELECT 1 FROM users WHERE (lower(id)=lower(?) OR lower(login_name)=lower(?)) AND id<>?',(name,name,uid)).fetchone()

def user():
    uid=session.get('user_id')
    if not uid:return None
    with connect() as db:
        schema(db)
        row=db.execute('SELECT id,nickname,login_name,avatar FROM users WHERE id=?',(uid,)).fetchone()
    if not row:return None
    return dict(account=row[0],nickname=row[1],login_account=row[2] or row[0],legacy_account=row[2] is None,avatar_url='/api/auth/avatar/'+row[0]+'?v='+hashlib.sha256(row[3]).hexdigest()[:12] if row[3] else None)

@auth_api.get('/api/auth/me')
def me():return jsonify(user=user())

@auth_api.post('/api/auth/register')
def register():
    body=request.get_json(silent=True) or {};nickname=body.get('nickname','');password=body.get('password','')
    if not isinstance(nickname,str) or not 1<=len(nickname.strip())<=24:return jsonify(error='昵称需为1至24字'),400
    if not isinstance(password,str) or not 8<=len(password)<=128:return jsonify(error='密码需为8至128位'),400
    account=secrets.choice(['Sunny','Cloud','Breeze','Sky'])+str(secrets.randbelow(90000000)+10000000)
    login_name=body.get('account')
    if login_name is not None and not valid_name(login_name):return jsonify(error='登录账号需为3至32位，以英文字母开头，只含字母、数字或下划线'),400
    login_name=login_name.strip() if login_name is not None else None
    hashed=generate_password_hash(password)
    with connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, nickname TEXT NOT NULL, password TEXT NOT NULL)')
        schema(db)
        if login_name and occupied(db,login_name):return jsonify(error='该登录账号已被使用，请换一个'),409
        try:db.execute('INSERT INTO users (id,nickname,password,login_name) VALUES (?,?,?,?)',(account,nickname.strip(),hashed,login_name))
        except sqlite3.IntegrityError:return jsonify(error='该登录账号已被使用，请换一个'),409
    session.clear();session['user_id']=account
    return jsonify(user=user()),201

@auth_api.post('/api/auth/login')
def login():
    body=request.get_json(silent=True) or {};account=body.get('account','');password=body.get('password','')
    if not isinstance(account,str) or not isinstance(password,str) or len(account)>64 or len(password)>128:return jsonify(error='账号或密码错误'),401
    with connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, nickname TEXT NOT NULL, password TEXT NOT NULL)')
        schema(db)
        row=db.execute('SELECT password,id FROM users WHERE lower(id)=lower(?) OR lower(login_name)=lower(?)',(account.strip(),account.strip())).fetchone()
    valid=check_password_hash(row[0] if row else generate_password_hash('invalid-password'),password)
    if not row or not valid:return jsonify(error='账号或密码错误'),401
    session.clear();session['user_id']=row[1]
    return jsonify(user=user())

@auth_api.post('/api/auth/logout')
def logout():session.clear();return jsonify(user=None)

@auth_api.patch('/api/auth/profile')
def update_profile():
    current=user()
    if not current:return jsonify(error='请先登录'),401
    body=request.get_json(silent=True) or {}
    nickname=body.get('nickname',current['nickname']);name=body.get('account',current['login_account'])
    if not isinstance(nickname,str) or not 1<=len(nickname.strip())<=24:return jsonify(error='昵称需为1至24字'),400
    if not valid_name(name):return jsonify(error='登录账号需为3至32位，以英文字母开头，只含字母、数字或下划线'),400
    with connect() as db:
        schema(db)
        if occupied(db,name.strip(),current['account']):return jsonify(error='该登录账号已被使用，请换一个'),409
        try:db.execute('UPDATE users SET nickname=?,login_name=? WHERE id=?',(nickname.strip(),name.strip(),current['account']))
        except sqlite3.IntegrityError:return jsonify(error='该登录账号已被使用，请换一个'),409
    return jsonify(user=user())

@auth_api.post('/api/auth/avatar')
def upload_avatar():
    current=user()
    if not current:return jsonify(error='请先登录'),401
    upload=request.files.get('avatar')
    if not upload:return jsonify(error='请选择图片'),400
    raw=upload.read(1024*1024+1)
    if len(raw)>1024*1024:return jsonify(error='图片不能超过1MB'),413
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in ('PNG','JPEG','WEBP') or image.width*image.height>16000000:raise ValueError()
            image.load();image=image.convert('RGB');side=min(image.size);left=(image.width-side)//2;top=(image.height-side)//2
            image=image.crop((left,top,left+side,top+side));image.thumbnail((128,128))
            output=io.BytesIO();image.save(output,format='PNG')
    except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError):return jsonify(error='请上传有效的 PNG、JPG 或 WebP 图片'),400
    with connect() as db:db.execute('UPDATE users SET avatar=? WHERE id=?',(output.getvalue(),current['account']))
    return jsonify(user=user())

@auth_api.get('/api/auth/avatar/<uid>')
def avatar(uid):
    if session.get('user_id')!=uid:return jsonify(error='无法访问该头像'),404
    with connect() as db:
        schema(db);row=db.execute('SELECT avatar FROM users WHERE id=?',(uid,)).fetchone()
    if not row or not row[0]:return '',404
    return Response(row[0],mimetype='image/png',headers={'X-Content-Type-Options':'nosniff'})

@auth_api.delete('/api/auth/avatar')
def remove_avatar():
    current=user()
    if not current:return jsonify(error='请先登录'),401
    with connect() as db:db.execute('UPDATE users SET avatar=NULL WHERE id=?',(current['account'],))
    return jsonify(user=user())
