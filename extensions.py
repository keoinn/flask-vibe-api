"""Flask 擴充套件集中宣告。

避免 app 與 models 之間的循環匯入（Circular Import）。
"""

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

