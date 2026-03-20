#!/usr/bin/env python3
"""Video to SRT — 웹 기반 자막 생성기"""

import os
import re
import subprocess
import tempfile
import threading
from pathlib import Path

import whisper
from flask import Flask, render_template, request, jsonify, send_file

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024 * 1024  # 2GB

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".m4v"}

# Whisper 모델 (최초 요청 시 로드)
_model = None
_model_lock = threading.Lock()


def get_model():
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                _model = whisper.load_model("medium", device="cpu")
    return _model


def format_timestamp(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def segments_to_srt(segments: list) -> str:
    lines = []
    for i, seg in enumerate(segments, start=1):
        start = format_timestamp(seg["start"])
        end = format_timestamp(seg["end"])
        text = seg["text"].strip()
        lines.append(f"{i}\n{start} --> {end}\n{text}\n")
    return "\n".join(lines)


def spellcheck_korean(text: str) -> str:
    words = text.split()
    if not words:
        return text

    input_text = "\n".join(words)
    cmd = ["hunspell", "-d", "ko_KR,en_US", "-a"]
    try:
        result = subprocess.run(
            cmd, input=input_text, capture_output=True, text=True,
            env={**os.environ, "LANG": "ko_KR.UTF-8"}, timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return text
    if result.returncode != 0:
        return text

    corrections = {}
    for line in result.stdout.strip().split("\n"):
        if line.startswith("&"):
            parts = line.split(":")
            misspelled = line.split()[1]
            suggestions = [s.strip() for s in parts[1].split(",")]
            if suggestions:
                corrections[misspelled] = suggestions[0]

    if not corrections:
        return text
    return " ".join(corrections.get(w, w) for w in words)


def spellcheck_srt(srt_content: str) -> str:
    lines = srt_content.split("\n")
    result_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.isdigit() or "-->" in stripped or stripped == "":
            result_lines.append(line)
        else:
            result_lines.append(spellcheck_korean(line))
    return "\n".join(result_lines)


def detect_mixed_language(text: str) -> bool:
    has_korean = bool(re.search(r"[가-힣]", text))
    has_english = bool(re.search(r"[a-zA-Z]{2,}", text))
    return has_korean and has_english


def annotate_bilingual(text: str) -> str:
    if not detect_mixed_language(text):
        return text

    def add_parens(match):
        eng = match.group("eng").strip()
        if not eng:
            return match.group(0)
        full = match.group(0)
        if f"{eng}(" in full:
            return full
        return full.replace(eng, f"{eng}({eng})")

    return re.sub(
        r"(?<=[가-힣])\s+(?P<eng>[A-Za-z][A-Za-z\s]*[A-Za-z])\s+(?=[가-힣,.])",
        add_parens,
        text,
    )


def process_srt_text(srt_content: str) -> str:
    """병행 표기 + 맞춤법 검사 적용"""
    lines = srt_content.split("\n")
    result_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.isdigit() or "-->" in stripped or stripped == "":
            result_lines.append(line)
        else:
            result_lines.append(annotate_bilingual(line))
    srt_content = "\n".join(result_lines)
    return spellcheck_srt(srt_content)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/transcribe", methods=["POST"])
def transcribe():
    if "file" not in request.files:
        return jsonify({"error": "파일이 없습니다."}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "파일명이 없습니다."}), 400

    ext = Path(file.filename).suffix.lower()
    if ext not in VIDEO_EXTENSIONS:
        return jsonify({"error": f"지원하지 않는 형식입니다: {ext}"}), 400

    # 임시 파일에 저장
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        file.save(tmp)
        tmp_path = tmp.name

    try:
        model = get_model()
        result = model.transcribe(tmp_path, language=None)
        srt_content = segments_to_srt(result["segments"])
        srt_content = process_srt_text(srt_content)

        # SRT 임시 파일 생성
        srt_name = Path(file.filename).stem + ".srt"
        srt_tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".srt", delete=False, encoding="utf-8"
        )
        srt_tmp.write(srt_content)
        srt_tmp.close()

        return send_file(
            srt_tmp.name,
            as_attachment=True,
            download_name=srt_name,
            mimetype="text/plain; charset=utf-8",
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        os.unlink(tmp_path)


if __name__ == "__main__":
    print("=" * 40)
    print("  Video to SRT 웹 서버")
    print("  http://localhost:5050")
    print("=" * 40)
    app.run(host="0.0.0.0", port=5050, debug=False)
