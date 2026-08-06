from app.models.response import ExecutionPreview, QueryQualityResult, ValidationResult


class ExecutionPreviewService:
    def build(self, query: str | None, validation: ValidationResult | None, quality: QueryQualityResult | None) -> ExecutionPreview:
        if not query or not validation or not quality:
            return ExecutionPreview(status="unsupported", is_read_only=None, risk_level="high", blocked_reasons=["생성 또는 검증을 완료하지 못했습니다."])
        blocked = [issue.message for issue in validation.errors]
        if validation.requires_admin or quality.risk_level == "critical":
            blocked.append("관리자 권한 또는 치명적 위험 신호가 있습니다.")
        if blocked:
            return ExecutionPreview(status="blocked", is_read_only=False if validation.requires_admin else True, risk_level=quality.risk_level, blocked_reasons=blocked, checks_before_execution=["문법과 카탈로그 오류를 해결하세요."])
        is_forwarding = "stream forward=t" in query.lower()
        confirmation = quality.risk_level in {"medium", "high"} or is_forwarding
        message = "데이터를 스트림으로 전달합니다. 대상과 범위를 확인한 뒤 수동 실행하세요." if is_forwarding else ("조회 범위가 넓습니다. 기간과 결과 수를 확인한 뒤 수동 실행하세요." if confirmation else "Logpresso에서 복사한 쿼리를 수동 실행하세요.")
        return ExecutionPreview(status="requires_confirmation" if confirmation else "preview_ready", is_read_only=not is_forwarding, risk_level=quality.risk_level, recommended_limit=100, recommended_timeout_seconds=30, requires_user_confirmation=confirmation, confirmation_message=message, checks_before_execution=["실제 실행 전 대상 테이블과 기간을 확인하세요."])
