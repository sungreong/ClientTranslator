import streamlit as st
import logging

# Streamlit 페이지 설정 (가장 먼저 호출해야 함)
st.set_page_config(page_title="보이스 프로그램", page_icon="🎙️", layout="wide")

import os
from dotenv import load_dotenv
import numpy as np
from pydub import AudioSegment
import openai
import json
from datetime import datetime
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
import glob
from pathlib import Path
import base64
import re
import pyaudio
import wave
from firebase_admin import credentials, initialize_app, auth
from database import get_db_manager

# 환경 변수 로드
load_dotenv()

# 데이터베이스 매니저 초기화
db_manager = get_db_manager()

# OpenAI API 설정 (최신 API 방식으로 변경)
api_key = os.getenv("OPENAI_API_KEY")
client = None
if api_key:
    client = openai.OpenAI(api_key=api_key)

# config 파일 로드
import os

logging.info(os.getcwd())
logging.info(os.listdir(os.getcwd()))
current_dir = Path(__file__).parent
logging.info(current_dir)
with open(current_dir / "config.yaml", "r", encoding="utf-8") as file:
    config = yaml.load(file, Loader=SafeLoader)

# 인증 설정
authenticator = stauth.Authenticate(
    config["credentials"], config["cookie"]["name"], config["cookie"]["key"], config["cookie"]["expiry_days"]
)

# 언어별 국기 아이콘
LANGUAGE_ICONS = {"ja": "🇯🇵", "zh": "🇨🇳", "en": "🇺🇸", "ko": "🇰🇷"}

# 언어 레이블
LANGUAGE_LABELS = {"ko": "한국어", "en": "영어", "ja": "일본어", "zh": "중국어"}


def main():
    # 필요한 디렉토리 생성
    create_required_directories()

    # 오디오 폴더와 데이터베이스 동기화
    db_manager.sync_groups_with_folders()

    # 오디오 파일 스캔 및 데이터베이스 업데이트
    scan_result = db_manager.scan_audio_files_and_update_db()
    if scan_result and (scan_result.get("added", 0) > 0 or scan_result.get("updated", 0) > 0):
        st.toast(
            f"오디오 파일 스캔 완료: {scan_result.get('added', 0)}개 추가, {scan_result.get('updated', 0)}개 업데이트"
        )

    # 모든 그룹에 대해 기본 멘트 생성 확인
    groups = db_manager.get_phrase_groups()
    for group in groups:
        # 각 그룹에 대해 언어별 기본 멘트 생성
        result = db_manager.create_default_phrases_for_group(group["id"], group["name"])
        if result and result.get("created", 0) > 0:
            st.toast(f"{group['name']} 그룹에 {result.get('created')}개 기본 멘트 생성 완료")

    # 세션 상태 초기화
    if "recording" not in st.session_state:
        st.session_state.recording = False
    if "frames" not in st.session_state:
        st.session_state.frames = []
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "username" not in st.session_state:
        st.session_state.username = None
    if "selected_customer" not in st.session_state:
        st.session_state.selected_customer = None
    if "active_tab" not in st.session_state:
        st.session_state.active_tab = 0

    # 로그인 상태 확인
    if not st.session_state.authenticated or not st.session_state.username:
        show_login()
    else:
        show_main_app()


def show_login():
    st.title("보이스 프로그램 로그인")

    # 개발 모드 확인
    dev_mode = st.checkbox("개발 모드")

    if dev_mode:
        st.session_state.authenticated = True
        st.session_state.username = "admin"  # 기본 사용자명 사용
        st.write("개발자 모드로 로그인 중...")
        st.write("잠시 후 메인 화면으로 이동합니다.")
        # 녹음 디렉토리 생성
        os.makedirs(os.path.join("recordings", "admin"), exist_ok=True)
        st.rerun()  # rerun() 사용
    else:
        try:
            # bcrypt 가져오기
            import bcrypt

            # 로그인 폼 생성
            with st.form(key="login_form"):
                st.subheader("로그인")
                username_input = st.text_input("이메일", placeholder="이메일 주소 입력")
                password_input = st.text_input("비밀번호", type="password", placeholder="비밀번호 입력")

                # 폼 제출 버튼
                submit_button = st.form_submit_button("로그인")

            # 폼 제출 결과 처리
            if submit_button:
                if username_input and password_input:
                    # 직접 config.yaml에서 사용자 정보 확인
                    for username, user_data in config["credentials"]["usernames"].items():
                        if user_data["email"] == username_input:
                            # 일반 텍스트 비밀번호로 시도하는 경우 (개발 환경용)
                            if user_data["password"] == password_input:
                                st.session_state.authenticated = True
                                st.session_state.username = username
                                st.success("로그인 성공! 메인 화면으로 이동합니다.")
                                os.makedirs(os.path.join("recordings", username), exist_ok=True)
                                st.rerun()
                                break
                            # bcrypt 해시 비밀번호 확인 (일반 운영환경용)
                            try:
                                stored_pw = user_data["password"]
                                if stored_pw.startswith("$2b$") or stored_pw.startswith("$2a$"):
                                    # bcrypt 해시 비교
                                    if bcrypt.checkpw(password_input.encode(), stored_pw.encode()):
                                        st.session_state.authenticated = True
                                        st.session_state.username = username
                                        st.success("로그인 성공! 메인 화면으로 이동합니다.")
                                        os.makedirs(os.path.join("recordings", username), exist_ok=True)
                                        st.rerun()
                                        break
                            except Exception as hash_error:
                                logging.error(f"비밀번호 해시 확인 중 오류: {hash_error}")
                    else:
                        logging.error(f"이메일/비밀번호가 올바르지 않습니다: {username_input}")
                        st.error("이메일/비밀번호가 올바르지 않습니다")
                else:
                    st.warning("이메일과 비밀번호를 입력해주세요")
        except Exception as e:
            st.error(f"로그인 처리 중 오류가 발생했습니다: {e}")
            st.info("개발 모드를 사용하여 로그인해보세요.")


def show_main_app():
    st.title("보이스 프로그램")
    st.write(f"환영합니다, {st.session_state.username}님!")

    # 커스텀 로그아웃 버튼
    if st.button("로그아웃"):
        # 세션 상태 초기화
        st.session_state.authenticated = False
        st.session_state.username = None
        st.success("로그아웃되었습니다!")
        st.rerun()

    # 탭 설정 - 간단한 탭 구현으로 복원
    tab_names = ["녹음", "멘트 관리", "녹음 기록", "대화", "설정"]
    tabs = st.tabs(tab_names)

    # 탭 내용 표시 - 조건 검사 없이 각 탭에 내용 직접 표시
    # 녹음 탭
    with tabs[0]:
        show_recording_tab()

    # 멘트 관리 탭
    with tabs[1]:
        show_phrase_management_tab()

    # 녹음 기록 탭
    with tabs[2]:
        show_recording_history_tab()

    # 대화 탭
    with tabs[3]:
        show_conversation_tab()

    # 설정 탭
    with tabs[4]:
        show_settings_tab()


def show_recording_tab():
    st.header("음성 녹음")

    # 멘트 선택 섹션 (폼 바깥에서 선택)
    st.subheader("멘트 선택")

    # 선택 방식 (검색 또는 그룹 선택)
    selection_method = st.radio("선택 방식", ["검색으로 찾기", "그룹에서 선택하기"], horizontal=True)

    selected_phrase = None

    if selection_method == "검색으로 찾기":
        # 멘트 검색
        search_query = st.text_input("멘트 검색", "")

        # 검색 결과 표시
        if search_query:
            search_results = db_manager.search_phrases(search_query)
            if search_results:
                selected_phrase_id = st.selectbox(
                    "검색 결과에서 멘트 선택",
                    options=[
                        (result["id"], f"{result['group_name']} - {result['language']} - {result['content'][:30]}...")
                        for result in search_results
                    ],
                    format_func=lambda x: x[1],
                )

                if selected_phrase_id:
                    # 선택된 멘트 정보 찾기
                    for result in search_results:
                        if result["id"] == selected_phrase_id[0]:
                            selected_phrase = {
                                "id": result["id"],
                                "group_id": result["group_id"],
                                "language": result["language"],
                                "content": result["content"],
                                "audio_path": result["audio_path"] if "audio_path" in result else None,
                            }
                            break
            else:
                st.info("검색 결과가 없습니다.")
    else:  # 그룹에서 선택하기
        # 그룹 선택
        groups = db_manager.get_phrase_groups()
        if groups:
            group_options = [(group["id"], group["name"]) for group in groups]
            selected_group_id = st.selectbox("그룹 선택", options=group_options, format_func=lambda x: x[1])

            if selected_group_id:
                # 선택된 그룹의 멘트 가져오기
                phrases = db_manager.get_phrases_by_group(selected_group_id[0])

                # 언어별로 정리
                languages = {}
                for phrase in phrases:
                    lang = phrase["language"]
                    if lang not in languages:
                        languages[lang] = []
                    languages[lang].append(phrase)

                # 언어 선택
                if languages:
                    language_options = list(languages.keys())
                    selected_language = st.selectbox(
                        "언어 선택",
                        options=language_options,
                        format_func=lambda x: {"ko": "한국어", "en": "영어", "ja": "일본어", "zh": "중국어"}.get(x, x),
                    )

                    if selected_language and selected_language in languages:
                        # 선택된 언어의 멘트
                        phrase = languages[selected_language][0]  # 언어당 하나의 멘트만 있음
                        selected_phrase = {
                            "id": phrase["id"],
                            "group_id": phrase["group_id"],
                            "language": phrase["language"],
                            "content": phrase["content"],
                            "audio_path": phrase["audio_path"],
                        }
        else:
            st.info("등록된 그룹이 없습니다.")

    # 이전에 선택된 멘트가 있는 경우 (새 선택이 없을 때만)
    if not selected_phrase and "selected_phrase" in st.session_state:
        phrase = st.session_state.selected_phrase
        language_name = {"ko": "한국어", "en": "영어", "ja": "일본어", "zh": "중국어"}
        st.write(f"언어: {language_name.get(phrase['language'], phrase['language'])}")
        st.text_area("멘트 내용", phrase["content"], height=150, disabled=True)
        st.success("이전에 선택한 멘트를 사용합니다.")
        selected_phrase = phrase

    # 선택된 멘트 정보 표시 및 오디오 재생
    if selected_phrase:
        language_name = {"ko": "한국어", "en": "영어", "ja": "일본어", "zh": "중국어"}
        st.write(f"언어: {language_name.get(selected_phrase['language'], selected_phrase['language'])}")
        st.text_area("멘트 내용", selected_phrase["content"], height=150, disabled=True)

        # 선택된 멘트 세션 상태에 저장 (다음 사용을 위해)
        st.session_state.selected_phrase = selected_phrase

        # 기존 녹음본 재생 (있는 경우)
        if selected_phrase.get("audio_path") and os.path.exists(selected_phrase["audio_path"]):
            st.write("기존 녹음본:")
            st.audio(selected_phrase["audio_path"])

    # 고객 ID 입력 및 녹음 폼 (선택 이후에 표시)
    if selected_phrase or "selected_phrase" in st.session_state:
        # 녹음 안내
        st.info("멘트를 읽고 녹음하세요. 마이크 아이콘을 클릭하여 녹음을 시작하세요.")

        with st.form(key="recording_form"):
            customer_id = st.text_input("고객 ID")

            # 녹음 위젯
            audio_bytes = st.audio_input("마이크로 녹음하기", key="audio_recorder")

            # 폼 제출 버튼
            submit_button = st.form_submit_button("저장하기")

            # 폼 제출 결과 처리 (폼 내부에서)
            if submit_button and audio_bytes is not None:
                if not customer_id:
                    st.error("고객 ID를 입력해주세요.")
                    return

        # 녹음 저장 처리 (폼 제출 후)
        if submit_button and audio_bytes is not None and customer_id:
            # 세션 상태에서 선택된 멘트 정보 가져오기
            phrase_to_use = st.session_state.get("selected_phrase")

            # 저장 경로 생성
            date_str = datetime.now().strftime("%Y-%m-%d")
            save_path = os.path.join("recordings", st.session_state.username, date_str, customer_id)
            os.makedirs(save_path, exist_ok=True)

            # 파일 저장
            time_str = datetime.now().strftime("%H%M%S")
            filename = f"recording_{time_str}.wav"
            filepath = os.path.join(save_path, filename)

            # 오디오 바이트를 파일로 저장
            with open(filepath, "wb") as f:
                if isinstance(audio_bytes, bytes):
                    f.write(audio_bytes)
                else:
                    # UploadedFile 객체인 경우 getbuffer() 사용
                    f.write(audio_bytes.getbuffer())

            st.success(f"녹음이 완료되었습니다: {filepath}")

            # 오디오 재생 (폼 외부에서)
            st.audio(audio_bytes)

            # 선택된 멘트가 있는 경우 멘트 정보 저장
            if phrase_to_use:
                # 그룹 이름 가져오기
                group_name = db_manager.get_group_name(phrase_to_use["group_id"])

                # 멘트 정보 저장
                phrase_info_path = os.path.join(save_path, f"phrase_info_{time_str}.json")
                with open(phrase_info_path, "w", encoding="utf-8") as f:
                    json.dump(
                        {
                            "phrase_id": phrase_to_use["id"],
                            "group_id": phrase_to_use["group_id"],
                            "group_name": group_name,
                            "language": phrase_to_use["language"],
                            "content": phrase_to_use["content"],
                        },
                        f,
                        ensure_ascii=False,
                        indent=2,
                    )

                st.info("멘트 정보가 녹음과 함께 저장되었습니다.")

                # OpenAI API를 사용한 STT 및 번역 처리
                if api_key and client:
                    with st.spinner("음성을 텍스트로 변환 중..."):
                        try:
                            # OpenAI API를 사용한 STT
                            with open(filepath, "rb") as audio_file:
                                # 오디오 파일 크기 확인 (25MB 제한)
                                audio_file.seek(0, os.SEEK_END)
                                file_size = audio_file.tell()
                                audio_file.seek(0)

                                if file_size > 25 * 1024 * 1024:
                                    st.error("오디오 파일이 너무 큽니다 (25MB 제한). 더 짧은 녹음을 시도해주세요.")
                                    transcription = "파일 크기 초과로 변환 실패"
                                else:
                                    # STT 처리
                                    response = client.audio.transcriptions.create(model="whisper-1", file=audio_file)
                                    transcription = response.text

                                    # STT 결과 텍스트 파일로 저장
                                    stt_path = os.path.join(save_path, f"stt_result_{time_str}.txt")
                                    with open(stt_path, "w", encoding="utf-8") as f:
                                        f.write(transcription)

                                    # 번역 처리 (기본 언어가 한국어이므로 일본어, 중국어, 영어로 번역)
                                    for lang in ["ja", "zh", "en"]:
                                        try:
                                            translation = translate_text(
                                                transcription, lang, save_path, "recording", time_str
                                            )

                                            # 번역 결과 파일명: translated_ja_time.txt, translated_zh_time.txt 등
                                            trans_path = os.path.join(save_path, f"translated_{lang}_{time_str}.txt")
                                            with open(trans_path, "w", encoding="utf-8") as f:
                                                f.write(translation)
                                        except Exception as e:
                                            st.error(f"{lang} 번역 중 오류 발생: {str(e)}")

                                    st.success(f"STT 및 번역 처리가 완료되었습니다.")
                        except Exception as e:
                            st.error(f"STT 처리 중 오류가 발생했습니다: {str(e)}")
                else:
                    st.warning("OpenAI API 키가 설정되지 않아 STT 및 번역 처리를 수행할 수 없습니다.")


def show_phrase_management_tab():
    st.header("멘트 관리")

    # 탭 구성: 검색, 전체 리스트, 그룹 관리
    mgmt_tabs = st.tabs(["🔍 검색", "📋 전체 리스트", "📁 그룹 관리"])

    # 검색 탭
    with mgmt_tabs[0]:
        # 검색 개선
        col1, col2 = st.columns([1, 2])
        with col1:
            search_option = st.radio("검색 범위", ["전체", "그룹 이름", "멘트 내용"])
        with col2:
            search_query = st.text_input("검색어 입력", "")

        # 검색 옵션을 database 함수 파라미터로 변환
        search_type_map = {"전체": "all", "그룹 이름": "group", "멘트 내용": "content"}

        # 검색 결과 표시
        if search_query:
            search_type = search_type_map.get(search_option, "all")
            search_results = db_manager.search_phrases(search_query, search_type)

            if search_results:
                # 그룹별로 결과 정리
                group_results = {}
                for result in search_results:
                    group_id = result["group_id"]
                    group_name = result["group_name"]

                    if group_id not in group_results:
                        group_results[group_id] = {"name": group_name, "phrases": []}

                    group_results[group_id]["phrases"].append(result)

                # 그룹별로 결과 표시
                st.subheader(f"검색 결과: {len(search_results)}개 멘트 발견")

                for group_id, group_data in group_results.items():
                    with st.expander(f"📁 그룹: {group_data['name']} ({len(group_data['phrases'])}개)", expanded=True):
                        # 언어별 분류
                        languages = {}
                        for phrase in group_data["phrases"]:
                            lang = phrase["language"]
                            if lang not in languages:
                                languages[lang] = []
                            languages[lang].append(phrase)

                        # 언어별 탭
                        if languages:
                            lang_tabs = st.tabs(
                                [f"{LANGUAGE_ICONS.get(lang, '')} {lang}" for lang in languages.keys()]
                            )

                            for i, (lang, phrases) in enumerate(languages.items()):
                                with lang_tabs[i]:
                                    # 멘트 표시
                                    for phrase in phrases:
                                        with st.container():
                                            cols = st.columns([3, 1])

                                            with cols[0]:
                                                st.markdown(f"**멘트 ID: {phrase['id']}**")
                                                st.text_area(
                                                    "내용",
                                                    phrase["content"],
                                                    height=100,
                                                    key=f"search_phrase_{phrase['id']}",
                                                )

                                            with cols[1]:
                                                # 오디오 재생 (있는 경우)
                                                if phrase["audio_path"] and os.path.exists(phrase["audio_path"]):
                                                    st.audio(phrase["audio_path"])
                                                    st.caption(f"파일명: {os.path.basename(phrase['audio_path'])}")
                                                else:
                                                    st.warning("녹음 없음")

                                                # 녹음 탭으로 이동 버튼
                                                if st.button(f"녹음에 사용", key=f"search_use_{phrase['id']}"):
                                                    # 선택한 멘트 정보 저장
                                                    st.session_state.selected_phrase = {
                                                        "id": phrase["id"],
                                                        "group_id": phrase["group_id"],
                                                        "language": phrase["language"],
                                                        "content": phrase["content"],
                                                    }
                                                    # 활성 탭을 녹음 탭(0)으로 변경
                                                    st.session_state.active_tab = 0
                                                    st.success("멘트가 선택되었습니다. 녹음 탭으로 이동합니다.")

                        st.markdown("---")
            else:
                st.info("검색 결과가 없습니다.")

    # 전체 리스트 탭
    with mgmt_tabs[1]:
        st.subheader("멘트 전체 리스트")

        # 음성이 있는 멘트만 표시할지 여부
        show_audio_only = st.checkbox("음성 데이터가 있는 멘트만 표시", value=True)

        # 그룹 목록 가져오기 (phrase_groups 테이블만 사용)
        groups = db_manager.get_phrase_groups()

        if groups:
            # 그룹 선택 드롭다운
            group_options = [(group["id"], f"{group['name']}") for group in groups]

            selected_group_option = st.selectbox(
                "그룹 선택",
                options=group_options,
                format_func=lambda x: x[1] if isinstance(x, tuple) else x,
                key="list_group_selectbox",
            )

            if selected_group_option:
                selected_group_id = selected_group_option[0]
                selected_group_name = next(g["name"] for g in groups if g["id"] == selected_group_id)

                # 선택한 그룹의 멘트 가져오기
                group_phrases = db_manager.get_phrases_by_group(selected_group_id)

                print(f"[DEBUG] 그룹 {selected_group_id}({selected_group_name})의 멘트: {len(group_phrases)}개")

                # 음성 데이터 필터링 (클라이언트 측에서)
                if show_audio_only:
                    filtered_by_audio = []
                    for p in group_phrases:
                        has_audio = p.get("audio_path") and os.path.exists(p.get("audio_path"))
                        print(
                            f"[DEBUG] 멘트 ID {p.get('id')}: 오디오 경로 {p.get('audio_path')}, 파일 존재: {has_audio}"
                        )
                        if has_audio:
                            filtered_by_audio.append(p)

                    group_phrases = filtered_by_audio
                    print(f"[DEBUG] 오디오 필터링 후: {len(group_phrases)}개 멘트 남음")

                if not group_phrases:
                    if show_audio_only:
                        st.info(f"선택한 그룹 '{selected_group_name}'에 음성 데이터가 있는 멘트가 없습니다.")
                    else:
                        st.info(f"선택한 그룹 '{selected_group_name}'에 멘트가 없습니다.")
                else:
                    # 선택한 그룹의 언어 목록 추출
                    available_languages = set(p["language"] for p in group_phrases)

                    # 언어 선택 드롭다운
                    language_options = [
                        (lang, f"{LANGUAGE_ICONS.get(lang, '')} {lang}") for lang in available_languages
                    ]

                    if language_options:
                        selected_language_option = st.selectbox(
                            "언어 선택",
                            options=language_options,
                            format_func=lambda x: x[1] if isinstance(x, tuple) else x,
                            key="list_language_selectbox",
                        )

                        if selected_language_option:
                            selected_language = selected_language_option[0]

                            # 필터링된 멘트 목록 - 언어로만 필터링
                            filtered_phrases = [p for p in group_phrases if p["language"] == selected_language]

                            if not filtered_phrases:
                                st.info(f"선택한 그룹과 언어에 표시할 멘트가 없습니다.")
                            else:
                                st.write(f"{len(filtered_phrases)}개 멘트 표시")

                                # 멘트 표시
                                for phrase in filtered_phrases:
                                    with st.container():
                                        st.markdown(f"**멘트 ID: {phrase['id']}**")

                                        col1, col2 = st.columns([2, 1])

                                        with col1:
                                            st.text_area(
                                                "내용",
                                                phrase["content"],
                                                height=100,
                                                key=f"list_phrase_{phrase['id']}",
                                            )

                                        with col2:
                                            # 오디오 영역
                                            if phrase["audio_path"] and os.path.exists(phrase["audio_path"]):
                                                st.audio(phrase["audio_path"])
                                                st.caption(f"파일명: {os.path.basename(phrase['audio_path'])}")
                                            else:
                                                st.warning("녹음된 오디오가 없습니다")

                                        # 액션 버튼
                                        col1, col2, col3, col4 = st.columns(4)

                                        with col1:
                                            if st.button(f"녹음에 사용", key=f"list_use_{phrase['id']}"):
                                                # 선택한 멘트 정보 저장
                                                st.session_state.selected_phrase = {
                                                    "id": phrase["id"],
                                                    "group_id": phrase["group_id"],
                                                    "language": phrase["language"],
                                                    "content": phrase["content"],
                                                }
                                                # 활성 탭을 녹음 탭(0)으로 변경
                                                st.session_state.active_tab = 0
                                                st.success("멘트가 선택되었습니다. 녹음 탭으로 이동합니다.")

                                        with col2:
                                            if st.button(f"멘트 삭제", key=f"list_delete_{phrase['id']}"):
                                                db_manager.delete_phrase(phrase["id"])
                                                st.success("멘트가 삭제되었습니다.")

                                        with col3:
                                            if phrase["audio_path"] and os.path.exists(phrase["audio_path"]):
                                                if st.button(f"오디오 삭제", key=f"list_delete_audio_{phrase['id']}"):
                                                    db_manager.update_phrase_audio(phrase["id"], None)
                                                    st.success("오디오가 삭제되었습니다.")

                                        with col4:
                                            # 녹음 버튼
                                            if st.button(f"녹음하기", key=f"list_record_btn_{phrase['id']}"):
                                                st.session_state[f"show_record_{phrase['id']}"] = True

                                        # 녹음 영역 (버튼 클릭 시 표시)
                                        if st.session_state.get(f"show_record_{phrase['id']}", False):
                                            with st.form(key=f"list_record_form_{phrase['id']}"):
                                                st.subheader("직접 녹음하기")

                                                # 녹음 위젯
                                                st.markdown("#### 💬 마이크 아이콘을 클릭하여 녹음하세요")
                                                audio_bytes = st.audio_input(
                                                    "마이크로 녹음", key=f"list_audio_recorder_{phrase['id']}"
                                                )

                                                col1, col2 = st.columns(2)
                                                with col1:
                                                    submit_record = st.form_submit_button(
                                                        "저장", use_container_width=True
                                                    )
                                                with col2:
                                                    cancel_record = st.form_submit_button(
                                                        "취소", use_container_width=True
                                                    )

                                            if cancel_record:
                                                st.session_state[f"show_record_{phrase['id']}"] = False
                                                st.rerun()

                                            if submit_record and audio_bytes is not None:
                                                # 파일 저장 경로 생성
                                                audio_dir = Path("audio_files")
                                                audio_dir.mkdir(exist_ok=True)

                                                # 그룹 폴더 생성
                                                group_dir = audio_dir / str(phrase["group_id"])
                                                group_dir.mkdir(exist_ok=True)

                                                # 언어 폴더 생성
                                                language_dir = group_dir / phrase["language"]
                                                language_dir.mkdir(exist_ok=True)

                                                # 파일명 생성
                                                save_name = f"phrase_{phrase['id']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
                                                filepath = os.path.join(language_dir, save_name)

                                                # 녹음된 오디오 바이트를 파일로 저장
                                                with open(filepath, "wb") as f:
                                                    if isinstance(audio_bytes, bytes):
                                                        f.write(audio_bytes)
                                                    else:
                                                        # UploadedFile 객체인 경우 getbuffer() 사용
                                                        f.write(audio_bytes.getbuffer())

                                                # 데이터베이스 업데이트
                                                db_manager.update_phrase_audio(phrase["id"], filepath)

                                                st.success(f"녹음이 저장되었습니다!")
                                                st.session_state[f"show_record_{phrase['id']}"] = False
                                                st.rerun()

                                    # 구분선
                                    st.markdown("---")
                    else:
                        st.info("이 그룹에 사용 가능한 언어가 없습니다.")
        else:
            st.info("등록된 멘트 그룹이 없습니다. 그룹 관리 탭에서 그룹을 추가해보세요.")

    # 그룹 관리 탭
    with mgmt_tabs[2]:
        # 멘트 그룹 목록
        st.subheader("멘트 그룹 관리")

        # 새 멘트 그룹 추가
        with st.expander("새 멘트 그룹 추가"):
            group_name = st.text_input("그룹 이름")
            group_desc = st.text_area("설명")

            if st.button("그룹 추가") and group_name:
                db_manager.add_phrase_group(group_name, group_desc)
                st.success(f"멘트 그룹 '{group_name}'이(가) 추가되었습니다.")

        # 기존 멘트 그룹 목록
        groups = db_manager.get_phrase_groups()

        if groups:
            for group in groups:
                with st.expander(f"{group['name']}"):
                    st.write(f"설명: {group['description'] or '없음'}")

                    # 해당 그룹의 멘트 표시
                    phrases = db_manager.get_phrases_by_group(group["id"])

                    # 지원하는 언어 목록
                    supported_languages = ["ko", "en", "ja", "zh"]
                    language_labels = {"ko": "한국어", "en": "영어", "ja": "일본어", "zh": "중국어"}

                    # 현재 있는 언어 확인
                    existing_languages = set(phrase["language"] for phrase in phrases)

                    # 없는 언어에 대해 행 자동 추가 버튼
                    missing_languages = [lang for lang in supported_languages if lang not in existing_languages]

                    if missing_languages:
                        st.warning(
                            f"이 그룹에 {', '.join([language_labels[lang] for lang in missing_languages])} 언어 멘트가 없습니다."
                        )
                        if st.button(f"누락된 언어 멘트 자동 추가", key=f"add_missing_{group['id']}"):
                            for lang in missing_languages:
                                db_manager.ensure_phrase_exists(group["id"], lang)
                            st.success("누락된 언어의 멘트가 추가되었습니다. 페이지를 새로고침합니다.")
                            st.rerun()

                    # 언어별 탭 생성
                    if phrases:
                        languages = set(phrase["language"] for phrase in phrases)
                        lang_tabs = st.tabs(
                            [f"{LANGUAGE_ICONS.get(lang, '')} {language_labels.get(lang, lang)}" for lang in languages]
                        )

                        for i, lang in enumerate(languages):
                            with lang_tabs[i]:
                                for phrase in [p for p in phrases if p["language"] == lang]:
                                    st.write(f"**멘트 ID: {phrase['id']}**")

                                    # 멘트 표시
                                    st.text_area(
                                        "멘트 내용",
                                        phrase["content"],
                                        height=100,
                                        key=f"phrase_{phrase['id']}",
                                        disabled=True,
                                    )

                                    # 기존 녹음 파일이 있으면 표시
                                    if (
                                        "audio_path" in phrase
                                        and phrase["audio_path"]
                                        and os.path.exists(phrase["audio_path"])
                                    ):
                                        st.markdown("##### 💿 녹음된 오디오 재생")
                                        st.audio(phrase["audio_path"])
                                        file_info = os.path.basename(phrase["audio_path"])
                                        st.caption(f"파일명: {file_info}")
                                        st.text(f"경로: {phrase['audio_path']}")
                                    else:
                                        st.warning(
                                            "녹음된 오디오가 없습니다. 아래에서 녹음하거나 파일을 업로드하세요."
                                        )

                                    # 오디오 관리 열
                                    col1, col2, col3 = st.columns(3)

                                    # 녹음 탭으로 이동
                                    with col1:
                                        if st.button(f"녹음 탭에서 사용", key=f"use_group_{phrase['id']}"):
                                            # 녹음 탭으로 이동하고 선택한 멘트 정보 저장
                                            st.session_state.selected_phrase = {
                                                "id": phrase["id"],
                                                "group_id": group["id"],
                                                "language": phrase["language"],
                                                "content": phrase["content"],
                                            }
                                            # 활성 탭을 녹음 탭(0)으로 변경
                                            st.session_state.active_tab = 0
                                            st.success("멘트가 선택되었습니다. 녹음 탭으로 이동합니다.")

                                    # 멘트 삭제 기능
                                    with col2:
                                        if st.button(f"멘트 삭제", key=f"delete_{phrase['id']}"):
                                            db_manager.delete_phrase(phrase["id"])
                                            st.success("멘트가 삭제되었습니다.")

                                    # 오디오 삭제 버튼
                                    with col3:
                                        if (
                                            "audio_path" in phrase
                                            and phrase["audio_path"]
                                            and os.path.exists(phrase["audio_path"])
                                        ):
                                            if st.button(f"오디오 삭제", key=f"delete_audio_{phrase['id']}"):
                                                db_manager.update_phrase_audio(phrase["id"], None)
                                                st.success("오디오가 삭제되었습니다.")

                                    # 오디오 파일 업로드
                                    with st.form(key=f"upload_form_{phrase['id']}"):
                                        st.subheader("오디오 파일 업로드")

                                        uploaded_file = st.file_uploader(
                                            "MP3 또는 WAV 파일 선택", type=["mp3", "wav"], key=f"upload_{phrase['id']}"
                                        )

                                        col1, col2 = st.columns(2)
                                        with col1:
                                            submit_upload = st.form_submit_button("업로드", use_container_width=True)
                                        with col2:
                                            cancel_upload = st.form_submit_button("취소", use_container_width=True)

                                    if submit_upload and uploaded_file is not None:
                                        # 파일 저장 경로 생성
                                        audio_dir = Path("audio_files")
                                        audio_dir.mkdir(exist_ok=True)

                                        # 그룹 폴더 생성
                                        group_dir = audio_dir / str(phrase["group_id"])
                                        group_dir.mkdir(exist_ok=True)

                                        # 언어 폴더 생성
                                        language_dir = group_dir / phrase["language"]
                                        language_dir.mkdir(exist_ok=True)

                                        # 파일명 생성 (파일 확장자 유지)
                                        file_ext = uploaded_file.name.split(".")[-1]
                                        save_name = f"phrase_{phrase['id']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{file_ext}"
                                        filepath = os.path.join(language_dir, save_name)

                                        # 파일 저장
                                        with open(filepath, "wb") as f:
                                            if isinstance(uploaded_file, bytes):
                                                f.write(uploaded_file)
                                            else:
                                                # UploadedFile 객체인 경우 getbuffer() 사용
                                                f.write(uploaded_file.getbuffer())

                                        # 데이터베이스 업데이트
                                        db_manager.update_phrase_audio(phrase["id"], filepath)

                                        st.success(f"오디오 파일이 업로드되었습니다!")

                                    # 직접 녹음
                                    with st.form(key=f"record_form_{phrase['id']}"):
                                        st.subheader("직접 녹음하기")

                                        # 녹음 위젯 (강조)
                                        st.markdown("#### 💬 마이크 아이콘을 클릭하여 녹음하세요")
                                        audio_bytes = st.audio_input(
                                            "마이크로 녹음하기", key=f"audio_recorder_{phrase['id']}"
                                        )

                                        st.info("녹음 후 아래 버튼을 클릭하여 저장하세요.")
                                        # 폼 제출 버튼
                                        submit_record = st.form_submit_button("녹음 저장", use_container_width=True)

                                    if submit_record and audio_bytes is not None:
                                        # 파일 저장 경로 생성
                                        audio_dir = Path("audio_files")
                                        audio_dir.mkdir(exist_ok=True)

                                        # 그룹 폴더 생성
                                        group_dir = audio_dir / str(phrase["group_id"])
                                        group_dir.mkdir(exist_ok=True)

                                        # 언어 폴더 생성
                                        language_dir = group_dir / phrase["language"]
                                        language_dir.mkdir(exist_ok=True)

                                        # 파일명 생성
                                        save_name = (
                                            f"phrase_{phrase['id']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
                                        )
                                        filepath = os.path.join(language_dir, save_name)

                                        # 녹음된 오디오 바이트를 파일로 저장
                                        with open(filepath, "wb") as f:
                                            if isinstance(audio_bytes, bytes):
                                                f.write(audio_bytes)
                                            else:
                                                # UploadedFile 객체인 경우 getbuffer() 사용
                                                f.write(audio_bytes.getbuffer())

                                        # 데이터베이스 업데이트
                                        db_manager.update_phrase_audio(phrase["id"], filepath)

                                        st.success(f"녹음이 저장되었습니다!")

                                    # 구분선
                                    st.markdown("---")

                    # 새 멘트 추가
                    st.subheader("새 멘트 추가")

                    # 언어 선택
                    language = st.selectbox(
                        "언어", ["한국어", "영어", "일본어", "중국어"], key=f"new_lang_{group['id']}"
                    )
                    language_code = {"한국어": "ko", "영어": "en", "일본어": "ja", "중국어": "zh"}[language]

                    # 멘트 내용
                    content = st.text_area("멘트 내용", key=f"new_content_{group['id']}")

                    # 파일 업로드와 직접 녹음을 열로 배치
                    col1, col2 = st.columns(2)

                    # 새 멘트 추가 시 오디오 파일 업로드 (선택 사항)
                    with col1:
                        st.subheader("파일 업로드")
                        uploaded_file = st.file_uploader(
                            "녹음 파일 업로드 (선택 사항)", type=["mp3", "wav"], key=f"upload_new_{group['id']}"
                        )

                    # 직접 녹음 추가 (선택 사항)
                    with col2:
                        st.subheader("직접 녹음")
                        st.markdown("#### 💬 마이크 아이콘을 클릭하여 녹음하세요")
                        audio_bytes = st.audio_input("마이크로 녹음하기", key=f"audio_recorder_new_{group['id']}")

                    if st.button("멘트 추가", key=f"add_{group['id']}") and (content or audio_bytes or uploaded_file):
                        # 내용이 없는 경우 기본 텍스트 설정
                        if not content:
                            content = f"{language} 녹음 파일 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

                        # 오디오 파일 처리
                        audio_path = None

                        # 폴더 구조 확인 및 생성
                        audio_dir = Path("audio_files")
                        audio_dir.mkdir(exist_ok=True)

                        # 그룹 폴더 - 그룹 ID와 동일하게 설정
                        group_dir = audio_dir / str(group["id"])
                        group_dir.mkdir(exist_ok=True)

                        # 언어 폴더
                        language_dir = group_dir / language_code
                        language_dir.mkdir(exist_ok=True)

                        # 1. 업로드된 파일 처리
                        if uploaded_file is not None:
                            # 새 멘트 추가
                            phrase_id = db_manager.add_phrase(group["id"], language_code, content)

                            # 파일명 생성 (파일 확장자 유지)
                            file_ext = uploaded_file.name.split(".")[-1]
                            save_name = (
                                f"{phrase_id}_{language_code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{file_ext}"
                            )
                            filepath = str(language_dir / save_name)

                            # 파일 저장
                            with open(filepath, "wb") as f:
                                if isinstance(uploaded_file, bytes):
                                    f.write(uploaded_file)
                                else:
                                    # UploadedFile 객체인 경우 getbuffer() 사용
                                    f.write(uploaded_file.getbuffer())

                            # 오디오 경로 업데이트
                            db_manager.update_phrase_audio(phrase_id, filepath)

                            st.success(f"멘트가 추가되었고 업로드된 오디오가 저장되었습니다.")

                        # 2. 녹음된 오디오 처리
                        elif audio_bytes is not None:
                            # 새 멘트 추가
                            phrase_id = db_manager.add_phrase(group["id"], language_code, content)

                            # 파일명 생성
                            save_name = f"{phrase_id}_{language_code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
                            filepath = str(language_dir / save_name)

                            # 녹음된 오디오 바이트를 파일로 저장
                            with open(filepath, "wb") as f:
                                if isinstance(audio_bytes, bytes):
                                    f.write(audio_bytes)
                                else:
                                    # UploadedFile 객체인 경우 getbuffer() 사용
                                    f.write(audio_bytes.getbuffer())

                            # 오디오 경로 업데이트
                            db_manager.update_phrase_audio(phrase_id, filepath)

                            st.success(f"멘트가 추가되었고 녹음된 오디오가 저장되었습니다.")

                        # 3. 오디오 없이 멘트만 추가
                        else:
                            # 새 멘트 추가
                            phrase_id = db_manager.add_phrase(group["id"], language_code, content)
                            st.success(f"멘트가 추가되었습니다. 나중에 녹음이나 파일을 추가할 수 있습니다.")

                    # 그룹 삭제
                    if st.button("그룹 삭제", key=f"delete_group_{group['id']}"):
                        db_manager.delete_phrase_group(group["id"])
                        st.success(f"멘트 그룹 '{group['name']}'이(가) 삭제되었습니다.")


def show_conversation_tab():
    st.header("고객 대화")

    # 고객 정보 입력 영역
    st.subheader("고객 정보")
    col1, col2 = st.columns(2)

    # 이전 화면에서 전달된 고객 ID가 있는지 확인
    if "continue_conversation_customer" in st.session_state:
        default_customer_id = st.session_state.continue_conversation_customer
        # 사용 후 상태 초기화
        del st.session_state.continue_conversation_customer
    else:
        default_customer_id = ""

    with col1:
        customer_id = st.text_input("고객 ID", value=default_customer_id)

    # 세션 상태 초기화
    if "conversation" not in st.session_state:
        st.session_state.conversation = []

    if "current_speaker" not in st.session_state:
        st.session_state.current_speaker = "나"

    if "my_translation_language" not in st.session_state:
        st.session_state.my_translation_language = "번역 안함"

    if "customer_translation_language" not in st.session_state:
        st.session_state.customer_translation_language = "번역 안함"

    if "previous_customer_id" not in st.session_state:
        st.session_state.previous_customer_id = None

    # 고객 ID가 변경된 경우 대화 기록 초기화
    if customer_id != st.session_state.previous_customer_id:
        st.session_state.conversation = []
        st.session_state.previous_customer_id = customer_id

    # 고객 ID가 입력되면 기존 대화 기록 확인 및 로드
    if customer_id and not st.session_state.conversation:
        # 오늘 날짜의 해당 고객 대화 기록 확인
        date_str = datetime.now().strftime("%Y-%m-%d")
        conversation_dir = os.path.join("conversations", st.session_state.username, date_str, customer_id)
        conversation_json = os.path.join(conversation_dir, "conversation.json")

        if os.path.exists(conversation_json):
            try:
                with open(conversation_json, "r", encoding="utf-8") as f:
                    st.session_state.conversation = json.load(f)
                st.success(f"기존 대화 기록을 불러왔습니다. ({len(st.session_state.conversation)}개 메시지)")
            except Exception as e:
                st.error(f"대화 기록을 불러오는 중 오류가 발생했습니다: {e}")

    # 화자별 번역 언어 설정
    st.subheader("번역 설정")
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### 내 발화 번역 설정")
        my_translation = st.selectbox(
            "내 발화 번역 언어",
            options=["번역 안함", "한국어 (ko)", "영어 (en)", "일본어 (ja)", "중국어 (zh)"],
            index=0,
            key="my_trans_select",
        )
        st.session_state.my_translation_language = my_translation

    with col2:
        st.markdown("#### 고객 발화 번역 설정")
        customer_translation = st.selectbox(
            "고객 발화 번역 언어",
            options=["번역 안함", "한국어 (ko)", "영어 (en)", "일본어 (ja)", "중국어 (zh)"],
            index=0,
            key="customer_trans_select",
        )
        st.session_state.customer_translation_language = customer_translation

    # 대화 영역 (채팅 인터페이스)
    st.markdown("---")
    st.subheader("대화 내용")

    # 채팅 메시지 컨테이너
    chat_container = st.container()

    with chat_container:
        # 대화 기록 표시
        if st.session_state.conversation:
            for idx, message in enumerate(st.session_state.conversation):
                # 화자에 따라 다른 배경색 적용
                if message["speaker"] == "나":
                    bgcolor = "#E0F7FA"  # 연한 파란색
                    align = "flex-end"
                    text_align = "right"
                else:
                    bgcolor = "#F1F8E9"  # 연한 녹색
                    align = "flex-start"
                    text_align = "left"

                # 메시지 UI 개선
                if message.get("translation", "") != "":
                    st.markdown(
                        f"""
                        <div style="display: flex; justify-content: {align}; margin-bottom: 10px;">
                            <div style="background-color: {bgcolor}; padding: 10px; border-radius: 15px; max-width: 80%; text-align: {text_align};">
                                <strong>{message['speaker']} ({message['timestamp']})</strong><br>
                                <p style="margin: 5px 0;">{message['text']}</p>
                                {f"<p style='margin: 5px 0; font-style: italic; color: #5c6bc0;'>번역: {message.get('translation', '')}</p>" if message.get('translation') else ""}
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                # 오디오 재생 (있는 경우)
                if message.get("audio_path") and os.path.exists(message["audio_path"]):
                    st.audio(message["audio_path"], format="audio/wav")
        else:
            st.info("대화를 시작하세요. 메시지는 여기에 표시됩니다.")

    # 화자 선택 및 입력 영역
    st.markdown("---")
    st.subheader("메시지 입력")

    # 화자 선택
    speaker = st.radio(
        "화자 선택", ["나", "고객"], horizontal=True, index=0 if st.session_state.current_speaker == "나" else 1
    )
    st.session_state.current_speaker = speaker

    # 직접 입력 옵션
    input_method = st.radio("입력 방식", ["음성 녹음", "텍스트 입력"], horizontal=True)

    if input_method == "음성 녹음":
        # 녹음 영역
        st.info("마이크 아이콘을 클릭하여 녹음을 시작하세요.")
        audio_bytes = st.audio_input(f"{speaker} 음성 녹음", key="conversation_recorder")

        # 녹음 처리
        if audio_bytes is not None:
            if not customer_id:
                st.error("고객 ID를 입력해주세요.")
            else:
                # 저장 경로 생성
                date_str = datetime.now().strftime("%Y-%m-%d")
                time_str = datetime.now().strftime("%H%M%S")
                conversation_dir = os.path.join("conversations", st.session_state.username, date_str, customer_id)
                os.makedirs(conversation_dir, exist_ok=True)

                # 파일명 구성 (화자 정보 포함)
                filename = f"{speaker}_{time_str}.wav"
                filepath = os.path.join(conversation_dir, filename)

                # 오디오 바이트를 파일로 저장
                with open(filepath, "wb") as f:
                    if isinstance(audio_bytes, bytes):
                        f.write(audio_bytes)
                    else:
                        # UploadedFile 객체인 경우 getbuffer() 사용
                        f.write(audio_bytes.getbuffer())

                with st.spinner("음성을 텍스트로 변환 중..."):
                    # OpenAI API 확인
                    if not client:
                        st.error("OpenAI API 키가 설정되어 있지 않습니다. 설정 탭에서 API 키를 설정해주세요.")
                        transcription = "STT API가 설정되지 않았습니다."
                    else:
                        try:
                            # OpenAI API를 사용한 STT (새로운 API 버전 사용)
                            with open(filepath, "rb") as audio_file:
                                # 오디오 파일 크기 확인 (25MB 제한)
                                audio_file.seek(0, os.SEEK_END)
                                file_size = audio_file.tell()
                                audio_file.seek(0)

                                if file_size > 25 * 1024 * 1024:
                                    st.error("오디오 파일이 너무 큽니다 (25MB 제한). 더 짧은 녹음을 시도해주세요.")
                                    transcription = "파일 크기 초과로 변환 실패"
                                else:
                                    # 새로운 API 버전 사용
                                    response = client.audio.transcriptions.create(model="whisper-1", file=audio_file)
                                    transcription = response.text

                                    # 텍스트 파일로 저장
                                    text_filepath = os.path.join(conversation_dir, f"{speaker}_{time_str}_text.txt")
                                    with open(text_filepath, "w", encoding="utf-8") as f:
                                        f.write(transcription)
                        except Exception as e:
                            st.error(f"STT 처리 중 오류가 발생했습니다: {e}")
                            transcription = f"STT 오류: {str(e)[:100]}..."

                # 번역 처리
                translation = None
                if speaker == "나":
                    target_language = st.session_state.my_translation_language
                else:
                    target_language = st.session_state.customer_translation_language

                # 언어 코드 추출
                target_lang_code = (
                    target_language.split("(")[-1].split(")")[0].strip() if "(" in target_language else None
                )

                if target_lang_code and target_lang_code != "번역 안함":
                    translation = translate_text(transcription, target_lang_code, conversation_dir, speaker, time_str)

                # 대화 기록에 추가
                message = {
                    "speaker": speaker,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "text": transcription,
                    "audio_path": filepath,
                    "translation": translation,
                }

                st.session_state.conversation.append(message)

                # 대화 내용을 JSON으로 저장
                conversation_json = os.path.join(conversation_dir, "conversation.json")
                with open(conversation_json, "w", encoding="utf-8") as f:
                    json.dump(st.session_state.conversation, f, ensure_ascii=False, indent=2)

                # 화자 자동 전환
                st.session_state.current_speaker = "고객" if speaker == "나" else "나"

                # 페이지 리로드 (대화 표시 업데이트)
                st.rerun()
    else:
        # 텍스트 직접 입력 섹션
        st.subheader("메시지 입력")

        # 화자와 번역 언어 정보 표시
        if speaker == "나":
            target_language = st.session_state.my_translation_language
        else:
            target_language = st.session_state.customer_translation_language

        st.write(f"화자: {speaker} | 번역 언어: {target_language}")

        # TTS 옵션 (폼 외부에 배치)
        use_tts = st.checkbox("번역 결과를 음성으로 변환 (TTS)")

        # TTS 옵션 (체크박스 선택 시에만 표시)
        tts_engine = "gtts"  # 기본값
        voice_option = "nova"
        instructions = "Speak in a natural and conversational tone."

        if use_tts:
            tts_engine = st.radio("TTS 엔진 선택", ["Google TTS (무료)", "OpenAI TTS (유료)"], horizontal=True)

            # OpenAI TTS 선택 시 추가 옵션
            if tts_engine == "OpenAI TTS (유료)":
                col1, col2 = st.columns(2)
                with col1:
                    voice_option = st.selectbox(
                        "음성 선택",
                        ["alloy", "echo", "fable", "onyx", "nova", "shimmer", "ash", "coral", "ballad", "sage"],
                        index=4,  # nova를 기본값으로
                    )

                with col2:
                    show_instructions = st.checkbox("음성 지시사항 편집")

                if show_instructions:
                    instructions = st.text_area(
                        "음성 지시사항",
                        value="Speak in a cheerful and positive tone.",
                        help="음성의 톤, 감정, 속도 등에 대한 지시사항을 입력하세요.",
                    )

        # TTS 엔진 매핑 (선택된 라디오 옵션을 코드 값으로 변환)
        tts_engine_code = "openai" if tts_engine == "OpenAI TTS (유료)" else "gtts"

        # 텍스트 입력 폼 (TTS 옵션과 분리)
        with st.form(key="text_input_form"):
            text_input = st.text_area(f"{speaker} 메시지 입력", height=100)
            submit_text = st.form_submit_button("메시지 전송")

            if submit_text and text_input:
                if not customer_id:
                    st.error("고객 ID를 입력해주세요.")
                else:
                    # 텍스트 메시지 처리
                    process_text_message(
                        text_input,
                        speaker,
                        customer_id,
                        use_tts=use_tts,
                        tts_engine=tts_engine_code,
                        voice_option=voice_option,
                        instructions=instructions,
                    )
                    st.rerun()

    # 대화 관리 버튼들
    st.markdown("---")
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("대화 초기화"):
            st.session_state.conversation = []
            st.success("대화 기록이 초기화되었습니다.")
            st.rerun()

    with col2:
        if st.button("대화 내용 저장"):
            if not customer_id:
                st.error("고객 ID를 입력해주세요.")
            else:
                # 저장 경로 생성
                date_str = datetime.now().strftime("%Y-%m-%d")
                conversation_dir = os.path.join("conversations", st.session_state.username, date_str, customer_id)
                os.makedirs(conversation_dir, exist_ok=True)

                # 파일명 생성
                time_str = datetime.now().strftime("%H%M%S")
                conversation_json = os.path.join(conversation_dir, f"conversation_{time_str}.json")

                # 대화 내용 저장
                with open(conversation_json, "w", encoding="utf-8") as f:
                    json.dump(st.session_state.conversation, f, ensure_ascii=False, indent=2)

                st.success(f"대화 내용이 저장되었습니다: {conversation_json}")

    with col3:
        if st.button("대화 기록 조회"):
            st.session_state.active_tab = 2  # 녹음 기록 탭으로 이동
            st.rerun()


def process_text_message(
    text_input, speaker, customer_id, use_tts=False, tts_engine="gtts", voice_option="nova", instructions=""
):
    """텍스트 메시지를 처리하는 함수"""
    # 저장 경로 생성
    date_str = datetime.now().strftime("%Y-%m-%d")
    time_str = datetime.now().strftime("%H%M%S")
    conversation_dir = os.path.join("conversations", st.session_state.username, date_str, customer_id)
    os.makedirs(conversation_dir, exist_ok=True)

    # 텍스트 파일로 저장
    text_filepath = os.path.join(conversation_dir, f"{speaker}_{time_str}_text.txt")
    with open(text_filepath, "w", encoding="utf-8") as f:
        f.write(text_input)

    # 번역 처리 (화자에 따라 다른 번역 언어 적용)
    translation = None
    if speaker == "나":
        target_language = st.session_state.my_translation_language
    else:
        target_language = st.session_state.customer_translation_language

    # 언어 코드 추출
    target_lang_code = target_language.split("(")[-1].split(")")[0].strip() if "(" in target_language else None

    if target_lang_code and target_lang_code != "번역 안함":
        translation = translate_text(text_input, target_lang_code, conversation_dir, speaker, time_str)

    # TTS 처리 (Text-to-Speech) - 번역된 텍스트에 대해 수행
    audio_path = None
    if use_tts:
        try:
            with st.spinner("텍스트를 음성으로 변환 중..."):
                # 음성 파일 경로 설정
                audio_filename = f"{speaker}_{time_str}_tts_{target_lang_code}.wav"
                audio_path = os.path.join(conversation_dir, audio_filename)

                # 번역된 텍스트가 있으면 그것을 사용, 없으면 원본 텍스트 사용
                tts_text = translation if translation else text_input

                # TTS 엔진 선택에 따라 다른 처리
                if tts_engine == "openai" and client:
                    # OpenAI TTS API 사용
                    try:
                        # 음성 선택 (사용자가 선택한 옵션 사용)
                        with client.audio.speech.with_streaming_response.create(
                            model="gpt-4o-mini-tts",
                            voice=voice_option,
                            input=tts_text,
                            response_format="wav",
                            speed=1.0,
                            # instructions=instructions,
                        ) as response:
                            response.stream_to_file(audio_path)

                        st.success(f"OpenAI TTS로 음성이 생성되었습니다. (음성: {voice_option})")
                    except Exception as openai_err:
                        st.error(f"OpenAI TTS 오류: {openai_err}")
                        audio_path = None
                else:
                    # Google TTS (gTTS) 사용
                    from gtts import gTTS

                    # 언어 코드 매핑 (gTTS에서 사용하는 언어 코드로 변환)
                    gtts_lang_map = {"ko": "ko", "en": "en", "ja": "ja", "zh": "zh-CN"}  # 중국어 간체

                    # 언어 코드가 없거나 매핑되지 않은 경우 기본값 사용
                    gtts_lang = gtts_lang_map.get(target_lang_code, "en")

                    # gTTS로 음성 생성
                    tts = gTTS(text=tts_text, lang=gtts_lang, slow=False)
                    tts.save(audio_path)

                    st.success(f"Google TTS로 음성이 생성되었습니다. (언어: {gtts_lang})")

        except Exception as e:
            st.error(f"TTS 처리 중 오류가 발생했습니다: {e}")
            audio_path = None

    # 대화 기록에 추가
    message = {
        "speaker": speaker,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "text": text_input,
        "audio_path": audio_path,  # TTS로 생성된 오디오 경로
        "translation": translation,
    }

    st.session_state.conversation.append(message)

    # 대화 내용을 JSON으로 저장
    conversation_json = os.path.join(conversation_dir, "conversation.json")
    with open(conversation_json, "w", encoding="utf-8") as f:
        json.dump(st.session_state.conversation, f, ensure_ascii=False, indent=2)

    # 화자 자동 전환
    st.session_state.current_speaker = "고객" if speaker == "나" else "나"


def translate_text(text, target_lang_code, conversation_dir, speaker, time_str):
    """텍스트를 지정된 언어로 번역하는 함수"""
    with st.spinner(f"{LANGUAGE_LABELS.get(target_lang_code, target_lang_code)}로 번역 중..."):
        # OpenAI API가 설정되지 않은 경우
        if not client:
            st.warning("번역을 위한 OpenAI API 키가 설정되어 있지 않습니다.")
            return "번역 API 설정 필요"

        try:
            # 새 OpenAI API 버전 사용 (ChatCompletion 대신 chat.completions 사용)
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": f"당신은 번역가입니다. 다음 텍스트를 {target_lang_code}로 번역하세요.",
                    },
                    {"role": "user", "content": text},
                ],
            )

            # 응답 처리 방식 변경
            translation = response.choices[0].message.content

            # 번역 결과 저장
            translation_filepath = os.path.join(conversation_dir, f"{speaker}_{time_str}_trans_{target_lang_code}.txt")
            with open(translation_filepath, "w", encoding="utf-8") as f:
                f.write(translation)

            return translation

        except Exception as e:
            st.error(f"번역 중 오류가 발생했습니다: {e}")
            # 개발 모드 - 가짜 번역 (예시)
            fake_translations = {
                "ko": "이것은 한국어 번역 예시입니다.",
                "en": "This is an example English translation.",
                "ja": "これは日本語翻訳の例です。",
                "zh": "这是中文翻译示例。",
            }

            st.info("현재 예시 번역을 표시합니다.")
            return fake_translations.get(target_lang_code, "번역 오류 발생")


def show_settings_tab():
    st.header("설정")

    # 기본 스토리지 경로 설정
    st.subheader("저장 경로 설정")
    storage_path = st.text_input("녹음 파일 저장 경로", "recordings")
    if st.button("경로 저장"):
        save_storage_path(storage_path)
        st.success(f"저장 경로가 '{storage_path}'로 설정되었습니다.")

    # API 키 설정
    st.subheader("API 키 설정")
    api_key_input = st.text_input("OpenAI API 키", os.getenv("OPENAI_API_KEY", ""), type="password")
    if st.button("API 키 저장"):
        save_api_key(api_key_input)
        st.success("API 키가 저장되었습니다.")

    # 음성 파일 및 데이터베이스 관리
    st.subheader("데이터베이스 및 음성 파일 관리")

    with st.expander("📋 데이터베이스 관리", expanded=False):
        st.warning("데이터베이스를 초기화하면 기존의 모든 멘트 정보가 삭제되고, 음성 파일을 기준으로 다시 구성됩니다.")
        st.info("이 기능은 데이터베이스와 음성 파일 간 불일치가 있을 때 사용하세요.")

        if st.button("데이터베이스 초기화 및 음성 파일 스캔", key="db_reset"):
            with st.spinner("데이터베이스 초기화 및 음성 파일 스캔 중..."):
                result = db_manager.reinitialize_database_and_scan()
                st.success(
                    f"데이터베이스 초기화 완료! 그룹 {result['groups']}개, 오디오 파일 {result['audio_files']}개 스캔"
                )
                st.toast(f"데이터베이스 초기화 완료")

    with st.expander("🔄 음성 파일 스캔", expanded=False):
        st.info("음성 파일만 다시 스캔하여 데이터베이스에 추가/업데이트합니다. 기존 데이터는 유지됩니다.")

        if st.button("음성 파일 스캔", key="scan_audio"):
            with st.spinner("음성 파일 스캔 중..."):
                result = db_manager.scan_audio_files_and_update_db()
                st.success(
                    f"스캔 완료! {result['scanned']}개 파일 스캔, {result['added']}개 추가, {result['updated']}개 업데이트"
                )
                st.toast(f"음성 파일 스캔 완료")

    # 기본 언어 설정
    default_lang = st.selectbox("기본 언어", ["ko", "ja", "zh", "en"])
    if st.button("기본 언어 저장"):
        save_default_language(default_lang)
        st.success("기본 언어가 저장되었습니다.")


def get_customers():
    base_path = os.path.join("recordings", st.session_state.username)
    if not os.path.exists(base_path):
        return []

    customers = []
    for date_dir in os.listdir(base_path):
        date_path = os.path.join(base_path, date_dir)
        if os.path.isdir(date_path):
            for customer_dir in os.listdir(date_path):
                if os.path.isdir(os.path.join(date_path, customer_dir)):
                    customers.append(customer_dir)
    return list(set(customers))


def get_customer_recordings(customer_id):
    base_path = os.path.join("recordings", st.session_state.username)
    recordings = []

    for date_dir in os.listdir(base_path):
        date_path = os.path.join(base_path, date_dir)
        if not os.path.isdir(date_path):
            continue

        customer_path = os.path.join(date_path, customer_id)
        if not os.path.exists(customer_path):
            continue

        for file in os.listdir(customer_path):
            if file.endswith(".wav"):
                recording_path = os.path.join(customer_path, file)
                time = file.split("_")[1].split(".")[0]

                # STT 결과 가져오기
                stt_path = os.path.join(customer_path, "stt_result.txt")
                stt_text = ""
                if os.path.exists(stt_path):
                    with open(stt_path, "r", encoding="utf-8") as f:
                        stt_text = f.read()

                # 번역 결과 가져오기
                translations = {}
                for lang in ["ja", "zh", "en"]:
                    trans_path = os.path.join(customer_path, f"translated_{lang}.txt")
                    if os.path.exists(trans_path):
                        with open(trans_path, "r", encoding="utf-8") as f:
                            translations[lang] = f.read()

                recordings.append(
                    {
                        "date": date_dir,
                        "time": time,
                        "audio_path": recording_path,
                        "stt_text": stt_text,
                        "translations": translations,
                    }
                )

    return sorted(recordings, key=lambda x: (x["date"], x["time"]), reverse=True)


def save_memo(customer_id, memo):
    memo_path = os.path.join("recordings", st.session_state.username, "memos")
    os.makedirs(memo_path, exist_ok=True)

    with open(os.path.join(memo_path, f"{customer_id}.txt"), "w", encoding="utf-8") as f:
        f.write(memo)


def load_memo(customer_id):
    memo_path = os.path.join("recordings", st.session_state.username, "memos", f"{customer_id}.txt")
    if os.path.exists(memo_path):
        with open(memo_path, "r", encoding="utf-8") as f:
            return f.read()
    return None


def save_api_key(api_key):
    # API 키 암호화하여 저장
    encrypted_key = base64.b64encode(api_key.encode()).decode()
    with open(current_dir / ".env", "r", encoding="utf-8") as f:
        lines = f.readlines()

    with open(current_dir / ".env", "w", encoding="utf-8") as f:
        for line in lines:
            if line.startswith("OPENAI_API_KEY="):
                f.write(f"OPENAI_API_KEY={encrypted_key}\n")
            else:
                f.write(line)


def save_default_language(lang):
    with open(current_dir / ".env", "r", encoding="utf-8") as f:
        lines = f.readlines()

    with open(current_dir / ".env", "w", encoding="utf-8") as f:
        for line in lines:
            if line.startswith("DEFAULT_LANGUAGE="):
                f.write(f"DEFAULT_LANGUAGE={lang}\n")
            else:
                f.write(line)
        if not any(line.startswith("DEFAULT_LANGUAGE=") for line in lines):
            f.write(f"DEFAULT_LANGUAGE={lang}\n")


def save_storage_path(path):
    with open(current_dir / ".env", "r", encoding="utf-8") as f:
        lines = f.readlines()

    with open(current_dir / ".env", "w", encoding="utf-8") as f:
        for line in lines:
            if line.startswith("STORAGE_PATH="):
                f.write(f"STORAGE_PATH={path}\n")
            else:
                f.write(line)
        if not any(line.startswith("STORAGE_PATH=") for line in lines):
            f.write(f"STORAGE_PATH={path}\n")


def filter_customers(customers, customer_search, date_search, language_filter):
    filtered_customers = []

    for customer in customers:
        # 고객명 검색
        if customer_search and customer_search.lower() not in customer.lower():
            continue

        # 날짜 검색
        if date_search:
            date_str = date_search.strftime("%Y-%m-%d")
            customer_path = os.path.join("recordings", st.session_state.username, date_str, customer)
            if not os.path.exists(customer_path):
                continue

        # 언어 필터
        if language_filter:
            has_language = False
            for date_dir in os.listdir(os.path.join("recordings", st.session_state.username)):
                date_path = os.path.join("recordings", st.session_state.username, date_dir)
                if not os.path.isdir(date_path):
                    continue

                customer_path = os.path.join(date_path, customer)
                if not os.path.exists(customer_path):
                    continue

                for lang in language_filter:
                    if lang == "ko":
                        if os.path.exists(os.path.join(customer_path, "stt_result.txt")):
                            has_language = True
                            break
                    else:
                        if os.path.exists(os.path.join(customer_path, f"translated_{lang}.txt")):
                            has_language = True
                            break

                if has_language:
                    break

            if not has_language:
                continue

        filtered_customers.append(customer)

    return filtered_customers


def create_required_directories():
    """필요한 디렉토리 구조 생성"""
    try:
        # 기본 디렉토리들 생성
        base_directories = [
            "audio_files",  # 오디오 파일 저장 디렉토리
            "recordings",  # 녹음 파일 저장 디렉토리
            "conversations",  # 대화 기록 저장 디렉토리
            "logs",  # 로그 파일 저장 디렉토리
            "data",  # 데이터 파일 저장 디렉토리
            "tmp",  # 임시 파일 저장 디렉토리
        ]

        for dir_name in base_directories:
            dir_path = Path(dir_name)
            dir_path.mkdir(exist_ok=True)
            print(f"디렉토리 생성/확인: {dir_path}")

        # 오디오 파일 디렉토리 구조 생성
        audio_dir = Path("audio_files")

        # 그룹 정보 가져오기
        try:
            groups = db_manager.get_phrase_groups()

            # 그룹별 폴더 생성
            for group in groups:
                group_dir = audio_dir / str(group["id"])
                group_dir.mkdir(exist_ok=True)

                # 언어별 폴더 생성
                for lang in ["ko", "en", "ja", "zh"]:
                    lang_dir = group_dir / lang
                    lang_dir.mkdir(exist_ok=True)
        except Exception as e:
            print(f"그룹 폴더 생성 중 오류 발생: {e}")
            # 데이터베이스가 아직 없는 경우를 대비해 기본 그룹 구조 생성
            default_group_id = "1"
            default_group_dir = audio_dir / default_group_id
            default_group_dir.mkdir(exist_ok=True)

            for lang in ["ko", "en", "ja", "zh"]:
                lang_dir = default_group_dir / lang
                lang_dir.mkdir(exist_ok=True)

        # 현재 로그인한 사용자의 디렉토리 생성
        if "username" in st.session_state and st.session_state.username:
            create_user_directories(st.session_state.username)

        # 개발 모드를 위한 기본 사용자 디렉토리 생성
        create_user_directories("admin")

    except Exception as e:
        st.error(f"디렉토리 생성 중 오류가 발생했습니다: {e}")
        print(f"디렉토리 생성 오류: {e}")


def create_user_directories(username):
    """특정 사용자의 디렉토리 구조 생성"""
    try:
        # 녹음 디렉토리
        user_recordings_dir = Path("recordings") / username
        user_recordings_dir.mkdir(exist_ok=True)

        # 대화 디렉토리
        user_conversations_dir = Path("conversations") / username
        user_conversations_dir.mkdir(exist_ok=True)

        # 오늘 날짜의 디렉토리도 미리 생성
        today = datetime.now().strftime("%Y-%m-%d")
        Path(user_recordings_dir / today).mkdir(exist_ok=True)
        Path(user_conversations_dir / today).mkdir(exist_ok=True)

        return True
    except Exception as e:
        print(f"사용자 '{username}'의 디렉토리 생성 중 오류: {e}")
        return False


def show_recording_history_tab():
    st.header("녹음 및 대화 기록")

    # 검색 필터 UI
    st.subheader("검색 필터")

    # 사용 가능한 날짜 목록 가져오기
    available_dates = get_available_dates()
    if not available_dates:
        st.info("저장된 녹음 또는 대화 기록이 없습니다.")
        return

    # 필터 컬럼 구성
    col1, col2, col3 = st.columns(3)

    with col1:
        # 날짜 선택 (드롭다운으로 변경)
        selected_date = st.selectbox("날짜 선택", options=available_dates, format_func=lambda x: x, index=0)

    # 선택된 날짜의 고객 목록 가져오기
    available_customers = get_customers_by_date(selected_date)

    with col2:
        # 고객 선택 (드롭다운으로 변경, '전체' 옵션 추가)
        customer_options = ["전체"] + available_customers
        selected_customer = st.selectbox("고객 ID 선택", options=customer_options, index=0)

        # 실제 필터링에 사용할 고객 ID
        customer_filter = None if selected_customer == "전체" else selected_customer

    with col3:
        record_type = st.selectbox("기록 유형", ["모두", "녹음만", "대화만"], index=0)

    # 날짜별 고객 목록 표시 (요약 정보)
    st.subheader(f"📅 {selected_date}의 기록")

    if available_customers:
        # 고객별 요약 정보 표시
        customer_summary = []
        for customer in available_customers:
            # 각 고객의 녹음 및 대화 개수 계산
            recordings_count = count_recordings_by_customer(selected_date, customer, "recording")
            conversations_count = count_recordings_by_customer(selected_date, customer, "conversation")

            customer_summary.append(
                {"customer_id": customer, "recordings": recordings_count, "conversations": conversations_count}
            )

        # 고객 요약 정보를 테이블로 표시
        if not customer_filter:  # '전체' 선택 시에만 표시
            # 테이블 헤더
            col1, col2, col3 = st.columns([2, 1, 1])
            col1.markdown("**고객 ID**")
            col2.markdown("**녹음 수**")
            col3.markdown("**대화 수**")

            # 테이블 내용
            for summary in customer_summary:
                col1, col2, col3 = st.columns([2, 1, 1])
                col1.write(summary["customer_id"])
                col2.write(summary["recordings"])
                col3.write(summary["conversations"])

            st.markdown("---")

    # 녹음 기록 가져오기
    recordings_data = get_all_recordings(selected_date, customer_filter)

    # 기록 유형으로 필터링
    if record_type == "녹음만":
        recordings_data = [r for r in recordings_data if r.get("type") == "recording"]
    elif record_type == "대화만":
        recordings_data = [r for r in recordings_data if r.get("type") == "conversation"]

    if not recordings_data:
        st.info("검색 조건에 맞는 기록이 없습니다.")
        return

    # 고객별 구분 (필터 적용)
    customers = sorted(list(set([r["customer_id"] for r in recordings_data])))

    for customer in customers:
        with st.expander(f"👤 고객 ID: {customer}", expanded=(len(customers) == 1)):
            # 해당 고객의 녹음 목록
            customer_recordings = [r for r in recordings_data if r["customer_id"] == customer]

            # 시간순 정렬
            customer_recordings.sort(key=lambda x: x["time_str"], reverse=True)

            for idx, recording in enumerate(customer_recordings):
                with st.container():
                    # 녹음과 대화를 구분하여 표시
                    if recording.get("type") == "recording":
                        st.markdown(f"##### 🎙️ 녹음 ({recording['time_str']})")

                        # 녹음 상세 정보
                        col1, col2 = st.columns([2, 1])

                        with col1:
                            if recording.get("phrase_info"):
                                # 멘트 정보 표시
                                phrase_info = recording["phrase_info"]

                                # 그룹 이름 표시 (group_name이 있으면 사용, 없으면 조회)
                                if "group_name" in phrase_info:
                                    group_name = phrase_info["group_name"]
                                else:
                                    group_name = "알 수 없음"
                                    try:
                                        group_data = db_manager.get_phrase_groups(phrase_info.get("group_id"))
                                        if group_data:
                                            group_name = group_data[0]["name"]
                                    except:
                                        pass

                                st.markdown(f"**그룹:** {group_name} (ID: {phrase_info.get('group_id')})")
                                st.markdown(f"**언어:** {phrase_info.get('language', '알 수 없음')}")
                                st.text_area(
                                    "멘트 내용",
                                    phrase_info.get("content", "내용 없음"),
                                    height=80,
                                    key=f"content_{customer}_{idx}",
                                    disabled=True,
                                )
                            else:
                                st.info("이 녹음에 연결된 멘트 정보가 없습니다.")

                        with col2:
                            # 오디오 재생
                            if os.path.exists(recording["audio_path"]):
                                st.audio(recording["audio_path"])
                                st.caption(f"파일명: {os.path.basename(recording['audio_path'])}")
                            else:
                                st.warning("녹음 파일을 찾을 수 없습니다.")

                            # STT 결과 확인 버튼
                            stt_path = os.path.join(
                                os.path.dirname(recording["audio_path"]), f"stt_result_{recording['time_str']}.txt"
                            )
                            if os.path.exists(stt_path):
                                if st.button("STT 결과 보기", key=f"stt_{customer}_{idx}"):
                                    with open(stt_path, "r", encoding="utf-8") as f:
                                        stt_text = f.read()
                                    st.text_area("STT 결과", stt_text, height=80, disabled=True)

                    else:  # 대화인 경우
                        conversation_file = recording.get("conversation_file", "conversation.json")
                        message_count = recording.get("message_count", 0)
                        st.markdown(f"##### 💬 대화 - {message_count}개 메시지")
                        st.caption(f"파일명: {conversation_file}")

                        # 대화 데이터 표시
                        conversation_data = recording.get("conversation_data", [])
                        if conversation_data:
                            # 대화 내용 표시 여부 토글
                            show_conversation = st.checkbox(f"대화 내용 보기", key=f"show_convo_{customer}_{idx}")

                            if show_conversation:
                                conversation_container = st.container()
                                with conversation_container:
                                    for msg_idx, message in enumerate(conversation_data):
                                        # 화자에 따라 다른 배경색 적용
                                        if message["speaker"] == "나":
                                            bgcolor = "#E0F7FA"  # 연한 파란색
                                            align = "flex-end"
                                            text_align = "right"
                                        else:
                                            bgcolor = "#F1F8E9"  # 연한 녹색
                                            align = "flex-start"
                                            text_align = "left"

                                        with st.container():
                                            st.markdown(
                                                f"""
                                            <div style="display: flex; justify-content: {align}; margin-bottom: 10px;">
                                                <div style="background-color: {bgcolor}; padding: 10px; border-radius: 15px; max-width: 80%; text-align: {text_align};">
                                                    <strong>{message['speaker']} ({message['timestamp']})</strong><br>
                                                    <p style="margin: 5px 0;">{message['text']}</p>
                                                    {f"<p style='margin: 5px 0; font-style: italic; color: #5c6bc0;'>번역: {message.get('translation', '')}</p>" if message.get('translation') else ""}
                                                </div>
                                            </div>
                                            """,
                                                unsafe_allow_html=True,
                                            )

                                            # 오디오 재생 (있는 경우)
                                            if message.get("audio_path") and os.path.exists(message["audio_path"]):
                                                st.audio(message["audio_path"])
                        else:
                            st.info("대화 내용이 없습니다.")

                        # 대화 계속하기 버튼
                        if st.button("대화 계속하기", key=f"continue_convo_{customer}_{idx}"):
                            # 대화 탭으로 이동하고 해당 고객 ID 설정
                            st.session_state.active_tab = 3  # 대화 탭 인덱스
                            st.session_state.continue_conversation_customer = customer
                            st.rerun()

                st.markdown("---")


def get_available_dates():
    """사용 가능한 날짜 목록 반환 (녹음과 대화 폴더 모두 확인)"""
    dates = set()

    # 녹음 폴더 확인
    recordings_path = os.path.join("recordings", st.session_state.username)
    if os.path.exists(recordings_path):
        for date_dir in os.listdir(recordings_path):
            date_path = os.path.join(recordings_path, date_dir)
            if os.path.isdir(date_path) and re.match(r"\d{4}-\d{2}-\d{2}", date_dir):
                dates.add(date_dir)

    # 대화 폴더 확인
    conversations_path = os.path.join("conversations", st.session_state.username)
    if os.path.exists(conversations_path):
        for date_dir in os.listdir(conversations_path):
            date_path = os.path.join(conversations_path, date_dir)
            if os.path.isdir(date_path) and re.match(r"\d{4}-\d{2}-\d{2}", date_dir):
                dates.add(date_dir)

    # 날짜 내림차순 정렬
    return sorted(list(dates), reverse=True)


def get_customers_by_date(date):
    """특정 날짜의 고객 목록 반환 (녹음과 대화 폴더 모두 확인)"""
    customers = set()

    # 녹음 폴더 확인
    recordings_date_path = os.path.join("recordings", st.session_state.username, date)
    if os.path.exists(recordings_date_path):
        for customer_dir in os.listdir(recordings_date_path):
            customer_path = os.path.join(recordings_date_path, customer_dir)
            if os.path.isdir(customer_path):
                customers.add(customer_dir)

    # 대화 폴더 확인
    conversations_date_path = os.path.join("conversations", st.session_state.username, date)
    if os.path.exists(conversations_date_path):
        for customer_dir in os.listdir(conversations_date_path):
            customer_path = os.path.join(conversations_date_path, customer_dir)
            if os.path.isdir(customer_path):
                customers.add(customer_dir)

    # 고객 ID 정렬
    return sorted(list(customers))


def count_recordings_by_customer(date, customer, record_type=None):
    """특정 날짜, 특정 고객의 녹음 또는 대화 개수 반환"""
    count = 0

    if record_type == "recording" or record_type is None:
        # 녹음 파일 확인
        recordings_customer_path = os.path.join("recordings", st.session_state.username, date, customer)
        if os.path.exists(recordings_customer_path):
            for file in os.listdir(recordings_customer_path):
                if file.startswith("recording_") and file.endswith(".wav"):
                    count += 1

    if record_type == "conversation" or record_type is None:
        # 대화 파일 확인
        conversations_customer_path = os.path.join("conversations", st.session_state.username, date, customer)
        if os.path.exists(conversations_customer_path):
            conversation_count = 0
            for file in os.listdir(conversations_customer_path):
                if file == "conversation.json" or (file.startswith("conversation_") and file.endswith(".json")):
                    conversation_count += 1
            # 대화 파일은 최소 1개로 카운트
            if conversation_count > 0:
                count += 1

    return count


def get_all_recordings(date_filter=None, customer_filter=None):
    """날짜와 고객 ID로 필터링된 모든 녹음 기록을 가져옵니다."""
    base_path = os.path.join("recordings", st.session_state.username)
    if not os.path.exists(base_path):
        return []

    recordings = []

    # 날짜 디렉토리 순회
    for date_dir in os.listdir(base_path):
        date_path = os.path.join(base_path, date_dir)

        # 디렉토리가 아니거나 날짜 형식이 아닌 경우 스킵
        if not os.path.isdir(date_path) or not re.match(r"\d{4}-\d{2}-\d{2}", date_dir):
            continue

        # 날짜 필터 적용 (date_filter가 문자열임을 가정)
        if date_filter and date_filter != date_dir:
            continue

        # 고객 디렉토리 순회
        for customer_dir in os.listdir(date_path):
            customer_path = os.path.join(date_path, customer_dir)

            # 디렉토리가 아닌 경우 스킵
            if not os.path.isdir(customer_path):
                continue

            # 고객 ID 필터 적용
            if customer_filter and customer_filter.lower() not in customer_dir.lower():
                continue

            # 음성 파일 및 관련 메타데이터 찾기
            for file in os.listdir(customer_path):
                if file.startswith("recording_") and file.endswith(".wav"):
                    recording_path = os.path.join(customer_path, file)
                    time_str = file.replace("recording_", "").replace(".wav", "")

                    # 메타데이터 파일 찾기
                    phrase_info = None
                    phrase_info_path = None
                    for meta_file in os.listdir(customer_path):
                        if meta_file.startswith("phrase_info_") and meta_file.endswith(".json"):
                            if meta_file.replace("phrase_info_", "").replace(".json", "") == time_str:
                                phrase_info_path = os.path.join(customer_path, meta_file)
                                try:
                                    with open(phrase_info_path, "r", encoding="utf-8") as f:
                                        phrase_info = json.load(f)
                                except:
                                    pass
                                break

                    # 녹음 정보 추가
                    recording_info = {
                        "date": date_dir,
                        "customer_id": customer_dir,
                        "time_str": time_str,
                        "audio_path": recording_path,
                        "metadata_path": phrase_info_path,
                        "phrase_info": phrase_info,
                        "type": "recording",
                    }

                    recordings.append(recording_info)

    # 대화 기록도 함께 가져오기
    conversations_path = os.path.join("conversations", st.session_state.username)
    if os.path.exists(conversations_path):
        # 날짜 디렉토리 순회
        for date_dir in os.listdir(conversations_path):
            date_path = os.path.join(conversations_path, date_dir)

            # 디렉토리가 아니거나 날짜 형식이 아닌 경우 스킵
            if not os.path.isdir(date_path) or not re.match(r"\d{4}-\d{2}-\d{2}", date_dir):
                continue

            # 날짜 필터 적용 (date_filter가 문자열임을 가정)
            if date_filter and date_filter != date_dir:
                continue

            # 고객 디렉토리 순회
            for customer_dir in os.listdir(date_path):
                customer_path = os.path.join(date_path, customer_dir)

                # 디렉토리가 아닌 경우 스킵
                if not os.path.isdir(customer_path):
                    continue

                # 고객 ID 필터 적용
                if customer_filter and customer_filter.lower() not in customer_dir.lower():
                    continue

                # 대화 JSON 파일 찾기
                conversation_files = []
                for file in os.listdir(customer_path):
                    if file == "conversation.json" or file.startswith("conversation_") and file.endswith(".json"):
                        conversation_files.append(file)

                # 가장 최신 대화 파일 사용 (없으면 conversation.json)
                conversation_file = "conversation.json"
                if conversation_files:
                    if "conversation.json" in conversation_files:
                        conversation_file = "conversation.json"
                    else:
                        # 파일명 기준 정렬해서 가장 최신 파일 선택
                        conversation_files.sort(reverse=True)
                        conversation_file = conversation_files[0]

                conversation_path = os.path.join(customer_path, conversation_file)
                if os.path.exists(conversation_path):
                    try:
                        with open(conversation_path, "r", encoding="utf-8") as f:
                            conversation_data = json.load(f)

                            # 시간 문자열 추출 시도 (파일명 또는 파일 수정 시간 기반)
                            try:
                                if conversation_file.startswith("conversation_") and conversation_file.endswith(
                                    ".json"
                                ):
                                    # 파일명에서 시간 추출
                                    time_str = conversation_file.replace("conversation_", "").replace(".json", "")
                                else:
                                    # 파일 수정 시간으로 대체
                                    file_mtime = os.path.getmtime(conversation_path)
                                    time_str = datetime.fromtimestamp(file_mtime).strftime("%H%M%S")
                            except:
                                # 예외 발생 시 파일별 구분을 위해 현재 시간 사용하되 마이크로초 포함
                                time_str = datetime.now().strftime("%H%M%S%f")[:8]

                            # 대화 정보 추가
                            recording_info = {
                                "date": date_dir,
                                "customer_id": customer_dir,
                                "time_str": time_str,
                                "conversation_path": conversation_path,
                                "conversation_data": conversation_data,
                                "type": "conversation",
                                "conversation_file": conversation_file,  # 파일명 추가
                                "message_count": len(conversation_data),  # 메시지 수 추가
                            }

                            recordings.append(recording_info)
                    except Exception as e:
                        # 오류 로깅만 하고 애플리케이션 계속 실행
                        logging.warning(f"대화 파일 읽기 오류: {conversation_path} - {str(e)}")
                        pass

    # 날짜 및 시간 기준 내림차순 정렬
    recordings.sort(key=lambda x: (x["date"], x["time_str"]), reverse=True)

    return recordings


if __name__ == "__main__":
    main()
