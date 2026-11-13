import os
import sys

# 將專案根目錄加入模組搜尋路徑，確保能順利引用 app 與相關模組
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app

