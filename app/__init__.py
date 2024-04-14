from flask import Flask
import logging
from logging.handlers import RotatingFileHandler
import os

def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_pyfile('config.py')

    # Configure logging
    if not app.debug:
        if not os.path.exists('logs'):
            os.mkdir('logs')
        file_handler = RotatingFileHandler('logs/app.log',
                                           maxBytes=10240,
                                           backupCount=10)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s '
            '[in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)

        app.logger.setLevel(logging.INFO)
        app.logger.info('Application startup')

    with app.app_context():
        from .auth.routes import auth_blueprint
        from .data.routes import data_blueprint

        app.register_blueprint(auth_blueprint, url_prefix='/auth')
        app.register_blueprint(data_blueprint, url_prefix='/data')

        return app
