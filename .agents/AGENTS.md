# Personal Preferences

- **Language:** 한국어 (Korean) - 사용자와의 모든 대화 및 문서 생성은 한국어로 진행합니다.
본 문서는 실운영 서버 환경인 Python 2.7.5 제약 조건하에서 파이썬 신규 및 수정 파이썬 소스 생성 및 구동하기 위한 구조 설계 및 코드 전환 규칙을 정의합니다.

1. Python 2.7.5 환경 핵심 호환성 전환 규칙
Python 3 기반의 sql_v12_full_emrput.py 소스 스타일을 유지하되, 하위 버전 컴파일러에서 에러가 나지 않도록 아래 규칙을 반드시 적용합니다.

① 문자열 포맷팅 전환 (f-string 제거)
Python 3: f"{PROGRAM_NAME}_{last_dir}_{suffix}.csv"

Python 2.7: "{}_{}_{}.csv".format(PROGRAM_NAME, last_dir, suffix) 또는 "%s_%s_%s.csv" % (PROGRAM_NAME, last_dir, suffix) 방식만 사용 가능합니다.

② 타입 힌팅(Type Hinting) 전면 제거
Python 3: def mysql_connect(conf: dict) -> tuple:

Python 2.7: def mysql_connect(conf): (인자 및 반환 값의 타입 선언문은 구문 에러를 유발하므로 전체 제거하고 주석으로 대체합니다.)

③ 파일 입출력 및 인코딩 처리 (open 함수 우회)
Python 2.7의 내장 open() 함수는 encoding 파라미터를 지원하지 않으며, utf-8-sig 처리가 불가능합니다.

대안: 상단에 import codecs를 선언하고, codecs.open(file_path, 'r', encoding='utf-8') 구조로 전환합니다. CSV 저장 시 엑셀 깨짐을 방지하는 BOM 마크는 f.write(codecs.BOM_UTF8)를 파일 오픈 직후 수동 기입합니다.

④ OS 모듈 예외 처리 하위 호환
Python 3: os.makedirs(OUT_DIR, exist_ok=True)

Python 2.7: exist_ok 파라미터가 없습니다. 방어 코드로 분기해야 합니다.

Python
if not os.path.exists(OUT_DIR):
    os.makedirs(OUT_DIR)
2. Unload 소스 구조 정의 (sql_unload_v001.py)
주요 설계 단위
인자 파싱: argparse 모듈은 Python 2.7에서 표준 지원하므로 동일하게 사용하되 f-string 구문만 걷어냅니다.

대용량 파일 대응: 한 번에 수백만 건의 데이터를 메모리에 올릴 경우 OOM(Out of Memory)으로 배치가 뻗게 됩니다. 이를 방지하기 위해 cursor.fetchmany(10000)를 사용하는 룹(Loop) 구조를 유지합니다.

함수 단위 설계 명세
load_mysql_conf(explicit_path=None): ConfigParser.ConfigParser()를 이용하여 mysql.conf 섹션을 파싱합니다. (Python 2는 대소문자 구문 주의)

mysql_connect(conf): 동적 로딩된 드라이버를 통해 커넥션 객체를 리턴합니다.

main(): 하위 sql/ 디렉토리 내의 지정된 .sql을 읽어 실행한 후 out/ 경로에 스트리밍 방식으로 CSV를 생성합니다.

3. Find 소스 구조 정의 (sql_find_v001.py)
주요 설계 단위
메모리 효율화: out/ 하위 CSV 파일의 특정 컬럼 데이터를 읽어 단어 리스트를 메모리에 적재할 때, 중복 제거를 위해 set() 자료형을 활용합니다.

대용량 파일 Line-by-Line 스캔: 대상 소스 코드를 읽을 때 read()나 readlines()를 쓰지 않고, for line in f: 생성자(Generator) 스타일을 사용하여 라인 단위로 스트리밍 탐색합니다.

배치 안정성 (Truncate & Insert Many): 기존 데이터와 꼬이지 않도록 대상 테이블을 TRUNCATE 한 후, 대량 적재를 위해 cursor.executemany()를 사용하여 2,000건 단위 청크(Chunk)로 분할 적재합니다.

함수 단위 설계 명세
build_dynamic_table_name(source_dir): 입력 디렉토리 경로의 최하위 폴더명을 추출하여 sql_find_v001_하위폴더명 형태의 테이블명을 동적 생성합니다.

collect_words_from_csv(out_dir, column_name): out/ 폴더 내 CSV들을 열어 지정된 컬럼명 위치의 단어들을 수집합니다.

scan_source_directory(search_dir, word_set): 소스 라인별 스캔을 수행하며 매칭 정보를 메모리 버퍼에 축적합니다.

db_insert_find_results(match_buffer, mysql_conf, table_name): DROP -> CREATE -> TRUNCATE -> EXECUTEMANY 메커니즘을 순차적으로 수행합니다.

4. 운영 안정성 및 디버깅을 위한 공통 프레임워크 (Python 2.7 필수 패턴)
① Silent Fail 금지 (오류 강제 전파)
오류가 발생했을 때 조용히 넘어가지 않도록 모든 예외 처리 블록의 마지막에는 raise를 수행하거나 sys.exit(1)을 명시하여 스케줄러(Airflow, Crontab 등)가 배치 실패를 즉각 인지할 수 있도록 합니다.

Python
try:
    # 데이터베이스 적재 로직
    cursor.executemany(query, batch)
except Exception, e:  # Python 2.7 예외 구문 스타일 ('as' 대신 ',' 사용 가능하나 호환용)
    sys.stderr.write("[ERROR] DB 적재 실패: %s\n" % str(e))
    raise e
② 디버깅 정보 및 출력문 보완
모든 주요 단계마다 처리 시각과 작업 내용을 표준 출력(print) 및 표준 에러(sys.stderr.write)로 분리 출력하여 로그 추적이 가능하게 만듭니다. 
또한 적재 완료 시 조사한 파일 수, 매칭 행 수, DB 적재 정보(건수, 테이블명)를 요약 리포트로 출력합니다.

5. DB연결방식
Python 2.7에서는 mysql.connector가 설치되지 않아 드라이버를 못 찾는 문제가 발생할수 있으니
Python 3 전용 (configparser, f-string, type hint 등 사용) configparser으로 성공한 케이스가 있으니 configparser사용권장입니다.
