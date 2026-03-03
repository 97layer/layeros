#!/usr/bin/env python3
"""
LAYER OS YouTube Analyzer
Automatically extracts, analyzes, and stores YouTube content

Author: LAYER OS Technical Director
Created: 2026-02-16
"""

import os
import re
import json
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime
import logging

# Load .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import google.genai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound
    TRANSCRIPT_AVAILABLE = True
except ImportError:
    TRANSCRIPT_AVAILABLE = False

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class YouTubeAnalyzer:
    """
    Analyzes YouTube videos and extracts insights

    Features:
    - Extract video ID from URL
    - Get transcript (Korean/English)
    - Summarize with Gemini
    - Save to knowledge base
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize YouTube Analyzer

        Args:
            api_key: Gemini API key (or use GOOGLE_API_KEY env var)
        """
        self.api_key = api_key or os.getenv('GOOGLE_API_KEY')

        # Initialize Gemini
        if GEMINI_AVAILABLE and self.api_key:
            self.client = genai.Client(api_key=self.api_key)
            self._model_name = 'gemini-2.5-flash'
            self.model = True  # flag: LLM available
            logger.info("✅ Gemini initialized for YouTube analysis")
        else:
            self.client = None
            self.model = None
            logger.warning("⚠️  Gemini not available")

        # Output directories
        self.signals_dir = PROJECT_ROOT / 'knowledge' / 'signals'
        self.signals_dir.mkdir(parents=True, exist_ok=True)

    def extract_video_id(self, url: str) -> Optional[str]:
        """
        Extract YouTube video ID from URL

        Supports:
        - https://youtu.be/VIDEO_ID
        - https://www.youtube.com/watch?v=VIDEO_ID
        - https://youtube.com/watch?v=VIDEO_ID
        """
        patterns = [
            r'(?:youtu\.be/)([a-zA-Z0-9_-]{11})',
            r'(?:youtube\.com/watch\?v=)([a-zA-Z0-9_-]{11})',
            r'(?:youtube\.com/embed/)([a-zA-Z0-9_-]{11})'
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        return None

    def get_transcript(self, video_id: str) -> Optional[str]:
        """
        Get transcript for YouTube video

        Tries Korean first, then English
        """
        if not TRANSCRIPT_AVAILABLE:
            logger.warning("youtube_transcript_api not installed")
            return None

        try:
            # Create API instance and fetch transcript
            api = YouTubeTranscriptApi()

            # Try Korean first, then English
            try:
                transcript_data = api.fetch(video_id, languages=['ko'])
                logger.info("✅ Found Korean transcript")
            except Exception:
                try:
                    transcript_data = api.fetch(video_id, languages=['en'])
                    logger.info("✅ Found English transcript")
                except Exception:
                    # Try any available transcript
                    transcript_data = api.fetch(video_id)
                    logger.info("✅ Found automatic transcript")

            # Format transcript
            text = ' '.join([snippet.text for snippet in transcript_data.snippets])
            return text

        except TranscriptsDisabled:
            logger.warning("Transcripts disabled for this video")
            return None
        except NoTranscriptFound:
            logger.warning("No transcript found")
            return None
        except Exception as e:
            logger.error("Transcript extraction failed: %s", e)
            return None

    def analyze_with_gemini(self, transcript: str, video_url: str) -> Dict:
        """
        Analyze transcript with Gemini

        Returns:
            {
                'summary': str,
                'key_insights': List[str],
                'topics': List[str],
                'actionable_items': List[str]
            }
        """
        if not self.model or not transcript:
            return {
                'summary': '분석 불가 (Gemini API 없음)',
                'key_insights': [],
                'topics': [],
                'actionable_items': []
            }

        transcript_excerpt = transcript[:8000]
        prompt = f"""다음은 YouTube 영상의 자막입니다. WOOHWAHAE 브랜드 렌즈(슬로우라이프, 소거, 본질)로 분석해주세요.

**영상 URL**: {video_url}

**자막**:
{transcript_excerpt}

**분석 요청**:
1. **요약** (3-4문장으로 핵심만)
2. **핵심 인사이트** (3-5개 bullet points)
3. **주요 토픽** (키워드 5개)
4. **브랜드 연결점** (슬로우라이프/소거 관점에서 적용 가능한 것)

간결하고 건조하게. 과장 없이 본질만.
"""

        try:
            response = self.client.models.generate_content(
                model=self._model_name,
                contents=[prompt]
            )
            text = response.text

            # Parse response (simple parsing)
            return {
                'summary': text[:500],  # First part as summary
                'full_analysis': text,
                'key_insights': self._extract_bullet_points(text),
                'topics': [],  # Could be enhanced with better parsing
                'actionable_items': []
            }

        except Exception as e:
            logger.error("Gemini analysis failed: %s", e)
            return {
                'summary': '분석 실패',
                'key_insights': [],
                'topics': [],
                'actionable_items': []
            }

    def _extract_bullet_points(self, text: str) -> list:
        """Extract bullet points from text"""
        lines = text.split('\n')
        bullets = []
        for line in lines:
            line = line.strip()
            if line.startswith('-') or line.startswith('•') or line.startswith('*'):
                bullets.append(line[1:].strip())
        return bullets[:5]  # Top 5

    def save_to_knowledge_base(self, analysis: Dict, video_url: str, transcript: str = None,
                               source_channel: str = "manual") -> str:
        """
        통합 스키마로 knowledge/signals/ 저장 + SA 큐 전달.

        Returns: Path to saved file
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        video_id = self.extract_video_id(video_url)
        signal_id = "youtube_video_%s_%s" % (timestamp[:8], timestamp[9:])

        # 요약 텍스트 → content 필드
        summary = analysis.get('summary', '') or analysis.get('full_analysis', '')
        content = summary[:3000] if summary else "YouTube 수집: %s" % video_url

        data = {
            'signal_id': signal_id,
            'type': 'youtube_video',
            'status': 'captured',
            'content': content,
            'captured_at': datetime.now().isoformat(),
            'from_user': '97layer',
            'source_channel': source_channel,
            'metadata': {
                'title': analysis.get('title', ''),
                'video_id': video_id,
                'source_url': video_url,
                'transcript_length': len(transcript) if transcript else 0,
                'transcript_preview': (transcript[:2000] + '...') if transcript and len(transcript) > 2000 else transcript,
                'analysis': {
                    'key_insights': analysis.get('key_insights', []),
                    'summary': summary[:500] if summary else '',
                },
            },
        }

        filepath = self.signals_dir / ("%s.json" % signal_id)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info("저장: %s", filepath)

        # SA 큐 전달
        try:
            from core.system.queue_manager import QueueManager
            qm = QueueManager()
            qm.create_task(
                agent_type='SA',
                task_type='analyze_signal',
                payload={
                    'signal_id': signal_id,
                    'signal_path': str(filepath),
                }
            )
            logger.info("SA 큐 전달 (유튜브): %s", signal_id)
        except Exception as q_e:
            logger.warning("SA 큐 전달 실패: %s", q_e)

        return str(filepath)

    def process_url(self, video_url: str, source_channel: str = "manual") -> Dict:
        """
        Complete processing pipeline for YouTube URL

        Returns:
            {
                'success': bool,
                'video_id': str,
                'transcript': str,
                'analysis': Dict,
                'saved_path': str,
                'error': Optional[str]
            }
        """
        logger.info("Processing YouTube URL: %s", video_url)

        # Step 1: Extract video ID
        video_id = self.extract_video_id(video_url)
        if not video_id:
            return {
                'success': False,
                'error': 'Invalid YouTube URL'
            }

        logger.info("Video ID: %s", video_id)

        # Step 2: Get transcript
        transcript = self.get_transcript(video_id)

        if not transcript:
            # Save without transcript (URL + metadata only)
            logger.warning("No transcript available, saving URL only")
            analysis = {
                'summary': 'Transcript unavailable (video from cloud IP blocked by YouTube)',
                'key_insights': [],
                'topics': [],
                'note': 'Manual review needed'
            }
            saved_path = self.save_to_knowledge_base(analysis, video_url, transcript=None, source_channel=source_channel)
            return {
                'success': True,  # Changed to True - partial success
                'video_id': video_id,
                'transcript': None,
                'analysis': analysis,
                'saved_path': saved_path,
                'warning': 'Transcript unavailable - saved URL for manual review'
            }

        logger.info("Transcript length: %d characters", len(transcript))

        # Step 3: Analyze with Gemini
        analysis = self.analyze_with_gemini(transcript, video_url)

        # Step 4: Save to knowledge base
        saved_path = self.save_to_knowledge_base(analysis, video_url, transcript, source_channel=source_channel)

        return {
            'success': True,
            'video_id': video_id,
            'transcript': transcript[:500] + '...',  # Preview only
            'analysis': analysis,
            'saved_path': saved_path
        }


# ========================
# Convenience Functions
# ========================

_youtube_analyzer_instance = None


def get_youtube_analyzer() -> YouTubeAnalyzer:
    """Get YouTubeAnalyzer instance (singleton)"""
    global _youtube_analyzer_instance
    if _youtube_analyzer_instance is None:
        _youtube_analyzer_instance = YouTubeAnalyzer()
    return _youtube_analyzer_instance


# ========================
# CLI Testing
# ========================

def main():
    """CLI test interface"""
    import sys

    # Configure logging
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 2:
        print("Usage: python youtube_analyzer.py <youtube_url>")
        print("Example: python youtube_analyzer.py https://youtu.be/DpD0wnGk03s")
        sys.exit(1)

    url = sys.argv[1]

    analyzer = YouTubeAnalyzer()
    result = analyzer.process_url(url)

    if result['success']:
        print("\n✅ YouTube Analysis Complete!")
        print("=" * 60)
        print(f"Video ID: {result['video_id']}")
        print(f"Transcript Preview: {result['transcript'][:200]}...")
        print(f"\nSummary: {result['analysis']['summary'][:300]}...")
        print(f"\nSaved to: {result['saved_path']}")
    else:
        print(f"\n❌ Failed: {result.get('error', 'Unknown error')}")


if __name__ == "__main__":
    main()
