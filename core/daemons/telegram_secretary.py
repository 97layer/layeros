#!/usr/bin/env python3
"""
LAYER OS Telegram Secretary v6 - JARVIS Plus Edition
초고도화된 AI 비서: Deep RAG + Premium UX + Multi-Agent Visibility

Features:
- 🧠 Deep RAG: NotebookLM MCP 직접 연동 (Knowledge Base 심층 검색)
- 💎 Premium UX: 절제된 포맷팅 및 에이전트 상태 리포팅
- 🎥 YouTube Pro: 자동 분석 + 오디오 개요 + 마인드맵 생성
- 🤖 Auto-Pilot: 인사이트 자동 분류 및 에이전트 워크플로우 트리거
"""

import os
import sys
import re
import logging
import json
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime
import asyncio

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / '.env')
except ImportError:
    pass

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, constants
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)

# Core Components
from core.system.notebooklm_bridge import get_bridge
from core.system.conversation_engine import get_conversation_engine
from core.system.intent_classifier import get_intent_classifier
from core.system.youtube_analyzer import YouTubeAnalyzer
from core.system.image_analyzer import ImageAnalyzer
from core.system.bot_templates import (
    DAILY_BRIEFING, DAILY_BRIEFING_RIPE, DAILY_BRIEFING_IDLE,
    PUBLISH_COMPLETE,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def _append_decision_log_direct(record: Dict) -> None:
    log_path = PROJECT_ROOT / 'knowledge' / 'system' / 'decision_log.jsonl'
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        if 'ts' not in record:
            record['ts'] = datetime.now().isoformat()
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
    except Exception as e:
        logger.warning("decision_log append 실패: %s", e)


def _escape_html(text: str) -> str:
    """Telegram HTML 모드용 이스케이프"""
    return (text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;'))


_TG_MAX = 4000  # Telegram 4096자 한도 — 여유분 확보


def _tg(text: str, max_len: int = _TG_MAX) -> str:
    """Telegram 메시지 길이 제한. 초과 시 말미 잘라냄."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "\n…[잘림]"


def admin_only(func):
    """ADMIN_TELEGRAM_ID만 커맨드 실행 가능"""
    async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        admin_id = os.getenv('ADMIN_TELEGRAM_ID')
        if admin_id and str(update.effective_user.id) != str(admin_id):
            await update.message.reply_text("권한 없음")
            return
        return await func(self, update, context)
    wrapper.__name__ = func.__name__
    return wrapper


class TelegramSecretaryV6:
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.notebooklm = get_bridge()
        self.engine = get_conversation_engine()
        self.classifier = get_intent_classifier()
        self.youtube = YouTubeAnalyzer()
        self.image = ImageAnalyzer()

        # Gardener (선택적 — 없어도 봇 동작)
        try:
            from core.agents.gardener import Gardener
            self.gardener = Gardener()
        except Exception as e:
            self.gardener = None
            logger.warning("Gardener 비활성: %s", e)

        # Code Agent + ProposeGate (선택적 — 없어도 봇 동작)
        try:
            from core.agents.code_agent import CodeAgent
            from core.system.propose_gate import ProposeGate
            self.code_agent = CodeAgent()
            self.propose_gate = ProposeGate()
        except Exception as e:
            self.code_agent = None
            self.propose_gate = None
            logger.warning("Code Agent 비활성: %s", e)

        # UI Settings
        self.loading_emojis = ["🔘", "⚪", "⚫"]

        logger.info("✅ Telegram Secretary V6 (JARVIS Plus) initialized")

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        welcome_msg = (
            f"<b>LAYER OS</b>\n\n"
            f"안녕하세요, {_escape_html(user.first_name)}님.\n\n"
            f"<b>명령어</b>\n"
            f"/status — 파이프라인 현황\n"
            f"/publish — 콘텐츠 즉시 발행\n"
            f"/publish [테마] — 테마 지정 발행\n"
            f"/report — 오늘 처리 요약\n"
            f"/growth [YYYY-MM] — 성장 지표\n"
            f"/signal [텍스트] — 신호 직접 투입\n"
            f"/note [제목] [내용] — 텍스트 메모 저장 (분석 없음)\n"
            f"/client list|add|info|due — 고객 관리\n"
            f"/visit <이름> <서비스> [만족도] — 방문 기록\n"
            f"/pending — 가드너 제안 목록\n\n"
            f"<b>자동 처리</b>\n"
            f"텍스트 → 신호 수집\n"
            f"YouTube 링크 → 영상 분석\n"
            f"이미지 → 브랜드 인사이트 추출"
        )
        await update.message.reply_text(welcome_msg, parse_mode=constants.ParseMode.HTML)

    @admin_only
    async def growth_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """월별 성장 지표 리포트 (Growth Module + 시스템 현황)"""
        from core.system.growth import get_growth_module

        # 기간 인자 파싱
        period = context.args[0] if context.args else datetime.now().strftime('%Y-%m')

        try:
            gm = get_growth_module()
            gm.auto_count_content(period)
            gm.auto_count_service(period)
            data = gm.get_month(period)

            revenue = data.get('revenue', {})
            content = data.get('content', {})
            service = data.get('service', {})

            # 시스템 현황 (누적)
            signals_dir = PROJECT_ROOT / 'knowledge' / 'signals'
            total_signals = len(list(signals_dir.glob('**/*.json'))) if signals_dir.exists() else 0

            msg = (
                f"<b>📈 Growth Report — {_escape_html(period)}</b>\n\n"
                f"<b>수익</b>\n"
                f"아틀리에: {revenue.get('atelier', 0):,}원\n"
                f"컨설팅: {revenue.get('consulting', 0):,}원\n"
                f"제품: {revenue.get('products', 0):,}원\n"
                f"합계: <b>{revenue.get('total', 0):,}원</b>\n\n"
                f"<b>콘텐츠</b>\n"
                f"신호 수집: {content.get('signals_captured', 0)}건\n"
                f"발행 에세이: {content.get('essays_published', 0)}개\n"
                f"성숙 군집: {content.get('clusters_ripe', 0)}개\n\n"
                f"<b>서비스</b>\n"
                f"총 방문: {service.get('total_visits', 0)}건\n"
                f"신규 고객: {service.get('new_clients', 0)}명\n"
                f"재방문 고객: {service.get('returning_clients', 0)}명\n\n"
                f"<b>시스템 누적</b>\n"
                f"전체 신호: {total_signals}개"
            )
            await update.message.reply_text(msg, parse_mode=constants.ParseMode.HTML)

        except Exception as e:
            logger.error("growth_command error: %s", e)
            await update.message.reply_text("지표 조회 중 오류가 발생했습니다.")

    @admin_only
    async def client_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Ritual Module 고객 관리 (/client list|add|info|due)"""
        from core.system.ritual import get_ritual_module

        args = context.args
        subcmd = args[0] if args else 'list'

        try:
            rm = get_ritual_module()

            if subcmd == 'list':
                clients = rm.list_clients()
                if not clients:
                    await update.message.reply_text("등록된 고객 없음")
                    return
                lines = ["<b>고객 목록</b>\n"]
                for c in clients:
                    visits = len(c.get('visits', []))
                    lines.append(
                        f"{_escape_html(c['client_id'])} | {_escape_html(c['name'])} | "
                        f"방문 {visits}회 | 리듬: {_escape_html(c.get('rhythm', '보통'))}"
                    )
                await update.message.reply_text('\n'.join(lines), parse_mode=constants.ParseMode.HTML)

            elif subcmd == 'add':
                if len(args) < 2:
                    await update.message.reply_text("사용법: /client add <이름> [전화번호]")
                    return
                name = args[1]
                phone = args[2] if len(args) > 2 else ""
                client = rm.create_client(name, phone=phone)
                base = os.getenv('SITE_BASE_URL', 'http://136.109.201.201')
                token = client['portal_token']
                msg = (
                    f"✅ <b>{_escape_html(name)}</b> 등록완료\n"
                    f"ID: {_escape_html(client['client_id'])}\n"
                    + (f"연락처: {_escape_html(phone)}\n" if phone else "")
                    + f"\n📋 사전상담 링크 (방문 전 전송):\n"
                    f"{base}/consult/{token}\n"
                    f"\n📁 시술일지 링크:\n"
                    f"{base}/me/{token}"
                )
                await update.message.reply_text(msg, parse_mode=constants.ParseMode.HTML)

            elif subcmd == 'link':
                if len(args) < 2:
                    await update.message.reply_text("사용법: /client link <이름>")
                    return
                name = args[1]
                client = rm.find_client(name)
                if not client:
                    await update.message.reply_text("고객을 찾을 수 없음")
                    return
                base = os.getenv('SITE_BASE_URL', 'http://136.109.201.201')
                token = client.get('portal_token', '')
                if not token:
                    await update.message.reply_text("portal_token 없음. 재등록 필요.")
                    return
                msg = (
                    f"<b>{_escape_html(client['name'])}</b>\n"
                    f"\n📋 사전상담:\n{base}/consult/{token}\n"
                    f"\n📁 시술일지:\n{base}/me/{token}"
                )
                await update.message.reply_text(msg, parse_mode=constants.ParseMode.HTML)

            elif subcmd == 'info':
                if len(args) < 2:
                    await update.message.reply_text("사용법: /client info <이름>")
                    return
                name = args[1]
                client = rm.find_client(name)
                if not client:
                    await update.message.reply_text("고객을 찾을 수 없음")
                    return
                revisit = rm.check_revisit_due(client['client_id'])
                visits = client.get('visits', [])
                last_visit = client.get('last_visit') or '없음'
                due_text = f"⚠️ 재방문 필요 ({revisit['days_since']}일 경과)" if revisit.get('due') else "정상"
                msg = (
                    f"<b>{_escape_html(client['name'])}</b>\n"
                    f"ID: {_escape_html(client['client_id'])}\n"
                    f"모발: {_escape_html(client.get('hair_type', '미기입'))}\n"
                    f"리듬: {_escape_html(client.get('rhythm', '보통'))}\n"
                    f"방문: {len(visits)}회 | 마지막: {_escape_html(last_visit)}\n"
                    f"재방문: {_escape_html(due_text)}"
                )
                await update.message.reply_text(msg, parse_mode=constants.ParseMode.HTML)

            elif subcmd == 'due':
                due_list = rm.get_due_clients()
                if not due_list:
                    await update.message.reply_text("재방문 대상 없음")
                    return
                lines = ["<b>재방문 대상</b>\n"]
                for d in due_list:
                    lines.append(
                        f"{_escape_html(d['client_name'])} | {d['days_since']}일 경과 | "
                        f"임계값: {d['threshold']}일"
                    )
                await update.message.reply_text('\n'.join(lines), parse_mode=constants.ParseMode.HTML)

            else:
                await update.message.reply_text(
                    "사용법: /client list | add <이름> | info <이름> | due"
                )

        except Exception as e:
            logger.error("client_command error: %s", e)
            await update.message.reply_text("고객 조회 중 오류가 발생했습니다.")

    @admin_only
    async def visit_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """방문 기록 (/visit <이름> <서비스> [만족도])"""
        from core.system.ritual import get_ritual_module

        args = context.args
        if len(args) < 2:
            await update.message.reply_text("사용법: /visit <이름> <서비스> [만족도(1-5)]")
            return

        name = args[0]
        service = args[1]
        satisfaction = None
        if len(args) >= 3:
            try:
                satisfaction = int(args[2])
            except ValueError:
                pass

        try:
            rm = get_ritual_module()
            client = rm.find_client(name)
            if not client:
                await update.message.reply_text(f"고객 없음: {_escape_html(name)}")
                return

            visit = rm.add_visit(
                client['client_id'],
                service=service,
                satisfaction=satisfaction,
            )
            sat_text = f" | 만족도: {satisfaction}/5" if satisfaction else ""
            msg = (
                f"✅ 방문 기록\n"
                f"{_escape_html(client['name'])} | {_escape_html(service)}"
                f"{_escape_html(sat_text)}\n"
                f"날짜: {_escape_html(visit['date'])}"
            )
            await update.message.reply_text(msg)

        except Exception as e:
            logger.error("visit_command error: %s", e)
            await update.message.reply_text("방문 기록 중 오류가 발생했습니다.")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = update.message
        if not message.text and not message.photo and not message.document:
            return

        # 1. YouTube 전역 감지
        youtube_match = re.search(r'(https?://(?:www\.)?(youtube\.com|youtu\.be)/[\w-]+)', message.text or '')
        if youtube_match:
            await self.process_youtube(update, context, youtube_match.group(1))
            return

        # 2. 이미지 처리
        if message.photo:
            await self.process_image(update, context)
            return

        # 3. PDF 문서 처리
        if message.document:
            await self.process_document(update, context)
            return

        # 4. Code Agent 패턴 감지 (콘텐츠 파이프라인 앞에서 처리)
        if self.code_agent and await self._try_code_routing(update, context):
            return

        # 5. 텍스트 의도 분석 및 처리
        await self.process_text(update, context)

    async def process_youtube(self, update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
        status_msg = await update.message.reply_text(
            "🛸 YouTube 분석 중...",
            parse_mode=constants.ParseMode.HTML
        )

        try:
            # 1. 자막 수집 + Gemini 분석 + 로컬 JSON 저장
            await status_msg.edit_text("🛸 <code>Step 1/2</code>: 영상 자막 수집 중...", parse_mode=constants.ParseMode.HTML)
            result = self.youtube.process_url(url, source_channel="telegram")

            if not result['success']:
                await status_msg.edit_text(
                    f"❌ 분석 실패: {_escape_html(str(result.get('error', '')))}",
                    parse_mode=constants.ParseMode.HTML
                )
                return

            video_id = result['video_id']
            transcript_len = len(result.get('transcript', ''))
            analysis = result.get('analysis', {})

            # 2. NotebookLM 저장 시도 (실패해도 전체 흐름 중단 안 함)
            nlm_saved = False
            if self.notebooklm and self.notebooklm.authenticated:
                await status_msg.edit_text("🛸 <code>Step 2/2</code>: NotebookLM 저장 중...", parse_mode=constants.ParseMode.HTML)
                try:
                    content_text = (
                        f"YouTube: {url}\n"
                        f"Video ID: {video_id}\n\n"
                        f"분석:\n{json.dumps(analysis, ensure_ascii=False, indent=2)}\n\n"
                        f"자막 요약:\n{result.get('transcript', '')[:3000]}"
                    )
                    nb_id = self.notebooklm.get_or_create_notebook("LAYER OS: Signal Archive")
                    title = f"[YouTube] {analysis.get('title', video_id)[:60]}"
                    self.notebooklm.add_source_text(nb_id, content_text, title)
                    nlm_saved = True
                except Exception as nlm_e:
                    logger.warning("NotebookLM 저장 실패: %s", nlm_e)

            # 결과 메시지 — 실제 완료된 것만 표시
            lines = [f"✅ <b>YouTube 분석 완료</b>", ""]
            lines.append(f"ID: <code>{_escape_html(video_id)}</code>")
            lines.append(f"자막: {transcript_len}자 수집")
            lines.append(f"로컬 저장: ✅")
            lines.append(f"NotebookLM: {'✅ 저장됨' if nlm_saved else '⚠️ 저장 실패 (로컬만)'}")

            await status_msg.edit_text("\n".join(lines), parse_mode=constants.ParseMode.HTML)

        except Exception as e:
            logger.error("YouTube processing error: %s", e)
            try:
                await status_msg.edit_text(f"❌ 시스템 오류: {_escape_html(str(e))}", parse_mode=constants.ParseMode.HTML)
            except Exception:
                pass

    async def process_image(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """이미지 처리 — 통합 스키마로 signals/ 저장 + SA 큐 전달"""
        caption = update.message.caption or ""
        status_msg = await update.message.reply_text("🖼️ 이미지 분석 중...")
        try:
            photo = update.message.photo[-1]
            file = await context.bot.get_file(photo.file_id)
            import tempfile
            import shutil
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                tmp_path = tmp.name
                await file.download_to_drive(tmp_path)

            # Gemini Vision 분석
            result = self.image.analyze_image(tmp_path)

            # 통합 스키마로 저장
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            signal_id = "image_%s" % timestamp
            files_dir = PROJECT_ROOT / 'knowledge' / 'signals' / 'files'
            files_dir.mkdir(parents=True, exist_ok=True)

            # 바이너리 복사
            dest_path = files_dir / ("%s.jpg" % signal_id)
            shutil.copy2(tmp_path, dest_path)
            os.unlink(tmp_path)

            # 통합 신호 JSON
            description = result.get('full_analysis') or result.get('description', '')
            content = description[:3000]
            if caption:
                content = "[메모] %s\n\n%s" % (caption, content)

            signal_data = {
                'signal_id': signal_id,
                'type': 'image',
                'status': 'captured',
                'content': content,
                'captured_at': datetime.now().isoformat(),
                'from_user': update.effective_user.username or update.effective_user.first_name,
                'source_channel': 'telegram',
                'metadata': {
                    'image_path': str(dest_path),
                    'title': caption[:100] if caption else 'telegram_image',
                },
            }

            _, queue_ok = self._save_signal(signal_data)
            if not queue_ok:
                logger.warning("SA 큐 전달 실패 (이미지): %s", signal_id)

            # 응답
            if description and '분석 실패' not in description:
                combined = description
                if caption:
                    combined = "📝 **메모**: %s\n\n%s" % (caption, description)
                if len(combined) > 4000:
                    combined = combined[:4000] + "\n\n..."
                await status_msg.edit_text(combined)
            else:
                err = result.get('description', '알 수 없는 오류')
                await status_msg.edit_text(
                    "❌ 이미지 분석 실패: %s" % _escape_html(err),
                    parse_mode=constants.ParseMode.HTML
                )

        except Exception as e:
            logger.error("Image processing error: %s", e)
            try:
                await status_msg.edit_text(
                    "❌ 이미지 처리 오류: %s" % _escape_html(str(e)),
                    parse_mode=constants.ParseMode.HTML
                )
            except Exception:
                pass

    async def process_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """PDF/문서 처리 — 통합 스키마로 signals/ 저장 + SA 큐 전달"""
        doc = update.message.document
        file_name = doc.file_name or "unknown"
        mime = doc.mime_type or ""

        # PDF만 지원
        if not (mime == "application/pdf" or file_name.lower().endswith(".pdf")):
            await update.message.reply_text(
                "현재 PDF 파일만 지원합니다. (%s)" % _escape_html(file_name),
                parse_mode=constants.ParseMode.HTML,
            )
            return

        status_msg = await update.message.reply_text("📄 PDF 수집 중...")
        try:
            import tempfile
            import shutil

            file = await context.bot.get_file(doc.file_id)
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp_path = tmp.name
                await file.download_to_drive(tmp_path)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            signal_id = "pdf_document_%s" % timestamp

            # 바이너리 복사
            files_dir = PROJECT_ROOT / "knowledge" / "signals" / "files"
            files_dir.mkdir(parents=True, exist_ok=True)
            dest_path = files_dir / ("%s.pdf" % signal_id)
            shutil.copy2(tmp_path, dest_path)

            # 텍스트 추출 시도
            content = "PDF 수집: %s" % file_name
            pages_extracted = 0
            try:
                import pdfplumber
                with pdfplumber.open(tmp_path) as pdf:
                    pages_text = []
                    for page in pdf.pages[:10]:
                        text = page.extract_text()
                        if text:
                            pages_text.append(text)
                    if pages_text:
                        content = "\n".join(pages_text)[:3000]
                        pages_extracted = len(pages_text)
            except ImportError:
                logger.info("pdfplumber 미설치 — 텍스트 추출 생략")
            except Exception as pdf_e:
                logger.warning("PDF 추출 실패: %s", pdf_e)

            os.unlink(tmp_path)

            # 통합 신호 JSON
            signal_data = {
                "signal_id": signal_id,
                "type": "pdf_document",
                "status": "captured",
                "content": content,
                "captured_at": datetime.now().isoformat(),
                "from_user": update.effective_user.username or update.effective_user.first_name,
                "source_channel": "telegram",
                "metadata": {
                    "pdf_path": str(dest_path),
                    "title": Path(file_name).stem,
                },
            }

            self._save_signal(signal_data)

            extract_info = ""
            if pages_extracted:
                extract_info = "\n텍스트 추출: %d페이지, %d자" % (pages_extracted, len(content))
            await status_msg.edit_text(
                "📄 <b>PDF 수집 완료</b>\n\n"
                "파일: %s%s\n"
                "SA 분석 큐 전달됨." % (_escape_html(file_name), extract_info),
                parse_mode=constants.ParseMode.HTML,
            )

        except Exception as e:
            logger.error("Document processing error: %s", e)
            try:
                await status_msg.edit_text(
                    "❌ PDF 처리 오류: %s" % _escape_html(str(e)),
                    parse_mode=constants.ParseMode.HTML,
                )
            except Exception:
                pass

    # ── Code Agent 라우팅 ────────────────────────────────────────────────────

    CODE_PATTERNS = ("/code", "fix:", "feat:", "bug:", "수정:", "고쳐", "refactor:")

    async def _try_code_routing(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> bool:
        """
        코드 관련 패턴이면 Code Agent로 라우팅.
        PROPOSE 응답(reply)이면 ProposeGate.confirm으로 처리.
        Returns True이면 다음 핸들러 스킵.
        """
        message = update.message
        text = message.text or ""
        chat_id = message.chat_id

        # 1. PROPOSE 응답 처리 — reply 없이 단독 ok/no도 처리
        if self.propose_gate:
            from core.system.propose_gate import CONFIRM_WORDS, REJECT_WORDS
            normalized = text.strip().lower()
            is_confirm_word = normalized in CONFIRM_WORDS or normalized in REJECT_WORDS

            pending = None
            if message.reply_to_message:
                reply_msg_id = message.reply_to_message.message_id
                pending = self.propose_gate.find_pending_by_reply(reply_msg_id)
            if not pending and is_confirm_word:
                # 단독 ok/no — 최근 pending으로 fallback
                pending = self.propose_gate.find_latest_pending(chat_id)

            if pending and is_confirm_word:
                result = self.propose_gate.confirm(text, pending["task_id"])
                if result == "approved":
                    task_type = pending.get("callback_data", {}).get("type", "code")
                    if task_type == "restart":
                        await self.code_agent.confirm_restart(
                            pending["task_id"],
                            lambda t: message.reply_text(t, parse_mode="HTML"),
                        )
                    else:
                        await self.code_agent.apply_confirmed(
                            pending["task_id"],
                            lambda t: message.reply_text(t, parse_mode="HTML"),
                        )
                    return True
                if result == "rejected":
                    await message.reply_text("❌ 폐기됨")
                    return True
                # unknown — 일반 대화로 넘김
                return False

        # 2. 코드 패턴 감지
        lower = text.lower().strip()
        if not any(lower.startswith(p.lower()) for p in self.CODE_PATTERNS):
            return False

        # admin만 Code Agent 사용 가능
        admin_id = os.getenv("ADMIN_TELEGRAM_ID")
        if admin_id and str(update.effective_user.id) != str(admin_id):
            await message.reply_text("권한 없음")
            return True

        # Code Agent 처리
        async def send_fn(text_: str):
            return await message.reply_text(text_, parse_mode="HTML")

        instruction = text
        for prefix in self.CODE_PATTERNS:
            if instruction.lower().startswith(prefix.lower()):
                instruction = instruction[len(prefix):].strip()
                break

        await self.code_agent.handle_task(instruction, chat_id, send_fn)
        return True

    # ── 텍스트 처리 ──────────────────────────────────────────────────────────

    @staticmethod
    def _fetch_url_content(url: str) -> dict:
        """
        URL 페이지 본문 추출.
        Returns: {"title": str, "content": str, "ok": bool}
        """
        try:
            import urllib.request
            from html.parser import HTMLParser

            class _Extractor(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self._title = []
                    self._body = []
                    self._in_title = False
                    self._skip = False

                def handle_starttag(self, tag, attrs):
                    if tag == 'title':
                        self._in_title = True
                    if tag in ('script', 'style', 'nav', 'header', 'footer', 'aside'):
                        self._skip = True

                def handle_endtag(self, tag):
                    if tag == 'title':
                        self._in_title = False
                    if tag in ('script', 'style', 'nav', 'header', 'footer', 'aside'):
                        self._skip = False

                def handle_data(self, data):
                    if self._in_title:
                        self._title.append(data.strip())
                    elif not self._skip:
                        stripped = data.strip()
                        if stripped:
                            self._body.append(stripped)

            req = urllib.request.Request(
                url,
                headers={'User-Agent': 'Mozilla/5.0 (compatible; LAYER-OS/1.0)'},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                charset = resp.headers.get_content_charset() or 'utf-8'
                html = resp.read().decode(charset, errors='replace')

            parser = _Extractor()
            parser.feed(html)
            title = ' '.join(parser._title).strip()
            content = ' '.join(parser._body)
            # 연속 공백 정리 + 5000자 제한
            content = ' '.join(content.split())[:5000]
            return {"title": title, "content": content, "ok": bool(content)}
        except Exception as e:
            logger.warning("URL fetch 실패 (%s): %s", url, e)
            return {"title": "", "content": "", "ok": False}

    async def process_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text
        try:
            # 의도 분류
            intent_data = self.classifier.classify(text)
            intent = intent_data['intent']

            if intent == 'insight':
                # URL이면 페이지 본문 fetch 후 풍부한 신호로 저장
                url_match = re.search(r'https?://\S+', text)
                if url_match:
                    url = url_match.group(0)
                    status_msg = await update.message.reply_text("🔍 페이지 수집 중...")
                    fetched = self._fetch_url_content(url)
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    signal_id = "url_%s" % timestamp
                    content = fetched["content"] if fetched["ok"] else ("URL: %s" % url)
                    signal_data = {
                        "signal_id": signal_id,
                        "type": "url_content",
                        "status": "captured",
                        "content": content,
                        "captured_at": datetime.now().isoformat(),
                        "from_user": update.effective_user.username or update.effective_user.first_name,
                        "source_channel": "telegram",
                        "metadata": {
                            "source_url": url,
                            "title": fetched["title"],
                            "fetch_ok": fetched["ok"],
                        },
                    }
                    _, queue_ok = self._save_signal(signal_data)
                    fetch_note = f"제목: {_escape_html(fetched['title'][:80])}\n" if fetched["title"] else ""
                    fetch_status = f"본문 {len(fetched['content'])}자 수집" if fetched["ok"] else "⚠️ 본문 수집 실패 (URL만 저장)"
                    sa_status = "SA 분석 중." if queue_ok else "⚠️ SA 큐 전달 실패"
                    await status_msg.edit_text(
                        f"📥 <b>URL 수집 완료</b>\n\n"
                        f"{fetch_note}"
                        f"{fetch_status}\n"
                        f"{sa_status}",
                        parse_mode=constants.ParseMode.HTML,
                    )
                    return

                queue_ok = self._save_insight(text, update.effective_user)
                timestamp = datetime.now().strftime('%H:%M:%S')
                preview = _escape_html(text[:150])
                sa_status = (
                    "SA가 분석 중입니다." if queue_ok
                    else "⚠️ SA 분석 대기열 전달 실패 (수동 확인 필요)"
                )
                await update.message.reply_text(
                    f"💾 <b>Captured</b> (<code>{timestamp}</code>)\n\n"
                    f"\"{preview}\"\n\n"
                    f"signals/ 저장 완료. {sa_status}",
                    parse_mode=constants.ParseMode.HTML
                )
            else:
                # 대화 및 질문 (Deep RAG)
                placeholder = await update.message.reply_text("💭 사유 중...")
                try:
                    response = self.engine.chat(str(update.effective_user.id), text)
                    await placeholder.edit_text(_tg(_escape_html(response)), parse_mode=constants.ParseMode.HTML)
                except Exception as chat_e:
                    logger.error("Chat engine error: %s", chat_e)
                    await placeholder.edit_text("죄송합니다. 응답 생성 중 오류가 발생했습니다.")

        except Exception as e:
            logger.error("process_text error: %s", e)
            try:
                await update.message.reply_text("처리 중 오류가 발생했습니다. 다시 시도해주십시오.")
            except Exception:
                pass

    def _save_signal(self, signal_data: dict) -> tuple:
        """
        signals/ JSON 저장 + SA 큐 전달.
        Returns: (signal_id: str, queue_ok: bool)
        """
        signal_id = signal_data["signal_id"]
        signals_dir = PROJECT_ROOT / "knowledge" / "signals"
        signals_dir.mkdir(parents=True, exist_ok=True)
        with open(signals_dir / ("%s.json" % signal_id), "w", encoding="utf-8") as f:
            json.dump(signal_data, f, ensure_ascii=False, indent=2)

        queue_ok = False
        try:
            from core.system.queue_manager import QueueManager
            qm = QueueManager()
            qm.create_task(
                agent_type="SA",
                task_type="analyze_signal",
                payload={
                    "signal_id": signal_id,
                    "signal_path": str(signals_dir / ("%s.json" % signal_id)),
                },
            )
            queue_ok = True
            logger.info("SA 큐 전달: %s", signal_id)
        except Exception as q_e:
            logger.warning("SA 큐 전달 실패: %s", q_e)

        return signal_id, queue_ok

    def _save_insight(self, text: str, user) -> bool:
        """
        인사이트 저장 + SA 에이전트 분석 큐에 전달.
        Returns: queue_ok — False면 경고 표시 필요
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        signal_id = "text_%s" % timestamp
        signal_data = {
            'signal_id': signal_id,
            'type': 'text_insight',
            'status': 'captured',
            'content': text,
            'captured_at': datetime.now().isoformat(),
            'from_user': user.username or user.first_name,
            'source_channel': 'telegram',
            'metadata': {},
        }
        _, queue_ok = self._save_signal(signal_data)
        return queue_ok

    @admin_only
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/status — 파이프라인 현황 스냅샷"""
        try:
            signals_dir = PROJECT_ROOT / 'knowledge' / 'signals'
            corpus_index = PROJECT_ROOT / 'knowledge' / 'corpus' / 'index.json'
            queue_completed = PROJECT_ROOT / '.infra' / 'queue' / 'tasks' / 'completed'
            queue_pending = PROJECT_ROOT / '.infra' / 'queue' / 'tasks' / 'pending'

            sig_stats: Dict = {}
            for f in signals_dir.glob('*.json'):
                try:
                    d = json.loads(f.read_text())
                    s = d.get('status', 'unknown')
                    sig_stats[s] = sig_stats.get(s, 0) + 1
                except Exception:
                    pass

            clusters_total = 0
            published_count = 0
            if corpus_index.exists():
                ci = json.loads(corpus_index.read_text())
                clusters_total = len(ci.get('clusters', {}))
                published_count = len(ci.get('published', []))

            pending_cnt = len(list(queue_pending.glob('*.json'))) if queue_pending.exists() else 0
            completed_cnt = len(list(queue_completed.glob('*.json'))) if queue_completed.exists() else 0

            from datetime import datetime as _dt
            now = _dt.now()
            next_g = now.replace(hour=3, minute=0, second=0, microsecond=0)
            if next_g <= now:
                from datetime import timedelta
                next_g += timedelta(days=1)
            delta = next_g - now
            h, rem = divmod(int(delta.total_seconds()), 3600)
            m = rem // 60

            total_sigs = sum(sig_stats.values())
            msg = (
                f"<b>⚙️ 파이프라인 현황</b>\n\n"
                f"<b>신호</b>\n"
                f"총 {total_sigs}개 | 수집 {sig_stats.get('captured',0)} | "
                f"분석완료 {sig_stats.get('analyzed',0)}\n\n"
                f"<b>Corpus</b>\n"
                f"군집 {clusters_total}개 | 발행됨 {published_count}개\n\n"
                f"<b>태스크 큐</b>\n"
                f"대기 {pending_cnt}개 | 완료 {completed_cnt}개\n\n"
                f"<b>Gardener</b>\n"
                f"다음 실행: {h}시간 {m}분 후 (03:00)"
            )
            await update.message.reply_text(msg, parse_mode=constants.ParseMode.HTML)

        except Exception as e:
            logger.error("status_command error: %s", e)
            await update.message.reply_text(f"상태 조회 오류: {_escape_html(str(e))}", parse_mode=constants.ParseMode.HTML)

    @admin_only
    async def publish_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/publish [테마] — Corpus 군집 즉시 발행 트리거"""
        theme_arg = ' '.join(context.args).strip() if context.args else None
        try:
            from core.system.corpus_manager import CorpusManager
            corpus = CorpusManager()
            corpus_index_path = PROJECT_ROOT / 'knowledge' / 'corpus' / 'index.json'

            if theme_arg:
                index = json.loads(corpus_index_path.read_text()) if corpus_index_path.exists() else {}
                clusters = index.get('clusters', {})
                matched = next((v for k, v in clusters.items() if theme_arg in k), None)
                if not matched:
                    available = ', '.join(clusters.keys()) or '없음'
                    await update.message.reply_text(
                        f"테마 <b>{_escape_html(theme_arg)}</b> 군집 없음.\n"
                        f"현재 군집: {_escape_html(available)}",
                        parse_mode=constants.ParseMode.HTML
                    )
                    return
                ripe = [matched]
                forced = True
            else:
                ripe = corpus.get_ripe_clusters()
                forced = False

            if not ripe:
                index = json.loads(corpus_index_path.read_text()) if corpus_index_path.exists() else {}
                clusters = index.get('clusters', {})
                if clusters:
                    lines = ["<b>발행 가능한 군집 없음</b> (성숙도 미달)\n", "<b>현재 군집:</b>"]
                    for theme, c in clusters.items():
                        cnt = len(c.get('entry_ids', []))
                        lines.append(f"  • {_escape_html(theme)}: {cnt}개 신호")
                    lines.append("\n조건: 5개+ 신호, 72시간+ 분포")
                    await update.message.reply_text('\n'.join(lines), parse_mode=constants.ParseMode.HTML)
                else:
                    await update.message.reply_text(
                        "아직 Corpus 군집이 없습니다.\n신호가 분석되면 자동으로 군집이 형성됩니다."
                    )
                return

            from core.system.queue_manager import QueueManager
            qm = QueueManager()
            triggered = []
            for cluster in ripe:
                theme = cluster.get('theme', 'unknown')
                qm.create_task(
                    agent_type='CE',
                    task_type='write_corpus_essay',
                    payload={
                        'cluster': cluster,
                        'forced': forced,
                        'triggered_by': 'telegram_publish_command',
                    }
                )
                triggered.append(theme)

            forced_label = " (강제)" if forced else ""
            themes_text = ', '.join(_escape_html(t) for t in triggered)
            await update.message.reply_text(
                f"🚀 <b>발행 트리거됨{forced_label}</b>\n\n"
                f"테마: {themes_text}\n"
                f"CE 에이전트가 에세이를 작성합니다.\n"
                f"완료 시 {os.getenv('SITE_ARCHIVE_PATH', 'website/archive')}/ 에 파일로 저장됩니다.\n"
                f"(도메인 연결 후 {os.getenv('SITE_BASE_URL', 'https://woohwahae.kr')}/archive/ 에 노출)",
                parse_mode=constants.ParseMode.HTML
            )

        except Exception as e:
            logger.error("publish_command error: %s", e)
            await update.message.reply_text(f"발행 오류: {_escape_html(str(e))}", parse_mode=constants.ParseMode.HTML)

    @admin_only
    async def signal_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/signal [텍스트] — 신호 직접 투입"""
        text = ' '.join(context.args).strip() if context.args else ''
        if not text:
            await update.message.reply_text(
                "사용법: <code>/signal 투입할 내용</code>",
                parse_mode=constants.ParseMode.HTML
            )
            return
        try:
            self._save_insight(text, update.effective_user)
            preview = _escape_html(text[:100])
            await update.message.reply_text(
                f"📥 <b>신호 투입 완료</b>\n\n\"{preview}\"\n\nSA 분석 큐 전달됨.",
                parse_mode=constants.ParseMode.HTML
            )
        except Exception as e:
            logger.error("signal_command error: %s", e)
            await update.message.reply_text(f"신호 투입 오류: {_escape_html(str(e))}", parse_mode=constants.ParseMode.HTML)

    @admin_only
    async def note_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/note [내용] — 텍스트를 knowledge/docs/note_YYYYMMDD_HHMMSS.md로 저장 (분석 없음)
        선택: /note @제목 내용  →  지정 제목으로 저장 / 기존 파일이면 append
        """
        import re as _re
        from datetime import datetime as _dt

        # 전체 텍스트에서 커맨드 부분 제거
        raw = update.message.text or ''
        # '/note' 이후 텍스트
        body = _re.sub(r'^/note\S*\s*', '', raw, count=1).strip()

        # @제목 옵션 파싱
        title_match = _re.match(r'^@(\S+)\s+(.*)', body, _re.DOTALL)
        if title_match:
            title = title_match.group(1)
            body = title_match.group(2).strip()
        else:
            title = _dt.now().strftime('note_%Y%m%d_%H%M%S')

        if not body:
            await update.message.reply_text(
                "<b>사용법</b>\n"
                "<code>/note 내용 그대로 붙여넣기</code>\n"
                "→ note_YYYYMMDD_HHMMSS.md 자동 생성\n\n"
                "<code>/note @제목 내용</code>\n"
                "→ 제목.md 저장 (기존 파일이면 내용 추가)\n\n"
                "분석 없음 — 나중에 지시해서 활용.",
                parse_mode=constants.ParseMode.HTML
            )
            return

        try:
            docs_dir = PROJECT_ROOT / 'knowledge' / 'docs'
            docs_dir.mkdir(parents=True, exist_ok=True)

            # 파일명 정리: 특수문자 제거, 소문자
            safe_title = _re.sub(r'[^\w가-힣-]', '_', title).lower().strip('_')
            if not safe_title:
                safe_title = _dt.now().strftime('note_%Y%m%d_%H%M%S')
            if not safe_title.endswith('.md'):
                safe_title += '.md'

            note_path = docs_dir / safe_title

            # 기존 파일 있으면 append, 없으면 신규 생성
            ts = _dt.now().strftime('%Y-%m-%d %H:%M')
            if note_path.exists():
                existing = note_path.read_text(encoding='utf-8')
                note_path.write_text(
                    existing + f"\n\n---\n_추가: {ts}_\n\n{body}",
                    encoding='utf-8'
                )
                action = "추가"
            else:
                note_path.write_text(
                    f"_저장: {ts}_\n\n{body}",
                    encoding='utf-8'
                )
                action = "생성"

            # git commit+push → 로컬 동기화
            import asyncio as _asyncio
            sync_ok = False
            try:
                _pipe = _asyncio.subprocess.PIPE
                _git_env = {
                    **__import__('os').environ,
                    'GIT_TERMINAL_PROMPT': '0',
                }

                _add = await _asyncio.create_subprocess_exec(
                    'git', 'add', str(note_path),
                    cwd=str(PROJECT_ROOT), env=_git_env,
                    stdout=_pipe, stderr=_pipe
                )
                _, _add_err = await _add.communicate()

                _commit = await _asyncio.create_subprocess_exec(
                    'git', 'commit', '-m', f'note: {safe_title[:-3]}',
                    cwd=str(PROJECT_ROOT), env=_git_env,
                    stdout=_pipe, stderr=_pipe
                )
                _, _commit_err = await _commit.communicate()

                _push = await _asyncio.create_subprocess_exec(
                    'git', 'push', 'origin', 'HEAD:main',
                    cwd=str(PROJECT_ROOT), env=_git_env,
                    stdout=_pipe, stderr=_pipe
                )
                _, _push_err = await _push.communicate()
                sync_ok = _push.returncode == 0
                if not sync_ok:
                    logger.warning("note git push failed (rc=%d): %s",
                                   _push.returncode,
                                   (_push_err or b'').decode('utf-8', errors='replace').strip())
            except Exception as _ge:
                logger.warning("note git sync failed: %s", _ge)

            preview = _escape_html(body[:80])
            sync_tag = " · git pushed" if sync_ok else " · git sync 실패"
            await update.message.reply_text(
                f"📝 <b>노트 {action}</b>{sync_tag}\n\n"
                f"파일: <code>knowledge/docs/{safe_title}</code>\n\n"
                f"\"{preview}\"",
                parse_mode=constants.ParseMode.HTML
            )
        except Exception as e:
            logger.error("note_command error: %s", e)
            await update.message.reply_text(f"노트 저장 오류: {_escape_html(str(e))}", parse_mode=constants.ParseMode.HTML)

    @admin_only
    async def report_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/report — 오늘 처리 요약"""
        try:
            from datetime import date as _date
            today = _date.today().isoformat()
            signals_dir = PROJECT_ROOT / 'knowledge' / 'signals'
            queue_completed = PROJECT_ROOT / '.infra' / 'queue' / 'tasks' / 'completed'

            today_sigs = []
            for f in signals_dir.glob('*.json'):
                try:
                    d = json.loads(f.read_text())
                    if d.get('captured_at', '').startswith(today):
                        today_sigs.append(d)
                except Exception:
                    pass

            today_sa = 0
            scores = []
            if queue_completed.exists():
                for f in queue_completed.glob('*.json'):
                    try:
                        d = json.loads(f.read_text())
                        if d.get('agent_type') == 'SA' and (d.get('completed_at') or '').startswith(today):
                            today_sa += 1
                            score = d.get('result', {}).get('result', {}).get('strategic_score', 0)
                            if score:
                                scores.append(score)
                    except Exception:
                        pass
            avg_score = int(sum(scores) / len(scores)) if scores else 0

            corpus_index = PROJECT_ROOT / 'knowledge' / 'corpus' / 'index.json'
            clusters_total = published_count = 0
            if corpus_index.exists():
                ci = json.loads(corpus_index.read_text())
                clusters_total = len(ci.get('clusters', {}))
                published_count = len(ci.get('published', []))

            sig_types: Dict = {}
            for s in today_sigs:
                t = s.get('type', 'unknown')
                sig_types[t] = sig_types.get(t, 0) + 1
            sig_type_text = ', '.join(f"{t} {n}개" for t, n in sig_types.items()) or '없음'

            msg = (
                f"<b>📋 일일 리포트 — {today}</b>\n\n"
                f"<b>오늘 수집</b>\n"
                f"신규 신호: {len(today_sigs)}개 ({sig_type_text})\n\n"
                f"<b>오늘 분석</b>\n"
                f"SA 완료: {today_sa}건"
                + (f" | 평균 점수: {avg_score}" if avg_score else "") + "\n\n"
                f"<b>Corpus 누적</b>\n"
                f"군집: {clusters_total}개 | 발행: {published_count}개\n\n"
                f"/publish — 즉시 발행  |  /status — 상세 현황"
            )
            await update.message.reply_text(msg, parse_mode=constants.ParseMode.HTML)

        except Exception as e:
            logger.error("report_command error: %s", e)
            await update.message.reply_text(f"리포트 오류: {_escape_html(str(e))}", parse_mode=constants.ParseMode.HTML)

    @admin_only
    async def approve_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Gardener 제안 승인 — /approve [id]"""
        if not self.gardener:
            await update.message.reply_text("Gardener가 비활성 상태입니다.")
            return

        pending = self.gardener.pending
        if not pending:
            await update.message.reply_text("대기 중인 제안이 없습니다.")
            return

        # ID 지정 없으면 첫 번째 제안
        args = context.args
        proposal_id = args[0] if args else pending[0]['id']

        success, msg = self.gardener.approve_proposal(proposal_id)
        await update.message.reply_text(msg, parse_mode=constants.ParseMode.HTML)

    @admin_only
    async def reject_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Gardener 제안 거절 — /reject [id]"""
        if not self.gardener:
            await update.message.reply_text("Gardener가 비활성 상태입니다.")
            return

        pending = self.gardener.pending
        if not pending:
            await update.message.reply_text("대기 중인 제안이 없습니다.")
            return

        args = context.args
        proposal_id = args[0] if args else pending[0]['id']
        proposal = next((p for p in pending if p['id'] == proposal_id), None)
        label = f"{proposal['target_file']} — {proposal['reason']}" if proposal else proposal_id

        self.gardener.reject_proposal(proposal_id)
        await update.message.reply_text(f"❌ 거절됨: {label}")

    @admin_only
    async def pending_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """대기 중인 Gardener 제안 목록 — /pending"""
        if not self.gardener or not self.gardener.pending:
            await update.message.reply_text("대기 중인 제안이 없습니다.")
            return

        lines = ["<b>📋 대기 중인 제안</b>", ""]
        for p in self.gardener.pending:
            lines.append(
                f"<code>{p['id']}</code>\n"
                f"파일: {p['target_file']}\n"
                f"이유: {p['reason']}\n"
                f"내용: {p['proposed_addition'][:80]}...\n"
            )
        lines.append("/approve [id] 또는 /reject [id]")
        await update.message.reply_text(
            "\n".join(lines), parse_mode=constants.ParseMode.HTML
        )

    @admin_only
    async def draft_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/draft [테마] — 에세이 초안 생성 후 승인 대기"""
        theme_arg = ' '.join(context.args).strip() if context.args else None
        if not theme_arg:
            await update.message.reply_text(
                "사용법: <code>/draft 테마명</code>\n예: /draft 슬로우라이프",
                parse_mode=constants.ParseMode.HTML
            )
            return

        status_msg = await update.message.reply_text(
            f"✍️ <b>{_escape_html(theme_arg)}</b> 초안 작성 중...",
            parse_mode=constants.ParseMode.HTML
        )
        try:
            # 지식 베이스에서 테마 관련 신호 검색
            knowledge = self.engine._search_knowledge(theme_arg)
            draft_prompt = (
                f"woohwahae 브랜드 아카이브 에세이 초안을 써줘.\n"
                f"테마: {theme_arg}\n"
                f"관련 자료:\n{knowledge[:2000] if knowledge else '없음'}\n\n"
                f"조건: 800~1200자, 한국어, 명사형 제목, Magazine B 스타일, "
                f"슬로우라이프 철학 반영. 제목과 본문만 출력."
            )
            import requests as _req
            _api_key = os.getenv('GOOGLE_API_KEY') or os.getenv('GEMINI_API_KEY')
            if not _api_key:
                raise RuntimeError("GOOGLE_API_KEY 환경변수 없음")
            _url = (
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"gemini-2.5-flash:generateContent?key={_api_key}"
            )
            _resp = _req.post(
                _url,
                json={"contents": [{"parts": [{"text": draft_prompt}]}]},
                timeout=90
            )
            _resp.raise_for_status()
            draft_text = _resp.json()["candidates"][0]["content"]["parts"][0]["text"]

            if not draft_text:
                await status_msg.edit_text("초안 생성 실패.")
                return

            # 초안 임시 저장
            draft_id = f"draft_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            draft_path = PROJECT_ROOT / '.infra' / 'drafts'
            draft_path.mkdir(parents=True, exist_ok=True)
            (draft_path / f"{draft_id}.json").write_text(
                json.dumps({'id': draft_id, 'theme': theme_arg, 'content': draft_text,
                            'created_at': datetime.now().isoformat()}, ensure_ascii=False, indent=2)
            )

            # 초안 미리보기 + 승인 버튼
            preview = draft_text[:800] + ("..." if len(draft_text) > 800 else "")
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ 발행", callback_data=f"draft_publish:{draft_id}"),
                InlineKeyboardButton("❌ 폐기", callback_data=f"draft_discard:{draft_id}"),
            ]])
            await status_msg.edit_text(
                f"<b>📝 초안 — {_escape_html(theme_arg)}</b>\n\n"
                f"{_escape_html(preview)}",
                parse_mode=constants.ParseMode.HTML,
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error("draft_command error: %s", e)
            await status_msg.edit_text(f"초안 오류: {_escape_html(str(e))}", parse_mode=constants.ParseMode.HTML)

    @admin_only
    async def corpus_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/corpus — 군집 현황 미리보기"""
        try:
            corpus_index = PROJECT_ROOT / 'knowledge' / 'corpus' / 'index.json'
            if not corpus_index.exists():
                await update.message.reply_text("Corpus가 아직 초기화되지 않았습니다.")
                return

            ci = json.loads(corpus_index.read_text())
            clusters = ci.get('clusters', {})
            published = ci.get('published', [])

            if not clusters:
                await update.message.reply_text(
                    "아직 군집 없음.\nSA 분석이 완료되면 자동으로 군집이 형성됩니다."
                )
                return

            lines = [f"<b>🗂 Corpus 군집 현황</b> (발행됨: {len(published)}개)\n"]
            for theme, c in sorted(clusters.items(), key=lambda x: len(x[1].get('entry_ids', [])), reverse=True):
                cnt = len(c.get('entry_ids', []))
                last = c.get('last_seen', '')[:10]
                # 성숙도 판단 (5개+ = 발행 가능)
                ready = "🟢 발행가능" if cnt >= 5 else f"🟡 축적중 ({5-cnt}개 더 필요)"
                lines.append(f"<b>{_escape_html(theme)}</b>\n  {cnt}개 신호 | {last} | {ready}\n")

            lines.append("/publish [테마] 로 즉시 발행")
            await update.message.reply_text(_tg('\n'.join(lines)), parse_mode=constants.ParseMode.HTML)

        except Exception as e:
            logger.error("corpus_command error: %s", e)
            await update.message.reply_text(f"오류: {_escape_html(str(e))}", parse_mode=constants.ParseMode.HTML)

    async def handle_draft_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """초안 승인/폐기 인라인 버튼 처리"""
        query = update.callback_query
        await query.answer()
        data = query.data  # "draft_publish:draft_id" or "draft_discard:draft_id"

        try:
            action, draft_id = data.split(':', 1)
            draft_path = PROJECT_ROOT / '.infra' / 'drafts' / f"{draft_id}.json"

            if not draft_path.exists():
                await query.edit_message_text("초안을 찾을 수 없습니다.")
                return

            draft = json.loads(draft_path.read_text())

            if action == 'draft_discard':
                draft_path.unlink()
                await query.edit_message_text(f"❌ 폐기됨: {draft['theme']}")
                return

            # 발행: CE 태스크로 전달
            from core.system.queue_manager import QueueManager
            qm = QueueManager()
            qm.create_task(
                agent_type='CE',
                task_type='write_corpus_essay',
                payload={
                    'draft_content': draft['content'],
                    'theme': draft['theme'],
                    'forced': True,
                    'triggered_by': 'telegram_draft_approve',
                }
            )
            draft_path.unlink()
            await query.edit_message_text(
                f"🚀 <b>발행 승인됨</b>\n\n"
                f"테마: {_escape_html(draft['theme'])}\n"
                f"CE 에이전트가 최종 포맷으로 처리합니다.",
                parse_mode=constants.ParseMode.HTML
            )
        except Exception as e:
            logger.error("draft callback error: %s", e)
            await query.edit_message_text(f"처리 오류: {str(e)[:100]}")

    async def handle_action_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Gardener 기계적 수정 제안 승인/건너뜀 처리 — action_apply:id / action_skip:id"""
        query = update.callback_query
        await query.answer()
        data = query.data  # "action_apply:id" or "action_skip:id"

        try:
            verb, action_id = data.split(':', 1)
            actions_path = PROJECT_ROOT / '.infra' / 'queue' / 'pending_actions.json'

            if not actions_path.exists():
                await query.edit_message_text("액션 파일을 찾을 수 없습니다.")
                return

            registry = json.loads(actions_path.read_text(encoding='utf-8'))
            action = next((a for a in registry.get('actions', []) if a['id'] == action_id), None)

            if not action:
                await query.edit_message_text("액션을 찾을 수 없습니다: %s" % action_id)
                return

            if verb == 'action_skip':
                action['status'] = 'skipped'
                action['skipped_at'] = datetime.now().isoformat()
                actions_path.write_text(json.dumps(registry, indent=2, ensure_ascii=False), encoding='utf-8')
                _append_decision_log_direct({'type': 'action_skip', 'actor': 'telegram', 'id': action_id,
                    'title': action.get('title', action_id), 'meta': {'action_type': action.get('type', '')}})
                await query.edit_message_text("⏭ 건너뜀: %s" % action['title'])
                return

            # 적용
            from core.agents.gardener import Gardener
            success, msg = Gardener.execute_action(action)
            action['status'] = 'applied' if success else 'failed'
            action['applied_at'] = datetime.now().isoformat()
            action['result'] = msg
            actions_path.write_text(json.dumps(registry, indent=2, ensure_ascii=False), encoding='utf-8')
            _append_decision_log_direct({'type': 'action_apply', 'actor': 'telegram', 'id': action_id,
                'title': action.get('title', action_id),
                'meta': {'action_type': action.get('type', ''), 'result': msg, 'success': success}})

            icon = "✅" if success else "❌"
            await query.edit_message_text(
                "%s <b>%s</b>\n\n%s" % (icon, action['title'], msg),
                parse_mode=constants.ParseMode.HTML,
            )
        except Exception as e:
            logger.error("action callback error: %s", e)
            await query.edit_message_text("처리 오류: %s" % str(e)[:100])

    async def handle_council_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Council 협의 승인/거절 인라인 버튼 처리"""
        query = update.callback_query
        await query.answer()
        data = query.data  # "council_approve:proposal_id" or "council_reject:proposal_id"

        try:
            action, proposal_id = data.split(':', 1)
            from core.system.council_manager import CouncilManager
            council = CouncilManager()

            if action == 'council_reject':
                council.reject_proposal(proposal_id)
                _append_decision_log_direct({'type': 'council_reject', 'actor': 'telegram', 'id': proposal_id,
                    'title': '에세이 거절', 'meta': {}})
                await query.edit_message_text("❌ 거절됨 (proposal=%s)" % proposal_id)
                return

            # 승인
            task_id = council.approve_proposal(proposal_id)
            if task_id:
                _append_decision_log_direct({'type': 'council_approve', 'actor': 'telegram', 'id': proposal_id,
                    'title': 'Council 에세이 승인', 'meta': {'task_id': task_id}})
                await query.edit_message_text(
                    "🚀 <b>발행 승인됨</b>\n\nCE 에이전트가 에세이를 작성합니다.\nCE task: <code>%s</code>" % task_id,
                    parse_mode=constants.ParseMode.HTML,
                )
            else:
                await query.edit_message_text("⚠️ CE task 생성 실패. corpus entries 확인 필요.")
        except Exception as e:
            logger.error("council callback error: %s", e)
            await query.edit_message_text("처리 오류: %s" % str(e)[:100])

    async def send_daily_briefing(self, app):
        """매일 08:00 자동 브리핑 푸시"""
        admin_id = os.getenv('ADMIN_TELEGRAM_ID')
        if not admin_id:
            return
        try:
            from datetime import date as _date
            today = _date.today().isoformat()
            signals_dir = PROJECT_ROOT / 'knowledge' / 'signals'
            corpus_index = PROJECT_ROOT / 'knowledge' / 'corpus' / 'index.json'

            today_sigs = sum(
                1 for f in signals_dir.glob('*.json')
                if json.loads(f.read_text()).get('captured_at', '').startswith(today)
            )
            clusters_total = published = 0
            if corpus_index.exists():
                ci = json.loads(corpus_index.read_text())
                clusters_total = len(ci.get('clusters', {}))
                published = len(ci.get('published', []))
                ripe = sum(
                    1 for c in ci.get('clusters', {}).values()
                    if len(c.get('entry_ids', [])) >= 5
                )
            else:
                ripe = 0

            ripe_notice = (
                DAILY_BRIEFING_RIPE.format(ripe=ripe) if ripe > 0
                else DAILY_BRIEFING_IDLE
            )
            msg = DAILY_BRIEFING.format(
                today=today, today_sigs=today_sigs,
                clusters_total=clusters_total, ripe=ripe,
                published=published, ripe_notice=ripe_notice,
            )
            await app.bot.send_message(chat_id=int(admin_id), text=msg, parse_mode=constants.ParseMode.HTML)
        except Exception as e:
            logger.error("daily briefing error: %s", e)

    async def notify_publish_complete(self, theme: str, url: str = ""):
        """발행 완료 시 텔레그램 알림 (CE agent에서 호출)"""
        admin_id = os.getenv('ADMIN_TELEGRAM_ID')
        if not admin_id or not hasattr(self, '_app'):
            return
        try:
            link_text = f"\n🔗 {url}" if url else ""
            msg = PUBLISH_COMPLETE.format(
                theme=_escape_html(theme), link_text=link_text,
            )
            await self._app.bot.send_message(
                chat_id=int(admin_id), text=msg, parse_mode=constants.ParseMode.HTML
            )
        except Exception as e:
            logger.error("notify_publish_complete error: %s", e)

    def run(self):
        from telegram.ext import JobQueue
        application = Application.builder().token(self.bot_token).build()
        self._app = application

        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("growth", self.growth_command))
        application.add_handler(CommandHandler("status", self.status_command))
        application.add_handler(CommandHandler("publish", self.publish_command))
        application.add_handler(CommandHandler("signal", self.signal_command))
        application.add_handler(CommandHandler("note", self.note_command))
        application.add_handler(CommandHandler("report", self.report_command))
        application.add_handler(CommandHandler("draft", self.draft_command))
        application.add_handler(CommandHandler("corpus", self.corpus_command))
        application.add_handler(CommandHandler("approve", self.approve_command))
        application.add_handler(CommandHandler("reject", self.reject_command))
        application.add_handler(CommandHandler("pending", self.pending_command))
        application.add_handler(CommandHandler("client", self.client_command))
        application.add_handler(CommandHandler("visit", self.visit_command))
        application.add_handler(CallbackQueryHandler(self.handle_draft_callback, pattern=r'^draft_'))
        application.add_handler(CallbackQueryHandler(self.handle_council_callback, pattern=r'^council_'))
        application.add_handler(CallbackQueryHandler(self.handle_action_callback, pattern=r'^action_'))
        application.add_handler(MessageHandler(filters.TEXT | filters.PHOTO | filters.Document.ALL, self.handle_message))

        # 매일 08:00 브리핑 자동 푸시
        from datetime import time as _time
        job_queue = application.job_queue
        if job_queue:
            job_queue.run_daily(
                lambda ctx: asyncio.create_task(self.send_daily_briefing(application)),
                time=_time(hour=8, minute=0, second=0),
                name="daily_briefing"
            )

            async def _propose_expiry_job(context):
                if not self.propose_gate:
                    return
                admin_id = os.getenv('ADMIN_TELEGRAM_ID')
                if not admin_id:
                    return
                expired_list = self.propose_gate.expire_old()
                for item in expired_list:
                    try:
                        msg = (
                            f"⏰ <b>PROPOSE 만료</b>\n"
                            f"<code>{_escape_html(item['task_id'])}</code>\n\n"
                            f"요약: {_escape_html(item['summary'][:200])}\n\n"
                            f"24시간 응답 없어 자동 폐기됨."
                        )
                        await context.bot.send_message(
                            chat_id=int(admin_id), text=msg,
                            parse_mode=constants.ParseMode.HTML,
                        )
                    except Exception as notify_e:
                        logger.warning("PROPOSE 만료 알림 실패: %s", notify_e)

            job_queue.run_repeating(
                _propose_expiry_job,
                interval=1800,
                name="propose_expiry_check"
            )

            # Gardener 자율 제안 polling — 5분마다 미전송 제안을 순호에게 전송
            async def _duel_proposal_check_job(context):
                if not self.propose_gate:
                    return
                admin_id = os.getenv("ADMIN_TELEGRAM_ID")
                if not admin_id:
                    return
                unsent = self.propose_gate.get_pending_unsent()
                for task in unsent:
                    try:
                        short_diff = task["diff_text"][:3000]
                        escaped = (short_diff
                                   .replace("&", "&amp;")
                                   .replace("<", "&lt;")
                                   .replace(">", "&gt;"))
                        msg_text = (
                            f"[DUEL PROPOSE] <code>{task['task_id']}</code>\n\n"
                            f"<pre>{escaped}</pre>\n\n"
                            f"ok = 적용 / no = 폐기"
                        )
                        sent_msg = await context.bot.send_message(
                            chat_id=int(admin_id),
                            text=msg_text,
                            parse_mode=constants.ParseMode.HTML,
                        )
                        self.propose_gate.mark_sent(task["task_id"], sent_msg.message_id)
                        logger.info("Duel 제안 전송: %s", task["task_id"])
                    except Exception as send_e:
                        logger.warning("Duel 제안 전송 실패 (%s): %s", task["task_id"], send_e)

            job_queue.run_repeating(
                _duel_proposal_check_job,
                interval=300,  # 5분
                name="duel_proposal_check"
            )

        logger.info("🚀 V6 Secretary Service Started")
        application.run_polling()


if __name__ == "__main__":
    from core.system.env_validator import validate_env
    validate_env("telegram_secretary")

    token = os.getenv('TELEGRAM_BOT_TOKEN')
    bot = TelegramSecretaryV6(token)
    bot.run()
