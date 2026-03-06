#!/usr/bin/env python3
"""
LAYER OS Pipeline Orchestrator
Signal → SA → Gardener → CE → Ralph → AD → CD → Publisher 자동 파이프라인

역할:
- Signal 스캔 → SA 태스크 자동 생성
- SA 완료 → Corpus 누적 (Gardener가 성숙 시 CE 트리거)
- CE 완료 → Ralph QA(인라인) → AD 태스크 생성
- AD 완료 → CD 최종 리뷰 태스크 생성
- CD 승인 → ContentPublisher 호출 (웹+텔레그램)
- CD 거절/정제 → CE 재작업 (max 2회)
- Ralph 품질 게이트: 90 미만 CE 재작업, 90+ AD 진행

중복 방지: .infra/queue/orchestrated.json

Author: LAYER OS
Created: 2026-02-17
"""

import json
import logging
import asyncio
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Any

# Run-safe import path for direct script execution.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """
    파이프라인 자동 흐름 관리자.
    각 에이전트는 독립적으로 동작, Orchestrator만 다음 단계 태스크를 생성.
    """

    # 확정 파이프라인:
    # Signal → SA → Corpus → Gardener(군집 성숙) → CE → Ralph(QA) → AD → CD → Publisher
    #
    # SA→Corpus: _process_sa_completed_only() (활성)
    # Gardener→CE: gardener._trigger_essay_for_cluster() (별도 데몬)
    # CE→Ralph→AD: _process_ce_completed() (Ralph은 인라인 QA 게이트)
    # AD→CD: _process_ad_completed()
    # CD→Publisher: _process_cd_completed()

    MAX_CE_RETRIES = 2  # CD 거절 후 CE 재작업 최대 횟수
    RALPH_PASS_SCORE = 90  # Ralph 품질 게이트

    def __init__(self, base_path: Optional[Path] = None):
        self.base_path = base_path or Path("/app")
        self.queue_path = self.base_path / ".infra" / "queue"
        self.orchestrated_file = self.queue_path / "orchestrated.json"
        self.completed_path = self.queue_path / "tasks" / "completed"
        self.pending_path = self.queue_path / "tasks" / "pending"

        # 처리된 태스크 추적 (중복 방지)
        self._orchestrated: Dict[str, Any] = self._load_orchestrated()
        self._running = False

        # 신호 디렉토리 (입력 소스)
        self.signals_path = self.base_path / "knowledge" / "signals"

    def _load_orchestrated(self) -> Dict:
        """이미 처리한 task_id 목록 로드"""
        if self.orchestrated_file.exists():
            try:
                return json.loads(self.orchestrated_file.read_text())
            except Exception:
                return {}
        return {}

    def _save_orchestrated(self):
        """처리된 task_id 목록 저장"""
        self.orchestrated_file.parent.mkdir(parents=True, exist_ok=True)
        self.orchestrated_file.write_text(json.dumps(self._orchestrated, indent=2, ensure_ascii=False))

    def _is_orchestrated(self, task_id: str) -> bool:
        return task_id in self._orchestrated

    def _mark_orchestrated(self, task_id: str, next_task_id: str):
        self._orchestrated[task_id] = {
            "orchestrated_at": datetime.now().isoformat(),
            "next_task_id": next_task_id
        }
        self._save_orchestrated()

    def _create_task(self, agent_type: str, task_type: str, payload: Dict) -> str:
        """큐에 새 태스크 파일 생성"""
        import time
        task_id = f"{int(time.time() * 1000)}_{agent_type}_{task_type}"
        task = {
            "task_id": task_id,
            "agent_type": agent_type,
            "task_type": task_type,
            "payload": payload,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "claimed_at": None,
            "completed_at": None,
            "claimed_by": None,
            "result": None,
            "error": None
        }
        self.pending_path.mkdir(parents=True, exist_ok=True)
        task_file = self.pending_path / f"{task_id}.json"
        task_file.write_text(json.dumps(task, indent=2, ensure_ascii=False))
        logger.info("[Orchestrator] 태스크 생성: %s", task_id)
        return task_id

    def _load_completed_tasks(self):
        """완료된 태스크 파일 목록 로드"""
        if not self.completed_path.exists():
            return []
        tasks = []
        for f in sorted(self.completed_path.glob("*.json")):
            try:
                data = json.loads(f.read_text())
                tasks.append(data)
            except Exception as e:
                logger.warning("태스크 파일 읽기 실패: %s - %s", f.name, e)
        return tasks

    def _get_ce_retry_count(self, signal_id: str) -> int:
        """특정 signal_id에 대한 CE 재작업 횟수"""
        count = 0
        for v in self._orchestrated.values():
            if isinstance(v, dict) and v.get("signal_id") == signal_id and v.get("retry_for") == "CE":
                count += 1
        return count

    def _ralph_score(self, ce_result: Dict) -> int:
        """
        CE 결과물 Ralph Loop 점수 계산.
        sage_architect.md §6.5 기준 4-Loop 순차 스캔.
        SSOT: core/system/essay_quality_validator.EssayQualityValidator
        """
        content = ce_result.get("result", {})
        essay = content.get("archive_essay", "")

        # 에세이 없으면 최저 점수
        if not essay or len(essay.strip()) < 50:
            logger.warning("[Orchestrator] Ralph: 에세이 없음 → 0점")
            return 0

        try:
            from core.system.essay_quality_validator import EssayQualityValidator
            validator = EssayQualityValidator()
            result = validator.validate(essay)
            score = result["score"]
            if result["issues"]:
                top_issues = [i.get("match", i.get("type", "")) for i in result["issues"][:3]]
                logger.info("[Orchestrator] Ralph %d/100 | 이슈: %s", score, top_issues)
            else:
                logger.info("[Orchestrator] Ralph %d/100 | 이슈 없음", score)
            return score
        except Exception as e:
            logger.warning("[Orchestrator] Ralph Loop 실행 실패, fallback: %s", e)
            # fallback: 에세이 존재 확인만
            return 60 if len(essay) >= 200 else 40

    def _get_processed_signal_ids(self) -> set:
        """이미 파이프라인에 투입되었거나 큐에 대기 중인 signal_id 반환 (중복 투입 방지)"""
        processed = set()
        for v in self._orchestrated.values():
            if isinstance(v, dict):
                sid = v.get("signal_id")
                if sid:
                    processed.add(sid)
        # pending 큐 파일에서도 확인 (재시작 시 중복 방지)
        if self.pending_path.exists():
            for f in self.pending_path.glob("*_SA_*.json"):
                try:
                    d = json.loads(f.read_text())
                    sid = d.get("payload", {}).get("signal_id")
                    if sid:
                        processed.add(sid)
                except Exception:
                    pass
        return processed

    def _scan_new_signals(self) -> int:
        """
        knowledge/signals/ 스캔 → 미처리 신호 → SA 태스크 자동 생성

        이 메서드가 없으면 파이프라인이 시작되지 않는다.
        신호는 텔레그램/YouTube 등으로 들어와 'captured' 상태로 쌓이는데,
        누군가 이를 SA 태스크로 변환해줘야 에이전트들이 처리 시작 가능.

        상태 규칙:
          captured / stored → 미처리 → SA 태스크 생성
          analyzed / published / processing → 이미 처리됨 → 스킵
        """
        if not self.signals_path.exists():
            return 0

        SKIP_STATUSES = {"analyzed", "published", "processing"}
        processed_ids = self._get_processed_signal_ids()
        created_count = 0

        for signal_file in sorted(self.signals_path.glob("*.json")):
            try:
                signal_data = json.loads(signal_file.read_text())
            except Exception as e:
                logger.warning("[Orchestrator] 신호 파일 읽기 실패: %s - %s", signal_file.name, e)
                continue

            signal_id = signal_data.get("signal_id", signal_file.stem)
            status = signal_data.get("status", "captured")
            signal_type = signal_data.get("type", "text_insight")

            if status in SKIP_STATUSES:
                continue
            if signal_id in processed_ids:
                continue

            # 필터링: 빈 신호 제거
            if signal_type == "youtube_video":
                # YouTube: content 또는 transcript 없으면 스킵
                has_content = len(signal_data.get("content", "").strip()) > 20
                has_transcript = bool(signal_data.get("transcript") or
                                      signal_data.get("metadata", {}).get("transcript_preview"))
                if not has_content and not has_transcript:
                    logger.debug("[Orchestrator] 스킵: %s (transcript 없음)", signal_id)
                    continue
            elif signal_type in ("text_insight", "url_content", "pdf_document", "image"):
                # 최소 내용 검증
                content = signal_data.get("content", "")
                if len(content.strip()) < 10:
                    logger.debug("[Orchestrator] 스킵: %s (내용 부족: %d자)", signal_id, len(content))
                    continue

            # SA 태스크 페이로드 구성
            payload = {
                "signal_id": signal_id,
                "signal_type": signal_type,
                "content": signal_data.get("content", ""),
                "signal_path": str(signal_file),
                "captured_at": signal_data.get("captured_at", ""),
                "from_user": signal_data.get("from_user", "97layer"),
                "metadata": signal_data.get("metadata", {}),
            }
            if signal_type == "youtube_video":
                meta = signal_data.get("metadata", {})
                payload["transcript"] = (signal_data.get("transcript", "")
                                         or meta.get("transcript_preview", ""))
                payload["video_id"] = meta.get("video_id", signal_data.get("video_id", ""))
                payload["title"] = meta.get("title", signal_data.get("title", ""))

            task_id = self._create_task("SA", "analyze_signal", payload)

            # 즉시 처리됨으로 마킹 (재시작 시 중복 방지)
            self._orchestrated["queued_%s" % signal_id] = {
                "orchestrated_at": datetime.now().isoformat(),
                "next_task_id": task_id,
                "signal_id": signal_id,
            }
            self._save_orchestrated()

            logger.info("[Orchestrator] 신규 신호 → SA 태스크: %s (%s)", signal_id, signal_type)
            created_count += 1

        if created_count > 0:
            logger.info("[Orchestrator] %d개 신호 파이프라인 투입 완료", created_count)

        return created_count

    def _process_sa_completed_only(self) -> int:
        """
        SA 완료 태스크만 처리 → Corpus 누적.
        즉시발행 체인(AD→CE→CD)은 실행하지 않음.
        발행은 Gardener가 Corpus 군집 성숙도 기반으로 트리거.
        """
        from core.system.corpus_manager import CorpusManager

        tasks = self._load_completed_tasks()
        processed_count = 0
        corpus = CorpusManager()

        for task in tasks:
            task_id = task.get("task_id", "")
            agent_type = task.get("agent_type", "")
            task_type = task.get("task_type", "")
            status = task.get("status", "")
            result = task.get("result", {}) or {}

            if self._is_orchestrated(task_id):
                continue
            if status != "completed":
                continue

            # SA 완료 → Corpus에 누적 (체인 진행 없음)
            if agent_type == "SA" and task_type in ["analyze_signal", "analyze"]:
                sa_result = result.get("result", {})
                signal_id = task.get("payload", {}).get("signal_id", "")
                signal_path = task.get("payload", {}).get("signal_path", "")

                # 원본 신호 데이터 로드
                signal_data = {}
                if signal_path:
                    try:
                        signal_data = json.loads(Path(signal_path).read_text())
                    except Exception:
                        signal_data = task.get("payload", {})

                try:
                    corpus.add_entry(signal_id, sa_result, signal_data)
                    logger.info("[Orchestrator] SA→Corpus: %s", signal_id)
                except Exception as e:
                    logger.warning("[Orchestrator] Corpus 누적 실패: %s", e)

                self._mark_orchestrated(task_id, "corpus_accumulated")
                processed_count += 1

        return processed_count

    def _process_ce_completed(self) -> int:
        """CE 완료 태스크 → Ralph QA → AD 태스크 생성"""
        tasks = self._load_completed_tasks()
        count = 0
        for task in tasks:
            task_id = task.get("task_id", "")
            if self._is_orchestrated(task_id):
                continue
            if task.get("status") != "completed":
                continue
            if task.get("agent_type") != "CE":
                continue
            if task.get("task_type") not in ("write_content", "write_corpus_essay"):
                continue

            result = task.get("result", {}) or {}
            next_id = self._handle_ce_completed(task, result)
            self._mark_orchestrated(task_id, next_id)
            count += 1
        return count

    def _process_ad_completed(self) -> int:
        """AD 완료 태스크 → CD 리뷰 태스크 생성"""
        tasks = self._load_completed_tasks()
        count = 0
        for task in tasks:
            task_id = task.get("task_id", "")
            if self._is_orchestrated(task_id):
                continue
            if task.get("status") != "completed":
                continue
            if task.get("agent_type") != "AD":
                continue
            if task.get("task_type") != "create_visual_concept":
                continue

            result = task.get("result", {}) or {}
            next_id = self._handle_ad_completed(task, result)
            self._mark_orchestrated(task_id, next_id)
            count += 1
        return count

    def _process_cd_completed(self) -> int:
        """CD 완료 태스크 → Publisher 트리거 or CE 재작업"""
        tasks = self._load_completed_tasks()
        count = 0
        for task in tasks:
            task_id = task.get("task_id", "")
            if self._is_orchestrated(task_id):
                continue
            if task.get("status") != "completed":
                continue
            if task.get("agent_type") != "CD":
                continue
            if task.get("task_type") != "review_content":
                continue

            result = task.get("result", {}) or {}
            next_id = self._handle_cd_completed(task, result)
            self._mark_orchestrated(task_id, next_id)
            count += 1
        return count

    def process_completed_tasks(self):
        """완료된 태스크 스캔 → 다음 파이프라인 단계 생성 (레거시 — 현재 미사용)"""
        tasks = self._load_completed_tasks()
        processed_count = 0

        for task in tasks:
            task_id = task.get("task_id", "")
            agent_type = task.get("agent_type", "")
            task_type = task.get("task_type", "")
            status = task.get("status", "")
            result = task.get("result", {}) or {}

            # 이미 처리된 태스크 스킵
            if self._is_orchestrated(task_id):
                continue

            # 실패한 태스크 스킵
            if status != "completed":
                continue

            # SA 완료 → AD 태스크 생성
            if agent_type == "SA" and task_type in ["analyze_signal", "analyze"]:
                next_task_id = self._handle_sa_completed(task, result)
                if next_task_id:
                    self._mark_orchestrated(task_id, next_task_id)
                    processed_count += 1
                else:
                    # 건너뜀 (낮은 점수 등) - 중복 방지용으로 마킹
                    self._mark_orchestrated(task_id, "skipped")
                    processed_count += 1

            # AD 완료 → CE 태스크 생성
            elif agent_type == "AD" and task_type == "create_visual_concept":
                next_task_id = self._handle_ad_completed(task, result)
                self._mark_orchestrated(task_id, next_task_id)
                processed_count += 1

            # CE 완료 → Ralph 검증 → CD 태스크 생성
            elif agent_type == "CE" and task_type == "write_content":
                next_task_id = self._handle_ce_completed(task, result)
                self._mark_orchestrated(task_id, next_task_id)
                processed_count += 1

            # CD 완료 → ContentPublisher 호출 or CE 재작업
            elif agent_type == "CD" and task_type == "review_content":
                next_task_id = self._handle_cd_completed(task, result)
                self._mark_orchestrated(task_id, next_task_id)
                processed_count += 1

        if processed_count > 0:
            logger.info("[Orchestrator] %d개 태스크 처리 완료", processed_count)

        return processed_count

    def _handle_sa_completed(self, task: Dict, result: Dict) -> Optional[str]:
        """SA 완료 → AD 태스크 생성"""
        sa_result = result.get("result", {})
        strategic_score = sa_result.get("strategic_score", 0)

        # 전략 점수 50 미만이면 파이프라인 스킵
        if strategic_score < 50:
            logger.info("[Orchestrator] SA 점수 %s < 50, 파이프라인 스킵: %s", strategic_score, task['task_id'])
            return None

        signal_id = task.get("payload", {}).get("signal_id", "unknown")

        ad_payload = {
            "signal_id": signal_id,
            "sa_result": sa_result,
            "themes": sa_result.get("themes", []),
            "key_insights": sa_result.get("key_insights", []),
            "strategic_score": strategic_score,
            "source_task_id": task["task_id"]
        }

        logger.info("[Orchestrator] SA→AD: signal=%s, score=%s", signal_id, strategic_score)
        return self._create_task("AD", "create_visual_concept", ad_payload)

    def _handle_ad_completed(self, task: Dict, result: Dict) -> str:
        """AD 완료 → CD 최종 리뷰 태스크 생성"""
        ad_result = result.get("result", {})
        payload = task.get("payload", {})
        signal_id = payload.get("signal_id", "unknown")
        sa_result = payload.get("sa_result", {})
        ce_result = payload.get("ce_result", {})
        ralph_score = payload.get("ralph_score", 0)

        cd_payload = {
            "signal_id": signal_id,
            "sa_result": sa_result,
            "ce_result": ce_result,
            "ad_result": ad_result,
            "ralph_score": ralph_score,
            "instagram_caption": ce_result.get("instagram_caption", ""),
            "hashtags": ce_result.get("hashtags", ""),
            "archive_essay": ce_result.get("archive_essay", ""),
            "source_task_id": task["task_id"]
        }

        logger.info("[Orchestrator] AD→CD: signal=%s", signal_id)
        return self._create_task("CD", "review_content", cd_payload)

    def _handle_ce_completed(self, task: Dict, result: Dict) -> str:
        """CE 완료 → Ralph QA 인라인 → AD 태스크 생성 (또는 CE 재작업)"""
        ralph_score = self._ralph_score(result)
        signal_id = task.get("payload", {}).get("signal_id", "unknown")
        sa_result = task.get("payload", {}).get("sa_result", {})
        ce_result = result.get("result", {})

        logger.info("[Orchestrator] CE 완료, Ralph 점수: %s/100 (signal=%s)", ralph_score, signal_id)

        # Ralph < RALPH_PASS_SCORE → CE 재작업 (최대 2회)
        retry_count = self._get_ce_retry_count(signal_id)
        if ralph_score < self.RALPH_PASS_SCORE and retry_count < self.MAX_CE_RETRIES:
            logger.info("[Orchestrator] Ralph %s<%s → CE 재작업 (%d/%d)", ralph_score, self.RALPH_PASS_SCORE, retry_count + 1, self.MAX_CE_RETRIES)
            retry_payload = {
                **task.get("payload", {}),
                "retry_count": retry_count + 1,
                "ralph_score": ralph_score,
                "previous_output": ce_result,
                "feedback": "품질 점수 %d/100. 에세이(500-800자)와 캡션(300자 이내)을 더 충실히." % ralph_score
            }
            new_task_id = self._create_task("CE", "write_content", retry_payload)
            self._orchestrated["retry_%s_%d" % (signal_id, retry_count)] = {
                "orchestrated_at": datetime.now().isoformat(),
                "next_task_id": new_task_id,
                "signal_id": signal_id,
                "retry_for": "CE"
            }
            self._save_orchestrated()
            return new_task_id

        # Ralph 통과 → AD 시각 컨셉 태스크 생성
        ad_payload = {
            "signal_id": signal_id,
            "sa_result": sa_result,
            "ce_result": ce_result,
            "ralph_score": ralph_score,
            "themes": ce_result.get("themes", sa_result.get("themes", [])),
            "key_insights": sa_result.get("key_insights", []),
            "essay_preview": str(ce_result.get("archive_essay", ""))[:500],
            "source_task_id": task["task_id"]
        }

        logger.info("[Orchestrator] CE→AD: signal=%s, ralph=%s", signal_id, ralph_score)
        return self._create_task("AD", "create_visual_concept", ad_payload)

    def _handle_cd_completed(self, task: Dict, result: Dict) -> str:
        """CD 완료 → 승인 시 ContentPublisher, 거절 시 CE 재작업"""
        cd_result = result.get("result", {})
        approved = cd_result.get("approved", False)
        feedback = cd_result.get("feedback", "")
        signal_id = task.get("payload", {}).get("signal_id", "unknown")
        ce_result = task.get("payload", {}).get("ce_result", {})

        if approved:
            logger.info("[Orchestrator] CD 승인! ContentPublisher 호출: signal=%s", signal_id)
            publisher_payload = {
                "signal_id": signal_id,
                "sa_result": task.get("payload", {}).get("sa_result", {}),
                "ad_result": task.get("payload", {}).get("ad_result", {}),
                "ce_result": ce_result,
                "cd_result": cd_result,
                "instagram_caption": task.get("payload", {}).get("instagram_caption", ""),
                "hashtags": task.get("payload", {}).get("hashtags", ""),
                "archive_essay": task.get("payload", {}).get("archive_essay", ""),
                "source_task_id": task["task_id"]
            }
            # ContentPublisher는 별도 태스크가 아닌 직접 호출
            self._trigger_content_publisher(publisher_payload)
            return f"published_{signal_id}"
        else:
            # CE 재작업 (피드백 포함)
            retry_count = self._get_ce_retry_count(signal_id)
            if retry_count >= self.MAX_CE_RETRIES:
                logger.warning("[Orchestrator] CE 재작업 최대 횟수 초과, 파이프라인 종료: signal=%s", signal_id)
                return f"max_retry_{signal_id}"

            logger.info("[Orchestrator] CD 거절 → CE 재작업: %s", feedback[:100])
            retry_payload = {
                **task.get("payload", {}),
                "retry_count": retry_count + 1,
                "cd_feedback": feedback,
                "previous_output": ce_result,
                "feedback": f"CD 검토 결과: {feedback}"
            }
            new_task_id = self._create_task("CE", "write_content", retry_payload)
            self._orchestrated[f"cd_retry_{signal_id}_{retry_count}"] = {
                "orchestrated_at": datetime.now().isoformat(),
                "next_task_id": new_task_id,
                "signal_id": signal_id,
                "retry_for": "CE"
            }
            self._save_orchestrated()
            return new_task_id

    def _trigger_content_publisher(self, payload: Dict):
        """ContentPublisher 직접 트리거 (비동기 태스크로 실행)"""
        try:
            from core.system.content_publisher import ContentPublisher
            publisher = ContentPublisher(base_path=self.base_path)
            # 비동기 실행 (블로킹 방지)
            import threading
            t = threading.Thread(target=publisher.publish, args=(payload,), daemon=True)
            t.start()
            logger.info("[Orchestrator] ContentPublisher 스레드 시작: %s", payload.get('signal_id'))
        except ImportError:
            logger.warning("[Orchestrator] ContentPublisher 미구현 - 스킵")
        except Exception as e:
            logger.error("[Orchestrator] ContentPublisher 오류: %s", e)

    def _process_all_completed(self) -> Dict[str, int]:
        """완료 태스크 1회 로드 → 에이전트별 dispatch. 디스크 스캔 1회."""
        tasks = self._load_completed_tasks()
        counts = {"SA": 0, "CE": 0, "AD": 0, "CD": 0}

        for task in tasks:
            task_id = task.get("task_id", "")
            if self._is_orchestrated(task_id):
                continue
            if task.get("status") != "completed":
                continue

            agent = task.get("agent_type", "")
            task_type = task.get("task_type", "")
            result = task.get("result", {}) or {}

            if agent == "SA" and task_type in ("analyze_signal", "analyze"):
                self._handle_sa_corpus(task, result)
                counts["SA"] += 1

            elif agent == "CE" and task_type in ("write_content", "write_corpus_essay"):
                next_id = self._handle_ce_completed(task, result)
                self._mark_orchestrated(task_id, next_id)
                counts["CE"] += 1

            elif agent == "AD" and task_type == "create_visual_concept":
                next_id = self._handle_ad_completed(task, result)
                self._mark_orchestrated(task_id, next_id)
                counts["AD"] += 1

            elif agent == "CD" and task_type == "review_content":
                next_id = self._handle_cd_completed(task, result)
                self._mark_orchestrated(task_id, next_id)
                counts["CD"] += 1

        return counts

    def _handle_sa_corpus(self, task: Dict, result: Dict):
        """SA 완료 → Corpus 누적 (인라인, _process_sa_completed_only 대체)"""
        from core.system.corpus_manager import CorpusManager

        task_id = task.get("task_id", "")
        sa_result = result.get("result", {})
        signal_id = task.get("payload", {}).get("signal_id", "")
        signal_path = task.get("payload", {}).get("signal_path", "")

        signal_data = {}
        if signal_path:
            try:
                signal_data = json.loads(Path(signal_path).read_text())
            except Exception:
                signal_data = task.get("payload", {})

        try:
            corpus = CorpusManager()
            corpus.add_entry(signal_id, sa_result, signal_data)
            logger.info("[Orchestrator] SA→Corpus: %s", signal_id)
        except Exception as e:
            logger.warning("[Orchestrator] Corpus 누적 실패: %s", e)

        self._mark_orchestrated(task_id, "corpus_accumulated")

    async def run_forever(self, interval_seconds: int = 30):
        """무한 폴링 루프 — 전체 파이프라인 자동 체인"""
        self._running = True
        logger.info("[Orchestrator] 시작. 폴링 간격: %d초", interval_seconds)

        while self._running:
            try:
                # Step 1: 신규 신호 스캔 → SA 태스크 생성
                new_signals = self._scan_new_signals()

                # Step 2: 완료 태스크 일괄 처리 (1회 디스크 스캔)
                counts = self._process_all_completed()

                total = new_signals + sum(counts.values())
                if total > 0:
                    logger.info(
                        "[Orchestrator] 사이클: 신호=%d SA=%d CE=%d AD=%d CD=%d",
                        new_signals, counts["SA"], counts["CE"],
                        counts["AD"], counts["CD"]
                    )
            except Exception as e:
                logger.error("[Orchestrator] 오류: %s", e, exc_info=True)

            await asyncio.sleep(interval_seconds)

    def stop(self):
        self._running = False
        logger.info("[Orchestrator] 정지")


def main():
    """독립 실행 진입점"""
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
        ]
    )

    # base_path: GCP VM은 실행 디렉토리, 컨테이너는 /app
    base = Path("/app") if Path("/app").exists() else Path(".")
    orchestrator = PipelineOrchestrator(base_path=base)
    asyncio.run(orchestrator.run_forever(interval_seconds=30))


if __name__ == "__main__":
    main()
