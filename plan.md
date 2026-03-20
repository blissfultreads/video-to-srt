# 비디오 폴더 일괄 SRT 자막 생성기

## Context
지정 폴더 내 모든 비디오 파일을 Whisper로 음성 인식하여 `.srt` 자막 파일을 자동 생성하는 CLI 스크립트를 만든다. 한국어+영어 혼합 환경을 지원한다.

## 환경 확인 (모두 충족됨)
- [x] Python 3.12.0
- [x] ffmpeg (homebrew)
- [x] openai-whisper 20240930

## 구현 계획

### 생성 파일
- `video_to_srt.py` — 단일 메인 스크립트

### 구현 내용 (`video_to_srt.py`)

**1. CLI 인터페이스**
- `argparse`로 폴더 경로를 인자로 받음
- 기본값: 현재 디렉토리 (`.`)
- 선택 옵션: `--model` (기본 `medium`), `--device` (기본 `cpu`)

**2. 비디오 파일 탐색**
- `pathlib.Path.rglob()`으로 `.mp4, .mov, .avi, .mkv, .m4v` 재귀 탐색
- 동일 이름 `.srt` 존재 시 건너뜀

**3. Whisper 모델 로드**
- `whisper.load_model(model, device=device)`
- 모델 1회 로드 후 전체 파일에 재사용

**4. 음성 인식 및 SRT 생성**
- `model.transcribe(str(video_path), language=None)` 호출
- segments에서 `start`, `end`, `text` 추출
- 타임스탬프: `float` → `HH:MM:SS,mmm` 변환 함수
- SRT 형식으로 포맷팅 후 UTF-8로 저장

**5. 진행 상황 및 오류 처리**
- 처리 중 파일명 출력, 진행률 표시 (`[1/10]`)
- 개별 파일 오류 시 `try/except`로 스킵, 계속 진행
- 완료 후 성공/실패/스킵 건수 요약 출력

## 검증
- 생성된 `.srt` 파일이 비디오와 같은 폴더에 존재하는지 확인
- SRT 파일 내용의 타임스탬프 형식 (`HH:MM:SS,mmm --> HH:MM:SS,mmm`) 확인
- VLC에서 비디오+자막 재생하여 싱크 확인
