"""
Essay Quality Validator — Ralph Loop 기반 언어품질 검증
Standards: directives/sage_architect.md §6.5
"""

import re
import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


class EssayQualityValidator:
    """
    WOOHWAHAE 에세이 언어품질 검증기

    4단계 Ralph Loop:
    1. 시대 초월성 (Timelessness)
    2. 논리 일관성 (Logical Coherence)
    3. 클리셰/약한 표현 제거 (Cliché Elimination)
    4. 리듬/호흡 (Rhythm & Density)

    만점 100점, 기준선 90점
    """

    # Loop 1: 시대 초월성 금지 패턴
    TEMPORAL_PATTERNS = [
        r'현재',
        r'요즘',
        r'최근',
        r'오늘날',
        r'이\s*시대',
        r'이\s*시기',
        r'202\d',  # 2020-2029
        r'트렌드',
        r'유행',
        r'밀레니얼',
        r'MZ\s*세대',
    ]

    # Loop 3-A: 빈 공감 동사
    EMPTY_SYMPATHY = [
        r'중요합니다',
        r'필요합니다',
        r'생각합니다',
        r'가능합니다',
        r'좋습니다',
        r'나쁩니다',
    ]

    # Loop 3-B: 평면적 공동체 언어
    FLAT_COMMUNITY = [
        r'여러분',
        r'우리\s*모두',
        r'함께',
        r'같이',
        r'공동체',
        r'소통',
        r'공유',
        r'연결',
        r'관계',
    ]

    # Loop 3-C: 강조 부사
    EMPHASIS_ADVERBS = [
        r'정말',
        r'너무',
        r'매우',
        r'아주',
        r'정말로',
        r'진짜',
        r'엄청',
        r'굉장히',
    ]

    # Loop 4: 약한 명사 (경고용, 자동 감점 아님)
    WEAK_NOUNS = [
        r'인상',
        r'느낌',
        r'생각',
    ]

    def __init__(self):
        self.results = {
            "score": 0,
            "loops": {},
            "issues": []
        }

    def validate(self, text: str) -> Dict:
        """
        에세이 전체 검증 실행

        Args:
            text: 에세이 본문 (HTML 태그 제거된 순수 텍스트)

        Returns:
            {
                "score": 0-100,
                "loops": {
                    "timelessness": {"score": 25, "issues": []},
                    "logic": {"score": 25, "issues": []},
                    "cliche": {"score": 25, "issues": []},
                    "rhythm": {"score": 25, "issues": []}
                },
                "issues": [...]  # 전체 이슈 리스트
            }
        """
        self.results = {"score": 0, "loops": {}, "issues": []}

        # Loop 1: 시대 초월성
        self.results["loops"]["timelessness"] = self._check_timelessness(text)

        # Loop 2: 논리 일관성 (휴리스틱 기반 — 완전 자동화 어려움)
        self.results["loops"]["logic"] = self._check_logic(text)

        # Loop 3: 클리셰 제거
        self.results["loops"]["cliche"] = self._check_cliche(text)

        # Loop 4: 리듬/호흡 (경고만, 점수는 기본 부여)
        self.results["loops"]["rhythm"] = self._check_rhythm(text)

        # 총점 계산
        total = sum(loop["score"] for loop in self.results["loops"].values())
        self.results["score"] = total

        # 전체 이슈 병합
        for loop_data in self.results["loops"].values():
            self.results["issues"].extend(loop_data.get("issues", []))

        return self.results

    def _check_timelessness(self, text: str) -> Dict:
        """Loop 1: 시대 초월성 검증"""
        issues = []

        for pattern in self.TEMPORAL_PATTERNS:
            matches = list(re.finditer(pattern, text))
            for match in matches:
                # "지금" 예외 처리
                if pattern == r'지금':
                    continue

                context = self._get_context(text, match.start(), 40)
                issues.append({
                    "type": "temporal",
                    "pattern": pattern,
                    "match": match.group(),
                    "context": context
                })

        # 채점
        count = len(issues)
        if count == 0:
            score = 25
        elif count <= 2:
            score = 15
        else:
            score = 0

        return {"score": score, "issues": issues, "count": count}

    def _check_logic(self, text: str) -> Dict:
        """
        Loop 2: 논리 일관성 검증

        휴리스틱:
        - 같은 문장 구조 3회 이상 반복 (정규식 패턴 매칭)
        - "~입니다. ~입니다. ~입니다." 3연속
        """
        issues = []

        # 패턴 1: "~입니다" 3연속
        pattern = r'([\w\s가-힣]+입니다\.)\s*([\w\s가-힣]+입니다\.)\s*([\w\s가-힣]+입니다\.)'
        matches = list(re.finditer(pattern, text))
        for match in matches:
            issues.append({
                "type": "repetitive_structure",
                "match": match.group()[:80],
                "context": "같은 종결어미 3연속"
            })

        # 패턴 2: 같은 부정문 2회 반복
        # 예: "~가 아닙니다. (중략) ~가 아닙니다."
        negative_pattern = r'(\S+)\s*(이|가)\s*아닙니다'
        negatives = list(re.finditer(negative_pattern, text))
        if len(negatives) >= 2:
            # 간단 휴리스틱: 같은 주어 2회 이상
            subjects = [m.group(1) for m in negatives]
            duplicates = [s for s in subjects if subjects.count(s) >= 2]
            if duplicates:
                issues.append({
                    "type": "redundant_negation",
                    "subject": duplicates[0],
                    "context": f"'{duplicates[0]}(이)가 아닙니다' 2회 이상 반복"
                })

        # 채점
        count = len(issues)
        if count == 0:
            score = 25
        elif count == 1:
            score = 15
        else:
            score = 0

        return {"score": score, "issues": issues, "count": count}

    def _check_cliche(self, text: str) -> Dict:
        """Loop 3: 클리셰/약한 표현 제거"""
        issues = []

        # A. 빈 공감 동사
        for pattern in self.EMPTY_SYMPATHY:
            matches = list(re.finditer(pattern, text))
            for match in matches:
                context = self._get_context(text, match.start(), 40)
                issues.append({
                    "type": "empty_sympathy",
                    "pattern": pattern,
                    "match": match.group(),
                    "context": context
                })

        # B. 평면적 공동체 언어 ("우리" 제외)
        for pattern in self.FLAT_COMMUNITY:
            if pattern == r'우리':  # 예외
                continue
            matches = list(re.finditer(pattern, text))
            for match in matches:
                context = self._get_context(text, match.start(), 40)
                issues.append({
                    "type": "flat_community",
                    "pattern": pattern,
                    "match": match.group(),
                    "context": context
                })

        # C. 강조 부사
        for pattern in self.EMPHASIS_ADVERBS:
            matches = list(re.finditer(pattern, text))
            for match in matches:
                context = self._get_context(text, match.start(), 40)
                issues.append({
                    "type": "emphasis_adverb",
                    "pattern": pattern,
                    "match": match.group(),
                    "context": context
                })

        # 채점
        count = len(issues)
        if count == 0:
            score = 25
        elif count <= 3:
            score = 15
        else:
            score = 0

        return {"score": score, "issues": issues, "count": count}

    def _check_rhythm(self, text: str) -> Dict:
        """
        Loop 4: 리듬/호흡 검증

        주관적 영역이라 경고만 생성, 점수는 기본 부여
        """
        issues = []

        # 약한 명사 감지 (경고)
        for pattern in self.WEAK_NOUNS:
            matches = list(re.finditer(pattern, text))
            for match in matches:
                context = self._get_context(text, match.start(), 30)
                issues.append({
                    "type": "weak_noun",
                    "pattern": pattern,
                    "match": match.group(),
                    "context": context,
                    "severity": "warning"  # 자동 감점 X
                })

        # 기본 점수 부여 (약한 명사 3개 이상 시 감점)
        count = len(issues)
        if count == 0:
            score = 25
        elif count <= 2:
            score = 25  # 경고만
        elif count <= 5:
            score = 20
        else:
            score = 15

        return {"score": score, "issues": issues, "count": count}

    def _get_context(self, text: str, pos: int, length: int = 40) -> str:
        """매치 위치 주변 컨텍스트 추출"""
        start = max(0, pos - length)
        end = min(len(text), pos + length)
        return "..." + text[start:end] + "..."

    def format_report(self, result: Dict) -> str:
        """검증 결과 보고서 포맷팅"""
        lines = [
            "━━━ Essay Quality Report ━━━",
            f"Total Score: {result['score']}/100",
            ""
        ]

        for loop_name, loop_data in result["loops"].items():
            lines.append(f"{loop_name.upper()}: {loop_data['score']}/25")
            if loop_data["issues"]:
                for issue in loop_data["issues"][:3]:  # 최대 3개만
                    lines.append(f"  - {issue['type']}: {issue.get('match', '')}")

        lines.append("")
        lines.append(f"Total Issues: {len(result['issues'])}")

        return "\n".join(lines)


# CLI 테스트용
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python essay_quality_validator.py <text_file>")
        sys.exit(1)

    with open(sys.argv[1], 'r', encoding='utf-8') as f:
        text = f.read()

    validator = EssayQualityValidator()
    result = validator.validate(text)
    print(validator.format_report(result))
