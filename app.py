from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from pathlib import Path
from weather_routes import api
load_dotenv()
def create_app():
    app = Flask(__name__)
    import logging,re
    class LocationLogFilter(logging.Filter):
        def filter(self,record):
            record.msg=re.sub(r'((?:latitude|longitude)=)[^&\s"]+',r'\1[redacted]',record.getMessage())
            record.args=()
            return True
    if not any(type(f).__name__=='LocationLogFilter' for f in logging.getLogger('werkzeug').filters):
        logging.getLogger('werkzeug').addFilter(LocationLogFilter())
    import os, secrets
    configured_secret=os.getenv('FLASK_SECRET_KEY')
    if not configured_secret:
        secret_path=Path(__file__).resolve().parent/'data/.session-secret'
        secret_path.parent.mkdir(exist_ok=True)
        try:
            with secret_path.open('x',encoding='utf-8') as f:f.write(secrets.token_hex(32))
        except FileExistsError:pass
        configured_secret=secret_path.read_text(encoding='utf-8').strip()
    app.secret_key=configured_secret
    app.config.update(MAX_CONTENT_LENGTH=8192, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Strict')
    from agent_routes import agent_api
    app.register_blueprint(agent_api)
    from auth_routes import auth_api,user
    app.register_blueprint(auth_api)
    @app.before_request
    def check_access():
        if request.path=='/api/auth/avatar' and request.method=='POST':request.max_content_length=1024*1024+8192
        if request.method in ('POST','PUT','PATCH','DELETE') and request.headers.get('Origin'):
            if request.headers['Origin'] != request.host_url.rstrip('/'):
                return jsonify(error='请求来源无效'),403
        if request.path.startswith('/api/agent/') and not user():
            return jsonify(error='请先注册或登录后使用助手'),401

    app.json.ensure_ascii = False
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
    @app.context_processor
    def asset_versions():
        def asset_url(filename):
            from flask import url_for
            version = (Path(app.static_folder) / filename).stat().st_mtime_ns
            return url_for("static", filename=filename, v=version)
        return {"asset_url": asset_url}
    @app.after_request
    def prevent_stale_pages(response):
        response.headers["Cache-Control"] = "no-store"
        return response
    app.register_blueprint(api)
    @app.get('/')
    def index():
        return render_template('index.html')
    return app
if __name__ == '__main__':
    create_app().run(host='127.0.0.1', port=5000)
