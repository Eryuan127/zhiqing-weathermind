"""Start a verified WeatherMind instance without sharing an occupied port."""
import argparse
import os
import socket
from app import create_app
from werkzeug.serving import make_server

def main():
    parser=argparse.ArgumentParser(description='WeatherMind local server')
    parser.add_argument('--port',type=int,default=5001)
    args=parser.parse_args()
    if not 1<=args.port<=65535: parser.error('Invalid port')
    app=create_app()
    if app.test_client().get('/assistant').status_code!=200:
        raise SystemExit('Assistant route check failed. Server not started.')
    # On Windows, Flask may allow two processes to bind the same port.
    # Check with exclusive semantics before creating the development server.
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as probe:
        if os.name=='nt': probe.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
        try: probe.bind(('127.0.0.1',args.port))
        except OSError:
            raise SystemExit(f'Port {args.port} is already occupied. Stop the existing server or use --port with another port.')
    server=make_server('127.0.0.1',args.port,app,threaded=True)
    print(f'WeatherMind: http://127.0.0.1:{args.port}/',flush=True)
    print(f'Assistant: http://127.0.0.1:{args.port}/assistant',flush=True)
    server.serve_forever()

if __name__=='__main__': main()
