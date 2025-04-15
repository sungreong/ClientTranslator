import sqlite3
import os
from pathlib import Path
import shutil


class DatabaseManager:
    """
    데이터베이스 관리 클래스
    멘트 그룹 및 멘트 관리, 오디오 파일 스캔 등의 기능 제공
    """

    def __init__(self, db_name="voiceprogram.db"):
        """
        데이터베이스 관리자 초기화

        Args:
            db_name (str): 데이터베이스 파일명
        """
        self.db_name = db_name
        self.data_dir = Path("data")
        self.data_dir.mkdir(exist_ok=True)
        self.db_path = self.data_dir / self.db_name

        # 데이터베이스 연결 및 테이블 생성
        self._create_tables()

    def _get_connection(self):
        """데이터베이스 연결 가져오기"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _create_tables(self):
        """필요한 테이블 생성"""
        conn = self._get_connection()
        cursor = conn.cursor()

        # 멘트 그룹 테이블
        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS phrase_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        )

        # 멘트 테이블 확인 및 생성
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='phrases'")
        if not cursor.fetchone():
            # 멘트 테이블이 없으면 생성
            cursor.execute(
                """
            CREATE TABLE phrases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                language TEXT NOT NULL,
                content TEXT NOT NULL,
                audio_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (group_id) REFERENCES phrase_groups(id) ON DELETE CASCADE
            )
            """
            )

        conn.commit()
        conn.close()

    def add_phrase_group(self, name, description=""):
        """
        멘트 그룹 추가

        Args:
            name (str): 그룹 이름
            description (str): 그룹 설명

        Returns:
            int: 생성된 그룹 ID
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("INSERT INTO phrase_groups (name, description) VALUES (?, ?)", (name, description))

        group_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return group_id

    def add_phrase(self, group_id, language, content, audio_path=None):
        """
        멘트 추가 - 그룹별로 언어당 하나만 유지

        Args:
            group_id (int): 그룹 ID
            language (str): 언어 코드
            content (str): 멘트 내용
            audio_path (str, optional): 오디오 파일 경로

        Returns:
            int: 생성된 멘트 ID
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # 현재 그룹의 언어 조합 존재 여부 확인
        cursor.execute("SELECT id FROM phrases WHERE group_id = ? AND language = ?", (group_id, language))
        existing = cursor.fetchone()

        if existing:
            # 이미 해당 그룹-언어 멘트가 있으면 업데이트
            phrase_id = existing["id"]
            print(f"[DEBUG] 기존 그룹-언어 멘트 업데이트: 그룹 {group_id}, 언어 {language}, ID {phrase_id}")

            # 내용 업데이트
            cursor.execute("UPDATE phrases SET content = ? WHERE id = ?", (content, phrase_id))

            # 오디오 경로가 있으면 업데이트
            if audio_path:
                cursor.execute("UPDATE phrases SET audio_path = ? WHERE id = ?", (audio_path, phrase_id))
                print(f"[DEBUG] 오디오 경로 업데이트: {audio_path}")
        else:
            # 새 멘트 추가 (ID는 자동 생성)
            cursor.execute(
                "INSERT INTO phrases (group_id, language, content, audio_path) VALUES (?, ?, ?, ?)",
                (group_id, language, content, audio_path),
            )
            phrase_id = cursor.lastrowid
            print(f"[DEBUG] 새 멘트 추가: 그룹 {group_id}, 언어 {language}, ID {phrase_id}")

        conn.commit()
        conn.close()

        print(
            f"[DEBUG] 저장완료: 그룹-언어 조합 ({group_id}-{language}), ID {phrase_id}, 내용: {content}, 오디오: {audio_path}"
        )
        return phrase_id

    def get_phrase_groups(self):
        """
        모든 멘트 그룹 가져오기

        Returns:
            list: 멘트 그룹 목록
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM phrase_groups ORDER BY name")
        groups = cursor.fetchall()

        conn.close()

        return groups

    def get_phrases_by_group(self, group_id):
        """
        그룹 ID로 멘트 가져오기

        Args:
            group_id (int): 그룹 ID

        Returns:
            list: 멘트 목록
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM phrases WHERE group_id = ? ORDER BY language", (group_id,))
        phrases = cursor.fetchall()

        print(f"[DEBUG] 그룹 {group_id} 멘트 조회: {len(phrases)}개 발견")
        for p in phrases:
            if isinstance(p, dict):
                print(
                    f"[DEBUG] 멘트 ID: {p.get('id')}, 언어: {p.get('language')}, 오디오: {p.get('audio_path', 'None')}"
                )
            else:
                print(f"[DEBUG] 멘트(Raw): {p}")

        # 각 phrase 딕셔너리에 audio_path가 None인 경우 빈 문자열로 변환하여 인덱스 에러 방지
        result = []
        for phrase in phrases:
            phrase_dict = dict(phrase)
            if "audio_path" not in phrase_dict or phrase_dict["audio_path"] is None:
                phrase_dict["audio_path"] = ""
                print(f"[DEBUG] audio_path 없음: 멘트 ID {phrase_dict.get('id')}")
            else:
                # 오디오 파일 존재 여부 확인
                if os.path.exists(phrase_dict["audio_path"]):
                    print(f"[DEBUG] 오디오 파일 존재: {phrase_dict['audio_path']}")
                else:
                    print(f"[DEBUG] 오디오 파일 없음: {phrase_dict['audio_path']}")

            result.append(phrase_dict)

        conn.close()

        print(f"[DEBUG] 최종 결과: {len(result)}개 멘트 반환")
        return result

    def search_phrases(self, query, search_type="all"):
        """
        멘트 검색 (간단한 키워드 검색)

        Args:
            query (str): 검색 키워드
            search_type (str): 검색 타입 - "all", "group", "content" 중 하나

        Returns:
            list: 검색 결과 멘트 목록
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # 키워드로 검색
        search_term = f"%{query}%"

        # 검색 타입에 따라 쿼리 분기
        if search_type == "group":
            # 그룹 이름으로만 검색
            cursor.execute(
                """
            SELECT p.*, g.name as group_name
            FROM phrases p
            JOIN phrase_groups g ON p.group_id = g.id
            WHERE g.name LIKE ?
            ORDER BY g.name, p.language
            """,
                (search_term,),
            )
        elif search_type == "content":
            # 멘트 내용으로만 검색
            cursor.execute(
                """
            SELECT p.*, g.name as group_name
            FROM phrases p
            JOIN phrase_groups g ON p.group_id = g.id
            WHERE p.content LIKE ?
            ORDER BY g.name, p.language
            """,
                (search_term,),
            )
        else:
            # 기본: 모든 필드 검색
            cursor.execute(
                """
            SELECT p.*, g.name as group_name
            FROM phrases p
            JOIN phrase_groups g ON p.group_id = g.id
            WHERE p.content LIKE ? OR g.name LIKE ?
            ORDER BY g.name, p.language
            """,
                (search_term, search_term),
            )

        results = cursor.fetchall()
        conn.close()

        return results

    def delete_phrase(self, phrase_id):
        """
        멘트 삭제

        Args:
            phrase_id (int): 멘트 ID
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # 멘트 오디오 파일 경로 확인
        cursor.execute("SELECT audio_path FROM phrases WHERE id = ?", (phrase_id,))
        row = cursor.fetchone()

        if row and row["audio_path"]:
            # 파일이 존재하면 삭제
            try:
                audio_path = row["audio_path"]
                if os.path.exists(audio_path):
                    os.remove(audio_path)
            except Exception as e:
                print(f"오디오 파일 삭제 중 오류: {e}")

        # 멘트 삭제
        cursor.execute("DELETE FROM phrases WHERE id = ?", (phrase_id,))
        conn.commit()
        conn.close()

    def delete_phrase_group(self, group_id):
        """
        멘트 그룹 삭제

        Args:
            group_id (int): 그룹 ID
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # 그룹에 속한 모든 멘트의 오디오 파일 삭제
        cursor.execute("SELECT audio_path FROM phrases WHERE group_id = ?", (group_id,))
        rows = cursor.fetchall()

        for row in rows:
            if row["audio_path"]:
                try:
                    audio_path = row["audio_path"]
                    if os.path.exists(audio_path):
                        os.remove(audio_path)
                except Exception as e:
                    print(f"오디오 파일 삭제 중 오류: {e}")

        # 그룹 및 관련 멘트 삭제 (외래 키 제약조건으로 인해 자동 삭제)
        cursor.execute("DELETE FROM phrase_groups WHERE id = ?", (group_id,))
        conn.commit()
        conn.close()

    def update_phrase(self, phrase_id, content):
        """
        멘트 내용 업데이트

        Args:
            phrase_id (int): 멘트 ID
            content (str): 새 멘트 내용
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("UPDATE phrases SET content = ? WHERE id = ?", (content, phrase_id))
        conn.commit()
        conn.close()

    def update_phrase_group(self, group_id, name, description):
        """
        멘트 그룹 정보 업데이트

        Args:
            group_id (int): 그룹 ID
            name (str): 새 그룹 이름
            description (str): 새 그룹 설명
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE phrase_groups SET name = ?, description = ? WHERE id = ?", (name, description, group_id)
        )
        conn.commit()
        conn.close()

    def update_phrase_audio(self, phrase_id, audio_path):
        """
        멘트 오디오 파일 경로 업데이트

        Args:
            phrase_id (int): 멘트 ID
            audio_path (str): 새 오디오 파일 경로
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # 현재 phrases 테이블에 audio_path 열이 있는지 확인
        cursor.execute("PRAGMA table_info(phrases)")
        columns = cursor.fetchall()

        has_audio_path = any(col["name"] == "audio_path" for col in columns)
        print("업데이트", has_audio_path, audio_path)

        if not has_audio_path:
            # audio_path 열이 없으면 추가
            cursor.execute("ALTER TABLE phrases ADD COLUMN audio_path TEXT")
            conn.commit()

        # 이후 코드 실행
        try:
            # 기존 오디오 파일 경로 확인
            cursor.execute("SELECT audio_path FROM phrases WHERE id = ?", (phrase_id,))
            row = cursor.fetchone()

            if row and row["audio_path"]:
                # 기존 파일이 존재하면 삭제
                try:
                    old_audio_path = row["audio_path"]
                    if os.path.exists(old_audio_path):
                        os.remove(old_audio_path)
                except Exception as e:
                    print(f"기존 오디오 파일 삭제 중 오류: {e}")
        except sqlite3.OperationalError:
            # audio_path 열이 없는 경우에도 계속 진행
            pass

        # 새 오디오 파일 경로 업데이트
        cursor.execute("UPDATE phrases SET audio_path = ? WHERE id = ?", (audio_path, phrase_id))
        conn.commit()
        conn.close()

    def get_phrase(self, phrase_id):
        """
        특정 멘트 정보 가져오기

        Args:
            phrase_id (int): 멘트 ID

        Returns:
            dict: 멘트 정보
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM phrases WHERE id = ?", (phrase_id,))
        phrase = cursor.fetchone()

        conn.close()

        return phrase

    def get_all_phrases(self, audio_only=False):
        """
        모든 멘트 가져오기 (그룹 정보 포함)

        Args:
            audio_only (bool): True인 경우 오디오 파일이 있는 멘트만 반환

        Returns:
            list: 멘트 목록
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # 기본 쿼리
        base_query = """
        SELECT p.*, g.name as group_name
        FROM phrases p
        JOIN phrase_groups g ON p.group_id = g.id
        """

        # 오디오 파일이 있는 멘트만 필터링하는 조건 추가
        if audio_only:
            cursor.execute(
                base_query
                + """
                WHERE p.audio_path IS NOT NULL AND p.audio_path != ''
                ORDER BY g.name, p.language
                """
            )
        else:
            cursor.execute(
                base_query
                + """
                ORDER BY g.name, p.language
                """
            )

        phrases = cursor.fetchall()

        # 각 phrase 딕셔너리에 audio_path가 None인 경우 빈 문자열로 변환하여 인덱스 에러 방지
        result = []
        for phrase in phrases:
            phrase_dict = dict(phrase)
            if "audio_path" not in phrase_dict or phrase_dict["audio_path"] is None:
                phrase_dict["audio_path"] = ""
            result.append(phrase_dict)

        conn.close()

        return result

    def sync_groups_with_folders(self):
        """
        audio_files 폴더 구조와 데이터베이스 그룹을 동기화

        audio_files 폴더 내 숫자 폴더명을 그룹 ID로 사용해 그룹 생성
        """
        # audio_files 폴더 확인
        audio_dir = Path("audio_files")
        if not audio_dir.exists():
            audio_dir.mkdir(exist_ok=True)
            return

        # 데이터베이스 연결
        conn = self._get_connection()
        cursor = conn.cursor()

        # 기존 그룹 확인
        cursor.execute("SELECT id, name FROM phrase_groups")
        existing_groups = {row["id"]: row["name"] for row in cursor.fetchall()}
        print(f"[DEBUG] 기존 그룹: {existing_groups}")

        # 폴더 기반 그룹 업데이트
        for folder in audio_dir.iterdir():
            if folder.is_dir() and folder.name.isdigit():
                group_id = int(folder.name)
                print(f"[DEBUG] 그룹 폴더 발견: {folder.name}")

                # 이미 존재하는 그룹인지 확인
                if group_id in existing_groups:
                    # 이미 존재하면 무시
                    pass
                else:
                    # 새 그룹 생성
                    group_name = f"그룹-{group_id}"
                    description = f"폴더 ID {group_id}에서 자동 생성된 그룹"

                    # ID를 명시하여 그룹 생성
                    cursor.execute(
                        "INSERT INTO phrase_groups (id, name, description) VALUES (?, ?, ?)",
                        (group_id, group_name, description),
                    )
                    print(f"[DEBUG] 새 그룹 생성: ID {group_id}, 이름 {group_name}")

        conn.commit()
        conn.close()

    def scan_audio_files_and_update_db(self):
        """
        오디오 파일을 스캔하고 데이터베이스에 멘트를 추가/업데이트

        audio_files/{group_id}/{language}/ 구조의 폴더를 스캔하여
        발견된 오디오 파일에 해당하는 멘트가 없으면 추가하고,
        있으면 오디오 경로를 업데이트

        Returns:
            dict: 스캔 결과 통계
        """
        audio_base_dir = Path("audio_files")
        if not audio_base_dir.exists():
            print("[DEBUG] audio_files 폴더 없음")
            return

        # 데이터베이스 연결
        conn = self._get_connection()
        cursor = conn.cursor()

        # 우선 모든 그룹과 멘트 정보 가져오기
        cursor.execute("SELECT id, name FROM phrase_groups")
        groups = {row["id"]: row["name"] for row in cursor.fetchall()}
        print(f"[DEBUG] 기존 그룹: {groups}")

        # 그룹-언어 조합별 멘트 정보 가져오기
        group_lang_phrases = {}
        cursor.execute("SELECT id, group_id, language, content, audio_path FROM phrases")
        for row in cursor.fetchall():
            key = f"{row['group_id']}-{row['language']}"
            group_lang_phrases[key] = {"id": row["id"], "content": row["content"], "audio_path": row["audio_path"]}
        print(f"[DEBUG] 기존 그룹-언어 조합: {len(group_lang_phrases)}개")

        # 지원하는 언어 코드
        supported_languages = ["ko", "en", "ja", "zh"]

        # 스캔한 오디오 파일 수
        scanned_count = 0
        added_count = 0
        updated_count = 0

        # 그룹 폴더 스캔
        for group_folder in audio_base_dir.iterdir():
            if not (group_folder.is_dir() and group_folder.name.isdigit()):
                continue

            group_id = int(group_folder.name)
            print(f"[DEBUG] 그룹 폴더 발견: {group_folder.name}")

            # 그룹이 데이터베이스에 없으면 추가
            if group_id not in groups:
                group_name = f"그룹-{group_id}"
                description = f"폴더 {group_id}에서 자동 생성"
                cursor.execute(
                    "INSERT INTO phrase_groups (id, name, description) VALUES (?, ?, ?)",
                    (group_id, group_name, description),
                )
                groups[group_id] = group_name
                print(f"[DEBUG] 새 그룹 생성: ID {group_id}, 이름 {group_name}")

            # 언어 폴더 스캔
            for lang_folder in group_folder.iterdir():
                if not (lang_folder.is_dir() and lang_folder.name in supported_languages):
                    continue

                language = lang_folder.name
                print(f"[DEBUG] 언어 폴더 발견: {language}")

                # 그룹-언어 키 생성
                group_lang_key = f"{group_id}-{language}"

                # 오디오 파일 스캔
                audio_files = list(lang_folder.glob("*.wav"))
                audio_files.extend(lang_folder.glob("*.mp3"))

                if audio_files:
                    # 파일이 여러 개 있는 경우 가장 최신 파일 사용
                    audio_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
                    audio_file = audio_files[0]
                    audio_path = str(audio_file)
                    scanned_count += 1

                    print(f"[DEBUG] 오디오 파일 발견: {audio_path} (총 {len(audio_files)}개 중 최신 파일)")

                    # 그룹-언어 조합에 이미 멘트가 있는지 확인
                    if group_lang_key in group_lang_phrases:
                        # 이미 존재하면 오디오 경로만 업데이트
                        phrase_id = group_lang_phrases[group_lang_key]["id"]
                        old_audio = group_lang_phrases[group_lang_key]["audio_path"]
                        print(f"[DEBUG] 기존 멘트 발견 (ID {phrase_id}): 오디오 {old_audio} → {audio_path}")

                        cursor.execute("UPDATE phrases SET audio_path = ? WHERE id = ?", (audio_path, phrase_id))
                        updated_count += 1
                    else:
                        # 새 멘트 생성
                        content = f"{groups[group_id]} 그룹의 {language} 멘트"
                        cursor.execute(
                            "INSERT INTO phrases (group_id, language, content, audio_path) VALUES (?, ?, ?, ?)",
                            (group_id, language, content, audio_path),
                        )
                        phrase_id = cursor.lastrowid
                        print(
                            f"[DEBUG] 새 멘트 생성: 그룹 {group_id}, 언어 {language}, ID {phrase_id}, 오디오 {audio_path}"
                        )
                        added_count += 1
                elif group_lang_key not in group_lang_phrases:
                    # 오디오 파일은 없지만 해당 그룹-언어 멘트도 없으면 빈 멘트 생성
                    content = f"{groups[group_id]} 그룹의 {language} 멘트"
                    cursor.execute(
                        "INSERT INTO phrases (group_id, language, content, audio_path) VALUES (?, ?, ?, ?)",
                        (group_id, language, content, None),
                    )
                    phrase_id = cursor.lastrowid
                    print(f"[DEBUG] 빈 멘트 생성: 그룹 {group_id}, 언어 {language}, ID {phrase_id}")
                    added_count += 1

        # 커밋 전 확인
        print(f"[DEBUG] 커밋 전 - 스캔: {scanned_count}, 추가: {added_count}, 업데이트: {updated_count}")
        conn.commit()
        conn.close()

        print(f"[DEBUG] 최종 결과 - 스캔: {scanned_count}, 추가: {added_count}, 업데이트: {updated_count}")
        return {"scanned": scanned_count, "added": added_count, "updated": updated_count}

    def create_default_phrases_for_group(self, group_id, group_name=None):
        """
        그룹에 대한 기본 멘트를 모든 지원 언어로 생성

        Args:
            group_id (int): 멘트 그룹 ID
            group_name (str, optional): 그룹 이름. 없으면 DB에서 가져옴

        Returns:
            dict: 생성된 멘트 수
        """
        # 지원하는 언어 목록
        supported_languages = ["ko", "en", "ja", "zh"]

        # 데이터베이스 연결
        conn = self._get_connection()
        cursor = conn.cursor()

        # 그룹 이름 확인
        if not group_name:
            cursor.execute("SELECT name FROM phrase_groups WHERE id = ?", (group_id,))
            row = cursor.fetchone()
            if row:
                group_name = row["name"]
            else:
                group_name = f"그룹-{group_id}"

        # 기본 멘트 템플릿 (언어별로 다른 내용)
        default_templates = {
            "ko": f"{group_name} 관련 기본 멘트입니다 (한국어)",
            "en": f"Default phrase for {group_name} (English)",
            "ja": f"{group_name}に関する基本メッセージです (日本語)",
            "zh": f"关于{group_name}的默认信息 (中文)",
        }

        # 카운터 초기화
        created_count = 0

        # 현재 최대 phrase_id 가져오기
        cursor.execute("SELECT MAX(id) as max_id FROM phrases")
        result = cursor.fetchone()
        next_id = (result["max_id"] or 0) + 1

        # 기존 멘트 데이터 가져오기
        existing_phrases = {}
        cursor.execute("SELECT id, language, content, audio_path FROM phrases WHERE group_id = ?", (group_id,))
        for row in cursor.fetchall():
            existing_phrases[row["language"]] = {
                "id": row["id"],
                "content": row["content"],
                "audio_path": row["audio_path"],
            }

        # 각 언어별로 기본 멘트 생성
        for language in supported_languages:
            # 해당 언어의 멘트가 이미 있는지 확인
            cursor.execute(
                "SELECT COUNT(*) as cnt FROM phrases WHERE group_id = ? AND language = ?", (group_id, language)
            )
            result = cursor.fetchone()

            if result and result["cnt"] == 0:
                # 멘트가 없으면 새로 생성
                # 우선 그룹의 다른 언어 멘트 중 내용이 있으면 그 내용을 기반으로 새 멘트 생성
                content = default_templates.get(language, f"Default phrase for {group_name}")

                # 음성 파일 디렉토리 확인 및 생성
                audio_dir = Path(f"audio_files/{group_id}/{language}")
                audio_dir.mkdir(parents=True, exist_ok=True)

                # 기본 오디오 파일 경로 (실제 파일은 없음)
                audio_path = None

                # 새 멘트 추가
                cursor.execute(
                    "INSERT INTO phrases (id, group_id, language, content, audio_path) VALUES (?, ?, ?, ?, ?)",
                    (next_id, group_id, language, content, audio_path),
                )
                next_id += 1
                created_count += 1
                print(f"[DEBUG] 새 멘트 생성: 그룹 {group_id}, 언어 {language}, 내용 {content}")

        conn.commit()
        conn.close()

        return {"created": created_count}

    def ensure_phrase_exists(self, group_id, language, content=None):
        """
        특정 그룹과 언어에 대한 멘트가 존재하는지 확인하고 없으면 생성

        Args:
            group_id (int): 멘트 그룹 ID
            language (str): 언어 코드 (ko, en, ja, zh)
            content (str, optional): 멘트 내용, 없으면 기본 내용 사용

        Returns:
            int: 생성된 멘트 ID 또는 기존 멘트 ID
        """
        # 데이터베이스 연결
        conn = self._get_connection()
        cursor = conn.cursor()

        # 해당 그룹과 언어에 멘트가 이미 있는지 확인
        cursor.execute("SELECT id FROM phrases WHERE group_id = ? AND language = ? LIMIT 1", (group_id, language))
        row = cursor.fetchone()

        if row:
            # 멘트가 이미 있으면 ID 반환
            phrase_id = row["id"]
            print(f"[DEBUG] 기존 멘트 사용: 그룹 {group_id}, 언어 {language}, ID {phrase_id}")
        else:
            # 멘트가 없으면 새로 생성

            # 그룹 이름 가져오기
            cursor.execute("SELECT name FROM phrase_groups WHERE id = ?", (group_id,))
            group_row = cursor.fetchone()
            group_name = group_row["name"] if group_row else f"그룹-{group_id}"

            # 같은 그룹의 다른 언어 멘트 확인 (내용 참고용)
            cursor.execute(
                "SELECT language, content FROM phrases WHERE group_id = ? AND content IS NOT NULL AND content != ''",
                (group_id,),
            )
            existing_phrases = cursor.fetchall()

            # 기본 내용 설정
            if not content:
                language_labels = {"ko": "한국어", "en": "영어", "ja": "일본어", "zh": "중국어"}

                # 기본 템플릿
                default_templates = {
                    "ko": f"{group_name} 그룹의 한국어 멘트",
                    "en": f"English phrase for {group_name} group",
                    "ja": f"{group_name}グループの日本語メッセージ",
                    "zh": f"{group_name}组的中文信息",
                }

                content = default_templates.get(
                    language, f"{group_name} 그룹의 {language_labels.get(language, language)} 멘트"
                )

            # 다음 ID 가져오기
            cursor.execute("SELECT MAX(id) as max_id FROM phrases")
            result = cursor.fetchone()
            phrase_id = (result["max_id"] or 0) + 1

            # 오디오 디렉토리 확인
            audio_dir = Path(f"audio_files/{group_id}/{language}")
            audio_dir.mkdir(parents=True, exist_ok=True)

            # 새 멘트 추가
            cursor.execute(
                "INSERT INTO phrases (id, group_id, language, content, audio_path) VALUES (?, ?, ?, ?, ?)",
                (phrase_id, group_id, language, content, None),
            )
            print(f"[DEBUG] 새 멘트 생성: 그룹 {group_id}, 언어 {language}, ID {phrase_id}, 내용 {content}")

        conn.commit()
        conn.close()

        return phrase_id

    def reinitialize_database_and_scan(self):
        """
        데이터베이스를 초기화하고 오디오 파일을 다시 스캔하여 멘트를 재구성

        이 함수는 데이터베이스와 파일 시스템 간 불일치가 심한 경우 사용합니다.
        주의: 기존 멘트 내용은 삭제되고, 오디오 파일만 유지됩니다.

        Returns:
            dict: 처리 결과 통계
        """
        print("[INFO] 데이터베이스 초기화 및 재구성 시작...")

        # 데이터베이스 연결
        conn = self._get_connection()
        cursor = conn.cursor()

        # 기존 테이블 내용 모두 삭제
        print("[INFO] 기존 테이블 내용 삭제 중...")
        cursor.execute("DELETE FROM phrases")
        cursor.execute("DELETE FROM phrase_groups")
        conn.commit()

        # 필요한 디렉토리 생성
        audio_dir = Path("audio_files")
        audio_dir.mkdir(exist_ok=True)

        # 폴더 구조 스캔하여 그룹 생성
        print("[INFO] 폴더 구조 스캔 및 그룹 생성 중...")
        created_groups = []

        for group_folder in audio_dir.iterdir():
            if group_folder.is_dir() and group_folder.name.isdigit():
                group_id = int(group_folder.name)
                group_name = f"그룹-{group_id}"
                description = f"폴더 {group_id}에서 자동 생성"

                # 그룹 추가
                cursor.execute(
                    "INSERT INTO phrase_groups (id, name, description) VALUES (?, ?, ?)",
                    (group_id, group_name, description),
                )
                created_groups.append((group_id, group_name))
                print(f"[INFO] 그룹 생성: ID {group_id}, 이름 {group_name}")

        conn.commit()

        # 각 그룹과 언어별로 기본 멘트 생성
        print("[INFO] 기본 멘트 생성 중...")
        supported_languages = ["ko", "en", "ja", "zh"]

        for group_id, group_name in created_groups:
            group_dir = audio_dir / str(group_id)

            # 실제 존재하는 언어 폴더만 처리
            for lang_folder in group_dir.iterdir():
                if lang_folder.is_dir() and lang_folder.name in supported_languages:
                    language = lang_folder.name

                    # 해당 언어의 기본 멘트 생성
                    content = f"{group_name}의 {language} 멘트"
                    phrase_id = self.add_phrase(group_id, language, content)
                    print(f"[INFO] 멘트 생성: 그룹 {group_id}, 언어 {language}, ID {phrase_id}")

        conn.commit()
        conn.close()

        # 오디오 파일 스캔 및 매핑
        print("[INFO] 오디오 파일 스캔 및 매핑 중...")
        result = self.scan_audio_files_and_update_db()

        # 최종 결과 확인
        print(f"[INFO] 데이터베이스 초기화 및 재구성 완료!")
        print(f"[INFO] - 생성된 그룹: {len(created_groups)}개")
        print(f"[INFO] - 스캔된 오디오 파일: {result.get('scanned', 0)}개")
        print(f"[INFO] - 추가된 멘트: {result.get('added', 0)}개")
        print(f"[INFO] - 업데이트된 멘트: {result.get('updated', 0)}개")

        return {
            "groups": len(created_groups),
            "audio_files": result.get("scanned", 0),
            "added_phrases": result.get("added", 0),
            "updated_phrases": result.get("updated", 0),
        }

    def get_group_name(self, group_id):
        """
        그룹 ID로 그룹 이름 가져오기

        Args:
            group_id (int): 그룹 ID

        Returns:
            str: 그룹 이름 (그룹이 없는 경우 빈 문자열 반환)
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM phrase_groups WHERE id = ?", (group_id,))
        result = cursor.fetchone()

        conn.close()

        if result:
            return result["name"]
        else:
            return ""


# 싱글톤 인스턴스 생성을 위한 전역 함수
_db_instance = None


def get_db_manager():
    """
    데이터베이스 관리자의 싱글톤 인스턴스를 가져옴

    Returns:
        DatabaseManager: 데이터베이스 관리자 인스턴스
    """
    global _db_instance
    if _db_instance is None:
        _db_instance = DatabaseManager()
    return _db_instance
