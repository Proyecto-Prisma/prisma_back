from flask import Flask

def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_pyfile('config.py')

    with app.app_context():
        from .auth.routes import auth_blueprint
        from .data.routes import data_blueprint

        app.register_blueprint(auth_blueprint, url_prefix='/auth')
        app.register_blueprint(data_blueprint, url_prefix='/data')

        return app