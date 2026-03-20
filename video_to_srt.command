#!/bin/bash
cd "$(dirname "$0")"
echo "================================"
echo "  비디오 → SRT 자막 생성기"
echo "================================"
echo ""
python3 video_to_srt.py .
echo ""
echo "완료! 아무 키나 누르면 종료됩니다."
read -n 1 -s
