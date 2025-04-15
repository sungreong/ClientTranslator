import os
import sys
import subprocess
from pathlib import Path
import shutil
import logging


def setup_logging():
    """빌드 로깅 설정"""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / f"build_{os.path.basename(sys.executable)}_{os.getpid()}.log"

    # 로그 설정
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler(log_file, encoding="utf-8"), logging.StreamHandler()],
    )

    logging.info(f"빌드 로그 파일 생성: {log_file}")
    return log_file


def build_exe():
    """EXE 파일 빌드"""
    log_file = setup_logging()
    logging.info("보이스 프로그램 EXE 빌드를 시작합니다...")

    # 시스템 정보 기록
    logging.info(f"Python 버전: {sys.version}")
    logging.info(f"실행 경로: {sys.executable}")
    logging.info(f"플랫폼: {sys.platform}")
    logging.info(f"인코딩: {sys.getdefaultencoding()}")

    # 현재 디렉토리
    current_dir = Path.cwd()
    logging.info(f"작업 디렉토리: {current_dir}")

    # 아이콘 파일 경로 (아이콘이 있다면)
    icon_path = current_dir / "icon.ico"
    icon_param = []
    if icon_path.exists():
        icon_param = ["--icon", str(icon_path)]

    # 필수 파일 확인 및 추가
    add_data_params = []

    # streamlit_app.py 파일 명시적 추가 (중요)
    main_path = current_dir / "streamlit_app.py"
    if main_path.exists():
        add_data_params.extend(["--add-data", f"{main_path};."])
        logging.info(f"메인 스크립트 추가: {main_path}")
    else:
        logging.error(f"오류: 메인 스크립트를 찾을 수 없습니다: {main_path}")
        print(f"오류: 메인 스크립트를 찾을 수 없습니다: {main_path}")
        return
    # add database.py
    database_path = current_dir / "database.py"
    if database_path.exists():
        add_data_params.extend(["--add-data", f"{database_path};."])
        logging.info(f"데이터베이스 스크립트 추가: {database_path}")
    else:
        logging.error(f"오류: 데이터베이스 스크립트를 찾을 수 없습니다: {database_path}")

    # config.yaml 파일 확인
    config_path = current_dir / "config.yaml"
    if config_path.exists():
        add_data_params.extend(["--add-data", f"{config_path};."])
        logging.info(f"설정 파일 추가: {config_path}")
    else:
        logging.warning(f"경고: 설정 파일을 찾을 수 없습니다: {config_path}")

    # .env 파일 확인
    env_path = current_dir / ".env"
    if env_path.exists():
        add_data_params.extend(["--add-data", f"{env_path};."])
        logging.info(f"환경 변수 파일 추가: {env_path}")
    else:
        logging.warning(f"경고: 환경 변수 파일을 찾을 수 없습니다: {env_path}")

    # database.sqlite 파일 확인
    db_path = current_dir / "database.sqlite"
    if db_path.exists():
        add_data_params.extend(["--add-data", f"{db_path};."])
        logging.info(f"데이터베이스 파일 추가: {db_path}")
    else:
        logging.warning(f"경고: 데이터베이스 파일을 찾을 수 없습니다: {db_path}")
        logging.info("데이터베이스 파일이 없으면 프로그램 실행 시 자동으로 생성됩니다.")

    # audio_files 디렉토리 확인
    audio_dir = current_dir / "audio_files"
    if audio_dir.exists() and audio_dir.is_dir():
        add_data_params.extend(["--add-data", f"{audio_dir};audio_files"])
        logging.info(f"오디오 파일 디렉토리 추가: {audio_dir}")
    else:
        logging.warning(f"경고: 오디오 파일 디렉토리를 찾을 수 없습니다: {audio_dir}")
        logging.info("오디오 파일 디렉토리가 없으면 프로그램 실행 시 자동으로 생성됩니다.")

    # recordings 디렉토리가 있다면 추가
    recordings_dir = current_dir / "recordings"
    if recordings_dir.exists() and recordings_dir.is_dir():
        add_data_params.extend(["--add-data", f"{recordings_dir};recordings"])
        logging.info(f"녹음 파일 디렉토리 추가: {recordings_dir}")

    # conversations 디렉토리가 있다면 추가
    conversations_dir = current_dir / "conversations"
    if conversations_dir.exists() and conversations_dir.is_dir():
        add_data_params.extend(["--add-data", f"{conversations_dir};conversations"])
        logging.info(f"대화 파일 디렉토리 추가: {conversations_dir}")

    # 로그 디렉토리가 있다면 추가
    logs_dir = current_dir / "logs"
    if logs_dir.exists() and logs_dir.is_dir():
        add_data_params.extend(["--add-data", f"{logs_dir};logs"])
        logging.info(f"로그 디렉토리 추가: {logs_dir}")

    # 추가 필요한 모듈 (숨겨진 의존성)
    hidden_imports = [
        "streamlit",
        "streamlit_authenticator",
        "pyaudio",
        "pydub",
        "openai",
        "firebase_admin",
        "ctypes",  # 관리자 권한 확인용
        "ctypes.wintypes",  # Windows API 호출용
        "ctypes.windll.shell32",  # Windows 쉘 인터페이스
        "win32api",  # Windows API
        "win32con",  # Windows 상수
        "socket",  # 네트워크 소켓용
        "webbrowser",  # 브라우저 실행용
        "logging",  # 로깅용
        "subprocess",  # 프로세스 실행용
        "threading",  # 멀티스레딩용
        "yaml",  # 설정 파일 로드용
        "dotenv",  # 환경 변수 로드용
        "numpy",  # 음성 처리용
        "encodings.utf_8",  # 인코딩 처리
        "encodings.ascii",  # 인코딩 처리
        "encodings.cp949",  # 한글 인코딩 처리
        "encodings.idna",  # URL 인코딩 처리
        "encodings.latin_1",  # 추가 인코딩
        "encodings.mbcs",  # Windows 멀티바이트 문자셋
        "encodings.utf_16",  # 추가 인코딩
        "encodings.utf_32",  # 추가 인코딩
        "encodings.euc_kr",  # 한글 인코딩 추가
        "encodings.euc_jp",  # 일본어 인코딩
        "encodings.gb2312",  # 중국어 간체 인코딩
        "encodings.gbk",  # 중국어 확장 인코딩
        "encodings.big5",  # 중국어 번체 인코딩
        "encodings.shift_jis",  # 일본어 인코딩
    ]

    hidden_import_params = []
    for module in hidden_imports:
        hidden_import_params.extend(["--hidden-import", module])

    # 추가 콘솔 출력 개선
    logging.info("\n=== PyInstaller 빌드 시작 ===")
    logging.info(f"현재 작업 디렉토리: {current_dir}")
    logging.info(f"streamlit_app.py 파일 위치: {main_path}")

    # 일부 PyInstaller 버전에서는 main 스크립트를 직접 지정하는 것이 더 안정적
    main_entry_point = f"""
import sys
import os

# 필요한 경로 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# app_launcher 모듈에서 main 함수 가져오기 
from app_launcher import main

# 메인 함수 실행
if __name__ == "__main__":
    main()
"""

    # 임시 진입점 스크립트 생성
    entry_script = current_dir / "pyinstaller_entry.py"
    with open(entry_script, "w", encoding="utf-8") as f:
        f.write(main_entry_point)

    logging.info(f"임시 진입점 스크립트 생성: {entry_script}")

    # PyInstaller 명령어 구성
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",  # 단일 EXE 파일로 빌드
        "--console",  # 콘솔 창 표시 (오류 확인용)
        "--name",
        "VoiceProgram",  # EXE 파일 이름
        "--uac-admin",  # 관리자 권한 요청 (Windows UAC)
        "--clean",  # 빌드 전 캐시 정리
        "--workpath",
        str(current_dir / "build"),  # 빌드 작업 경로 지정
        "--distpath",
        str(current_dir / "dist"),  # 출력 경로 지정
        "--specpath",
        str(current_dir),  # spec 파일 경로 지정
        *hidden_import_params,  # 숨겨진 의존성
        *add_data_params,  # 동적으로 생성된 파일 목록
        *icon_param,
        str(entry_script),  # 대체 진입점 스크립트
    ]

    # 명령어 실행
    logging.info(f"실행 명령어: {' '.join(cmd)}")
    try:
        process = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")

        # 표준 출력 및 오류 로깅
        logging.info("빌드 출력:")
        for line in process.stdout.splitlines():
            logging.info(f"  {line}")

        if process.stderr:
            logging.warning("빌드 오류/경고:")
            for line in process.stderr.splitlines():
                logging.warning(f"  {line}")

        if process.returncode == 0:
            logging.info("\n빌드가 성공적으로 완료되었습니다!")
            dist_dir = current_dir / "dist"
            exe_path = dist_dir / "VoiceProgram.exe"
            logging.info(f"EXE 파일 위치: {exe_path}")

            # 실행 지침
            logging.info("\n실행 지침:")
            logging.info("1. 생성된 EXE 파일을 마우스 오른쪽 버튼으로 클릭하여 '관리자 권한으로 실행'을 선택하세요.")
            logging.info("2. 방화벽 경고가 표시되면 '액세스 허용'을 클릭하세요.")
            logging.info("3. 프로그램이 자동으로 브라우저를 열고 웹 인터페이스를 표시합니다.")
            logging.info("4. 브라우저가 자동으로 열리지 않으면, 콘솔 창에 표시된 URL을 브라우저에 직접 입력하세요.")

            print("\n빌드가 성공적으로 완료되었습니다!")
            print(f"EXE 파일 위치: {exe_path}")
            print("\n실행 지침:")
            print("1. 생성된 EXE 파일을 마우스 오른쪽 버튼으로 클릭하여 '관리자 권한으로 실행'을 선택하세요.")
            print("2. 방화벽 경고가 표시되면 '액세스 허용'을 클릭하세요.")
            print("3. 프로그램이 자동으로 브라우저를 열고 웹 인터페이스를 표시합니다.")
            print("4. 브라우저가 자동으로 열리지 않으면, 콘솔 창에 표시된 URL을 브라우저에 직접 입력하세요.")
        else:
            logging.error("\n빌드 중 오류가 발생했습니다.")
            logging.error(f"반환 코드: {process.returncode}")
            logging.error("자세한 내용은 로그 파일을 확인하세요.")

            print("\n빌드 중 오류가 발생했습니다.")
            print(f"반환 코드: {process.returncode}")
            print(f"자세한 내용은 로그 파일({log_file})을 확인하세요.")

    except Exception as e:
        logging.error(f"빌드 실행 중 예외 발생: {e}")
        print(f"빌드 실행 중 예외 발생: {e}")
        print(f"자세한 내용은 로그 파일({log_file})을 확인하세요.")


if __name__ == "__main__":
    # PyInstaller가 설치되어 있는지 확인
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "show", "pyinstaller"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError:
        print("PyInstaller가 설치되어 있지 않습니다. 설치를 시작합니다...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # EXE 빌드
    build_exe()
