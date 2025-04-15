
import sys
import os

# 필요한 경로 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# app_launcher 모듈에서 main 함수 가져오기 
from app_launcher import main

# 메인 함수 실행
if __name__ == "__main__":
    main()
