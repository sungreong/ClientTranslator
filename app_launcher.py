import os
import sys
import time
import subprocess
import threading
import webbrowser
import socket
import traceback
import logging
from pathlib import Path
from datetime import datetime
import ctypes


# Windows에서 관리자 권한 확인
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


# Windows에서 방화벽 예외 추가
def add_firewall_exception(port):
    """Windows 방화벽에 프로그램 예외 추가 시도"""
    try:
        if os.name == "nt":  # Windows 환경인 경우만
            program_path = sys.executable
            program_name = "VoiceProgram"

            logging.info(f"방화벽 예외 추가를 시도합니다. 포트: {port}, 프로그램: {program_path}")

            # 방화벽 인바운드 규칙 추가 명령어
            cmd = [
                "netsh",
                "advfirewall",
                "firewall",
                "add",
                "rule",
                f'name="{program_name}"',
                "dir=in",
                "action=allow",
                f'program="{program_path}"',
                "enable=yes",
                "profile=any",
                f"localport={port}",
                "protocol=TCP",
            ]

            # 관리자 권한 확인
            if is_admin():
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    logging.info("방화벽 예외가 성공적으로 추가되었습니다.")
                    return True
                else:
                    logging.warning(f"방화벽 예외 추가 실패: {result.stderr}")
            else:
                logging.warning("방화벽 예외 추가를 위해서는 관리자 권한이 필요합니다.")

        return False
    except Exception as e:
        logging.error(f"방화벽 예외 추가 중 오류 발생: {e}")
        return False


# 로그 설정
def setup_logging():
    """로그 설정 초기화"""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / f"app_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    # 파일과 콘솔에 모두 로그 출력
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler(log_file, encoding="utf-8", errors="replace"), logging.StreamHandler()],
    )

    logging.info(f"로그 파일이 생성되었습니다: {log_file}")

    # 시스템 정보 로깅
    logging.info(f"시스템 정보:")
    logging.info(f"- Python 버전: {sys.version}")
    logging.info(f"- 실행 경로: {sys.executable}")
    logging.info(f"- 플랫폼: {sys.platform}")
    logging.info(f"- 기본 인코딩: {sys.getdefaultencoding()}")
    logging.info(f"- 파일 시스템 인코딩: {sys.getfilesystemencoding()}")
    logging.info(f"- 현재 작업 디렉토리: {os.getcwd()}")

    try:
        # Windows 코드 페이지 확인
        if os.name == "nt":
            import subprocess

            result = subprocess.run(
                ["chcp"], shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace"
            )
            if result.stdout:
                logging.info(f"- Windows 콘솔 코드 페이지: {result.stdout.strip()}")
    except Exception as e:
        logging.warning(f"코드 페이지 확인 중 오류 발생: {e}")

    return log_file


def is_port_available(port):
    """지정된 포트가 사용 가능한지 확인합니다."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("0.0.0.0", port))  # 모든 인터페이스로 바인딩 시도
            logging.info(f"사용 가능한 포트를 찾았습니다: {port}")
            return True
    except OSError:
        return False


def try_port_range(start, end):
    """주어진 범위에서 사용 가능한 포트를 찾아 반환합니다."""
    for port in range(start, end):
        if is_port_available(port):
            return port
    return None


def find_free_port():
    """사용 가능한 포트를 찾아 반환합니다."""
    # 첫 번째 범위: 8000-8999 (사용자 요청)
    port = try_port_range(8000, 9000)
    if port:
        return port

    # 두 번째 범위: 3000-3999
    port = try_port_range(3000, 4000)
    if port:
        return port

    # 세 번째 범위: 10000-10999
    port = try_port_range(10000, 11000)
    if port:
        return port

    logging.error("사용 가능한 포트를 찾을 수 없습니다.")
    # 최종적으로 실패하면 기본값 8501 반환
    return 8501


def get_streamlit_path():
    """시스템에 설치된 streamlit 실행 파일의 경로를 찾습니다."""
    try:
        # Python 스크립트와 같은 디렉토리에 있는 venv 환경 확인
        base_dir = os.path.dirname(os.path.abspath(__file__))

        # Windows인 경우
        if os.name == "nt":
            # 가상 환경내 Scripts 폴더 확인
            venv_path = os.path.join(base_dir, "venv", "Scripts", "streamlit.exe")
            if os.path.exists(venv_path):
                return venv_path

            # 시스템 전역에 설치된 streamlit 확인
            try:
                result = subprocess.run(["where", "streamlit"], capture_output=True, text=True, encoding="utf-8")
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip().split("\n")[0]
            except Exception as e:
                logging.warning(f"streamlit 경로 검색 중 오류: {e}")

        # Linux/Mac인 경우
        else:
            # 가상 환경내 bin 폴더 확인
            venv_path = os.path.join(base_dir, "venv", "bin", "streamlit")
            if os.path.exists(venv_path):
                return venv_path

            # 시스템 전역에 설치된 streamlit 확인
            try:
                result = subprocess.run(["which", "streamlit"], capture_output=True, text=True, encoding="utf-8")
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip()
            except Exception as e:
                logging.warning(f"streamlit 경로 검색 중 오류: {e}")

        # Python -m streamlit로 실행할 수 있도록 Python 경로 반환
        python_exe = sys.executable
        if python_exe:
            logging.info(f"streamlit 직접 경로를 찾지 못해 Python으로 실행합니다: {python_exe}")
            return python_exe

        logging.error("streamlit 또는 python 실행 파일을 찾을 수 없습니다.")
        return None

    except Exception as e:
        logging.error(f"streamlit 경로 찾기 실패: {e}")
        return None


def launch_streamlit(port):
    """지정된 포트에서 Streamlit 애플리케이션을 실행합니다."""
    try:
        streamlit_path = get_streamlit_path()
        if not streamlit_path:
            logging.error("Streamlit 실행 파일을 찾을 수 없습니다.")
            return False

        # streamlit_app.py 파일 찾기 (여러 위치 시도)
        main_script = None
        possible_locations = [
            # 1. 현재 디렉토리
            os.path.join(os.getcwd(), "streamlit_app.py"),
            # 2. 스크립트와 같은 디렉토리
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "streamlit_app.py"),
            # 3. 상위 디렉토리
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "streamlit_app.py"),
            # 4. 번들된 파일 위치 (PyInstaller)
            os.path.join(getattr(sys, "_MEIPASS", os.getcwd()), "streamlit_app.py"),
        ]

        for location in possible_locations:
            if os.path.exists(location):
                main_script = location
                logging.info(f"streamlit_app.py 파일을 찾았습니다: {main_script}")
                break

        if not main_script:
            logging.error("streamlit_app.py 파일을 찾을 수 없습니다.")
            for location in possible_locations:
                logging.error(f"  시도한 위치: {location} (존재하지 않음)")
            return False

        # 환경변수 설정 - 인코딩 관련
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        # Python으로 streamlit을 실행하는 경우
        if streamlit_path == sys.executable:
            cmd = [
                streamlit_path,
                "-m",
                "streamlit",
                "run",
                main_script,
                "--server.port",
                str(port),
                "--server.headless",
                "true",
            ]
        else:
            cmd = [streamlit_path, "run", main_script, "--server.port", str(port), "--server.headless", "true"]

        logging.info(f"실행 명령어: {' '.join(cmd)}")

        # subprocess 실행 시 UTF-8 인코딩 명시적 지정
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",  # 인코딩 오류 발생 시 대체 문자로 대체
            env=env,  # 환경변수 전달
        )

        # 로그 스트림 처리를 위한 스레드 시작
        stdout_thread = threading.Thread(target=log_stream, args=(process.stdout, logging.INFO), daemon=True)
        stderr_thread = threading.Thread(target=log_stream, args=(process.stderr, logging.ERROR), daemon=True)
        stdout_thread.start()
        stderr_thread.start()

        # 프로세스가 시작되었는지 확인
        if process.poll() is None:
            logging.info(f"Streamlit이 포트 {port}에서 실행 중입니다.")
            return process
        else:
            stderr = process.stderr.read()
            logging.error(f"Streamlit 실행 실패: {stderr}")
            return False

    except Exception as e:
        logging.error(f"Streamlit 실행 중 오류 발생: {e}")
        logging.error(traceback.format_exc())
        return False


def log_stream(stream, level):
    """스트림의 출력을 로그로 리다이렉트"""
    try:
        for line in iter(stream.readline, ""):
            line = line.strip()
            if not line:
                continue

            if level == logging.INFO:
                logging.info(f"STREAMLIT: {line}")
            else:
                logging.error(f"STREAMLIT ERROR: {line}")
    except Exception as e:
        logging.error(f"로그 스트림 처리 중 오류 발생: {e}")
    finally:
        stream.close()


def open_browser(port):
    """브라우저 열기"""
    # 서버가 시작될 때까지 잠시 기다림
    logging.info("브라우저를 열기 전에 5초 대기합니다...")
    time.sleep(5)  # 대기 시간 늘림

    # IP 주소 확인
    try:
        # 내부 IP 주소 가져오기
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # Google DNS에 연결 (실제로 연결하지는 않음)
        local_ip = s.getsockname()[0]
        s.close()

        # localhost와 내부 IP 양쪽 모두 시도
        urls = [f"http://localhost:{port}", f"http://127.0.0.1:{port}", f"http://{local_ip}:{port}"]

        # 여러 URL 시도
        for url in urls:
            logging.info(f"브라우저 열기 시도: {url}")
            if webbrowser.open(url):
                logging.info(f"브라우저를 성공적으로 열었습니다: {url}")
                break
            else:
                logging.warning(f"브라우저 열기 실패: {url}")

        # 접속 방법 안내
        print(f"\n스트림릿 서버가 시작되었습니다. 다음 주소로 접속할 수 있습니다:")
        print(f"- 로컬: http://localhost:{port}")
        print(f"- 내부 IP: http://{local_ip}:{port}\n")

    except Exception as e:
        logging.error(f"브라우저 열기 실패: {e}")
        url = f"http://localhost:{port}"
        webbrowser.open(url)


def create_data_directories():
    """필요한 디렉토리 생성"""
    directories = [
        "data",  # 데이터 디렉토리
        "recordings",  # 녹음 디렉토리
        "conversations",  # 대화 디렉토리
        "audio_files",  # 오디오 파일 디렉토리
        "logs",  # 로그 디렉토리
    ]

    for dir_name in directories:
        dir_path = Path(dir_name)
        dir_path.mkdir(exist_ok=True)
        logging.info(f"디렉토리 확인/생성: {dir_path}")


def test_port_connectivity(port):
    """포트 연결 가능 여부 테스트"""
    try:
        # 내부 연결 테스트
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(2)
            result = s.connect_ex(("localhost", port))
            if result == 0:
                logging.info(f"포트 {port}가 localhost에서 접속 가능합니다.")
                return True
            else:
                logging.warning(f"포트 {port}가 localhost에서 접속 불가능합니다. 결과 코드: {result}")
                return False
    except Exception as e:
        logging.error(f"포트 연결 테스트 중 오류 발생: {e}")
        return False


def main():
    """메인 함수"""
    # 로그 설정
    log_file = setup_logging()

    try:
        logging.info("보이스 프로그램을 시작합니다...")

        # 필요한 디렉토리 생성
        create_data_directories()

        # 사용 가능한 포트 찾기
        port = find_free_port()

        # 방화벽 예외 추가 시도
        firewall_added = add_firewall_exception(port)
        if firewall_added:
            logging.info("방화벽 예외가 추가되었습니다.")
        else:
            logging.info("참고: 방화벽 예외가 추가되지 않았습니다. 접속 문제가 발생할 수 있습니다.")

        # Streamlit 앱 실행
        process = launch_streamlit(port)

        # 서버 시작 대기
        time.sleep(2)

        # 포트 연결 테스트
        if not test_port_connectivity(port):
            logging.warning(f"포트 {port}에 연결할 수 없습니다. 방화벽 설정을 확인하세요.")
            print(f"\n경고: 포트 {port}에 연결할 수 없습니다.")
            print("1. Windows 방화벽 설정을 확인하세요.")
            print("2. 다른 방화벽 프로그램이 실행 중인지 확인하세요.")
            print(f"3. 직접 브라우저에서 http://localhost:{port} 주소를 열어보세요.\n")

        # 브라우저 열기
        threading.Thread(target=open_browser, args=(port,)).start()

        # 프로세스 종료 대기
        logging.info("Streamlit 프로세스 종료를 기다립니다...")
        return_code = process.wait()
        logging.info(f"Streamlit 프로세스가 종료되었습니다. 반환 코드: {return_code}")

    except KeyboardInterrupt:
        logging.info("키보드 인터럽트로 프로그램이 종료되었습니다.")
    except Exception as e:
        error_msg = f"예상치 못한 오류가 발생했습니다: {str(e)}"
        logging.error(error_msg)
        logging.error(traceback.format_exc())

        # 콘솔에도 오류 메시지 출력
        print(error_msg)
        print(f"자세한 오류 내용은 로그 파일을 확인하세요: {log_file}")

        # 콘솔창이 바로 닫히지 않도록 사용자 입력 대기
        input("계속하려면 아무 키나 누르세요...")


if __name__ == "__main__":
    main()
