#!/bin/bash
cd "$(dirname "$0")"
echo "================================"
echo "  Video to SRT 웹 서버 시작"
echo "================================"
echo ""
echo "브라우저에서 http://localhost:5050 으로 접속하세요"
echo "종료하려면 Ctrl+C 를 누르세요"
echo ""
open http://localhost:5050
python3 app.py
