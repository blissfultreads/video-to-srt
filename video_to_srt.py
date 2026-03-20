#!/usr/bin/env python3
"""비디오 폴더 일괄 SRT 자막 생성기 — OpenAI Whisper 기반"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

import whisper

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".m4v"}


def format_timestamp(seconds: float) -> str:
    """초(float)를 SRT 타임스탬프 형식(HH:MM:SS,mmm)으로 변환한다."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def segments_to_srt(segments: list) -> str:
    """Whisper segments 리스트를 SRT 문자열로 변환한다."""
    lines = []
    for i, seg in enumerate(segments, start=1):
        start = format_timestamp(seg["start"])
        end = format_timestamp(seg["end"])
        text = seg["text"].strip()
        lines.append(f"{i}\n{start} --> {end}\n{text}\n")
    return "\n".join(lines)


def spellcheck_korean(text: str) -> str:
    """hunspell을 사용하여 한국어 맞춤법을 교정한다."""
    words = text.split()
    if not words:
        return text

    input_text = "\n".join(words)
    cmd = ["hunspell", "-d", "ko_KR,en_US", "-a"]
    result = subprocess.run(
        cmd, input=input_text, capture_output=True, text=True,
        env={**__import__("os").environ, "LANG": "ko_KR.UTF-8"},
    )
    if result.returncode != 0:
        return text

    corrections = {}
    lines = result.stdout.strip().split("\n")
    word_idx = 0
    for line in lines:
        if line.startswith("@(#)"):
            continue
        if line == "":
            word_idx += 1
            continue
        if line.startswith("&"):
            # & word count offset: suggestion1, suggestion2, ...
            parts = line.split(":")
            misspelled = line.split()[1]
            suggestions = [s.strip() for s in parts[1].split(",")]
            if suggestions:
                corrections[misspelled] = suggestions[0]

    if not corrections:
        return text

    corrected_words = []
    for w in words:
        corrected_words.append(corrections.get(w, w))
    return " ".join(corrected_words)


def spellcheck_srt(srt_content: str) -> str:
    """SRT 파일 전체의 텍스트 부분에 맞춤법 검사를 적용한다."""
    lines = srt_content.split("\n")
    result_lines = []
    for line in lines:
        # SRT 인덱스 번호나 타임스탬프는 건너뜀
        stripped = line.strip()
        if stripped.isdigit() or "-->" in stripped or stripped == "":
            result_lines.append(line)
        else:
            result_lines.append(spellcheck_korean(line))
    return "\n".join(result_lines)


def detect_mixed_language(text: str) -> bool:
    """텍스트에 한국어와 영어가 혼용되어 있는지 확인한다."""
    has_korean = bool(re.search(r"[가-힣]", text))
    has_english = bool(re.search(r"[a-zA-Z]{2,}", text))
    return has_korean and has_english


def annotate_bilingual(text: str) -> str:
    """영어 단어/구문 뒤에 한국어가 오거나, 한국어 뒤에 영어가 오는 경우 병행 표기한다.
    예: 'machine learning' → 'machine learning(머신 러닝)' 식의 표기는
    Whisper가 이미 한국어 또는 영어로 인식하므로, 영어 단어가 한국어 문장 안에 있을 때
    해당 영어를 괄호로 감싸 표기한다.
    """
    if not detect_mixed_language(text):
        return text

    # 한국어 문맥 속 영어 단어/구문을 찾아 병행 표기
    # 패턴: 한국어 뒤 공백 + 영어 + 공백 한국어/구두점
    def add_parens(match):
        eng = match.group("eng").strip()
        if not eng:
            return match.group(0)
        # 이미 뒤에 괄호가 있으면 건너뜀
        full = match.group(0)
        if f"{eng}(" in full:
            return full
        return full.replace(eng, f"{eng}({eng})")

    result = re.sub(
        r"(?<=[가-힣])\s+(?P<eng>[A-Za-z][A-Za-z\s]*[A-Za-z])\s+(?=[가-힣,.])",
        add_parens,
        text,
    )
    return result


def collect_videos(folder: Path) -> list[Path]:
    """폴더 내 비디오 파일을 재귀 탐색하고, 이미 SRT가 있는 파일은 제외한다."""
    videos = []
    for p in folder.rglob("*"):
        if p.suffix.lower() in VIDEO_EXTENSIONS:
            srt_path = p.with_suffix(".srt")
            if srt_path.exists():
                continue
            videos.append(p)
    videos.sort(key=lambda p: p.name)
    return videos


def main():
    parser = argparse.ArgumentParser(description="비디오 폴더 일괄 SRT 자막 생성기")
    parser.add_argument("folder", nargs="?", default=".", help="비디오 폴더 경로 (기본: 현재 디렉토리)")
    parser.add_argument("--model", default="medium", help="Whisper 모델 (tiny/base/small/medium/large-v3, 기본: medium)")
    parser.add_argument("--device", default="cpu", help="디바이스 (cpu/cuda/mps, 기본: cpu)")
    parser.add_argument("--no-spellcheck", action="store_true", help="맞춤법 검사 건너뛰기")
    args = parser.parse_args()

    folder = Path(args.folder).resolve()
    if not folder.is_dir():
        print(f"오류: '{folder}' 폴더가 존재하지 않습니다.")
        sys.exit(1)

    # hunspell 확인
    if not args.no_spellcheck:
        check = subprocess.run(["hunspell", "-D"], capture_output=True, text=True)
        if check.returncode != 0 and "hunspell" not in check.stderr:
            print("경고: hunspell이 설치되지 않았습니다. 맞춤법 검사를 건너뜁니다.")
            print("설치: brew install hunspell")
            args.no_spellcheck = True

    # 비디오 파일 수집
    videos = collect_videos(folder)
    if not videos:
        print("처리할 비디오 파일이 없습니다. (이미 SRT가 존재하거나 비디오 파일이 없음)")
        sys.exit(0)

    print(f"총 {len(videos)}개 비디오 발견\n")

    # Whisper 모델 로드
    print(f"Whisper '{args.model}' 모델 로딩 중...")
    model = whisper.load_model(args.model, device=args.device)
    print("모델 로딩 완료\n")

    success = 0
    failed = 0
    failed_files = []

    for idx, video_path in enumerate(videos, start=1):
        print(f"[{idx}/{len(videos)}] 처리 중: {video_path.name}")

        try:
            # 음성 인식
            result = model.transcribe(str(video_path), language=None)
            srt_content = segments_to_srt(result["segments"])

            # 영한 병행 표기
            lines = srt_content.split("\n")
            annotated_lines = []
            for line in lines:
                stripped = line.strip()
                if stripped.isdigit() or "-->" in stripped or stripped == "":
                    annotated_lines.append(line)
                else:
                    annotated_lines.append(annotate_bilingual(line))
            srt_content = "\n".join(annotated_lines)

            # 맞춤법 검사
            if not args.no_spellcheck:
                print("  → 맞춤법 검사 중...")
                srt_content = spellcheck_srt(srt_content)

            # SRT 파일 저장
            srt_path = video_path.with_suffix(".srt")
            srt_path.write_text(srt_content, encoding="utf-8")
            print(f"  ✓ 완료: {srt_path.name}")
            success += 1

        except Exception as e:
            print(f"  ✗ 오류 발생: {e}")
            failed += 1
            failed_files.append(video_path.name)

    # 요약
    print(f"\n{'='*40}")
    print(f"처리 완료: 성공 {success} / 실패 {failed} / 전체 {len(videos)}")
    if failed_files:
        print(f"실패 파일: {', '.join(failed_files)}")


if __name__ == "__main__":
    main()
