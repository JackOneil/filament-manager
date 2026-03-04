from flask_sqlalchemy import SQLAlchemy

# Shared SQLAlchemy instance — initialized in app.py via db.init_app(app)
db = SQLAlchemy()
