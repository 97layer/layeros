#!/bin/bash
# browser-reload.sh — PostToolUse(Edit|Write) HTML/CSS 수정 시 Puppeteer 리로드 신호
#
# 직접 브라우저를 제어하진 않지만, 에이전트에게 리로드 필요성을 알림.
# 실제 리로드는 visual-validate.js 실행 전 puppeteer_navigate로 처리.
#
# exit 0 = 항상 통과

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('tool_input', {}).get('file_path', ''))
except:
    print('')
" 2>/dev/null)

# HTML 또는 CSS 파일인 경우에만 반응
case "$FILE_PATH" in
  *.html|*.css)
    # website/ 하위 파일인 경우만
    if [[ "$FILE_PATH" == */website/* ]]; then
      echo "━━━ BROWSER RELOAD REQUIRED ━━━"
      echo "수정 파일: ${FILE_PATH##*/website/}"
      echo "→ puppeteer_navigate(현재 URL) 실행 후 visual-validate.js로 검증"
      echo "→ 스크린샷 금지. 숫자로 판단."
      echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    fi
    ;;
esac

exit 0
