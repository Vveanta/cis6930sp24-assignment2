from flask import Flask
from .server import main as main_blueprint

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'your_secret_key'
    app.register_blueprint(main_blueprint)
    return app
