import json
import hashlib
import re
from datetime import datetime, timezone

import streamlit as st

from app.core.config import settings
from app.core.ui_auth import LoginAttemptStore, authenticate, hash_password, load_users, session_expired, verify_password
from app.models.request import Catalog, CatalogField, CatalogTable, FeedbackRequest, GenerateQueryRequest, RequestContext
from app.models.dashboard import DashboardDefinition, DashboardDesignRequest, DashboardThreshold, LogpressoTarget
from app.services.catalog_service import CatalogService
from app.services.catalog_import import CatalogImportError, catalog_from_csv_bytes
from app.services.feedback_store import FeedbackStore
from app.services.alias_store import AliasImportError, AliasStore
from app.services.audit_store import AuditStore
from app.services.generation_comparison import append_comparison_history, comparison_history_rows, compare_generation_results
from app.services.gold_set import compare_llm_context_limits, run_gold_set
from app.services.session_hints import merge_hints, remove_hint
from app.services.execution_preview import ExecutionPreviewService
from app.services.indexer import DocumentIndex
from app.services.quality_analyzer import QueryQualityAnalyzer
from app.services.query_generator import QueryGenerator
from app.services.intent_parser import IntentParser
from app.services.llm.mock_provider import MockProvider
from app.services.query_validator import QueryValidator
from app.services.retriever import Retriever
from app.services.query_suggestions import apply_safe_suggestion
from app.services.query_history import append_version, query_diff
from app.services.ollama_status import check_ollama
from app.services.metrics_store import MetricsStore, metric_label, operational_overview
from app.services.store_schema_knowledge import StoreSchemaKnowledge
from app.services.store_schema_update import StoreSchemaUpdate, StoreSchemaUpdateError
from app.services.store_table_mapping import StoreTableMapping
from app.services.dashboard_designer import DashboardDesigner, dashboard_to_yaml
from app.services.dashboard_operations import analyze_dashboard, deployment_plan
from app.services.dashboard_store import DashboardStore


st.set_page_config(page_title="로그프레소 자연어 쿼리 생성기", layout="wide")


def require_login() -> None:
    if not settings.ui_auth_enabled:
        return
    try:
        users = load_users(settings.ui_users_json)
    except ValueError:
        st.error("로그인 설정이 올바르지 않습니다. 관리자에게 문의하세요.")
        st.stop()
    now = datetime.now(timezone.utc)
    attempt_store = LoginAttemptStore(settings.auth_db_path, settings.auth_max_failures, settings.auth_lockout_minutes)
    attempt_store.seed_users(users)
    users = attempt_store.users()
    if st.session_state.get("authenticated") and session_expired(
        st.session_state.get("auth_last_seen"), settings.session_idle_minutes, now=now
    ):
        for key in list(st.session_state):
            del st.session_state[key]
        st.warning("장시간 사용하지 않아 로그아웃되었습니다.")
    if st.session_state.get("authenticated"):
        st.session_state["auth_last_seen"] = now
        with st.sidebar:
            st.caption(f"사용자: {st.session_state['auth_username']} ({st.session_state['auth_role']})")
            if st.button("로그아웃", key="logout_button"):
                attempt_store.record_event("logout", st.session_state["auth_username"], st.session_state["auth_username"])
                for key in list(st.session_state):
                    del st.session_state[key]
                st.rerun()
        return
    st.title("로그프레소 쿼리 생성기 로그인")
    with st.form("login_form"):
        username = st.text_input("사용자 이름")
        password = st.text_input("비밀번호", type="password")
        submitted = st.form_submit_button("로그인", type="primary")
    if submitted:
        locked_seconds = attempt_store.locked_seconds(username, now=now)
        if locked_seconds:
            st.error(f"로그인 시도가 잠겼습니다. 약 {(locked_seconds + 59) // 60}분 후 다시 시도하세요.")
        else:
            result = authenticate(username, password, users)
        if not locked_seconds and result.ok:
            attempt_store.clear(username)
            attempt_store.record_event("login_success", result.username or username, result.username or username)
            st.session_state["authenticated"] = True
            st.session_state["auth_username"] = result.username
            st.session_state["auth_role"] = result.role
            st.session_state["auth_last_seen"] = now
            st.rerun()
        if not locked_seconds:
            newly_locked = attempt_store.record_failure(username, now=now)
            attempt_store.record_event("account_locked" if newly_locked else "login_failure", username)
            if newly_locked:
                st.error(f"로그인 실패 횟수를 초과해 {settings.auth_lockout_minutes}분 동안 잠겼습니다.")
            else:
                st.error("사용자 이름 또는 비밀번호가 올바르지 않습니다.")
    st.stop()


require_login()


def has_role(*roles: str) -> bool:
    return not settings.ui_auth_enabled or st.session_state.get("auth_role") in roles


def render_account_management() -> None:
    if not settings.ui_auth_enabled:
        return
    store = LoginAttemptStore(settings.auth_db_path, settings.auth_max_failures, settings.auth_lockout_minutes)
    username = st.session_state["auth_username"]
    with st.sidebar.expander("내 비밀번호 변경"):
        with st.form("change_own_password"):
            current = st.text_input("현재 비밀번호", type="password")
            new = st.text_input("새 비밀번호", type="password")
            confirm = st.text_input("새 비밀번호 확인", type="password")
            change = st.form_submit_button("비밀번호 변경")
        if change:
            account = store.users().get(username)
            if not account or not verify_password(current, account.password_hash):
                st.error("현재 비밀번호가 올바르지 않습니다.")
            elif len(new) < 8:
                st.error("새 비밀번호는 8자 이상이어야 합니다.")
            elif new != confirm:
                st.error("새 비밀번호 확인이 일치하지 않습니다.")
            else:
                store.set_password(username, hash_password(new), actor=username)
                st.success("비밀번호를 변경했습니다.")
    if not has_role("admin"):
        return
    with st.sidebar.expander("사용자 계정 관리"):
        accounts = store.users(include_disabled=True)
        st.dataframe(
            [{"사용자": name, "권한": account.role, "활성": account.enabled} for name, account in accounts.items()],
            use_container_width=True,
            hide_index=True,
        )
        with st.form("save_ui_user"):
            target = st.text_input("사용자 이름")
            role = st.selectbox("권한", ["viewer", "editor", "admin"])
            password = st.text_input("새 비밀번호", type="password", help="기존 계정도 새 비밀번호를 입력해야 저장됩니다.")
            save = st.form_submit_button("계정 생성/수정")
        if save:
            if len(password) < 8:
                st.error("비밀번호는 8자 이상이어야 합니다.")
            else:
                try:
                    store.save_user(target, hash_password(password), role, actor=username)
                except ValueError as error:
                    st.error(str(error))
                else:
                    st.success("계정을 저장했습니다.")
                    st.rerun()
        unlock_target = st.selectbox("잠금 해제할 사용자", list(accounts), key="unlock_ui_user")
        if st.button("계정 잠금 해제", key="unlock_ui_user_button"):
            store.unlock(unlock_target, actor=username)
            st.success("로그인 잠금을 해제했습니다.")
        with st.expander("로그인/계정 감사 로그"):
            st.dataframe(
                [event.__dict__ for event in store.recent_events(100)], use_container_width=True, hide_index=True
            )


render_account_management()

index = DocumentIndex(settings.db_path)
status = index.status(settings.doc_path)
catalog_service = CatalogService(settings.catalog_path)
store_knowledge = StoreSchemaKnowledge.active(settings.store_schema_path)
store_mapping = StoreTableMapping(settings.store_table_mapping_path)


def load_uploaded_catalog(uploaded_file) -> Catalog | None:
    if uploaded_file is None:
        return None
    try:
        if uploaded_file.name.lower().endswith(".csv"):
            return catalog_from_csv_bytes(uploaded_file.getvalue())
        return Catalog.model_validate_json(uploaded_file.getvalue())
    except (ValueError, CatalogImportError) as error:
        st.sidebar.error(f"카탈로그 파일 오류: {error}")
        return None


def parse_request_catalog(schema_text: str) -> Catalog | None:
    tables: list[CatalogTable] = []
    for raw_line in schema_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        table_name, separator, raw_fields = line.partition(":")
        table_name = table_name.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", table_name):
            raise ValueError(f"테이블 이름 형식이 올바르지 않습니다: {table_name}")
        field_names = []
        if separator:
            field_names = [value.strip() for value in raw_fields.split(",") if value.strip()]
        invalid_fields = [name for name in field_names if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name)]
        if invalid_fields:
            raise ValueError(f"필드 이름 형식이 올바르지 않습니다: {', '.join(invalid_fields)}")
        tables.append(CatalogTable(table_name=table_name, fields=[CatalogField(field_name=name) for name in field_names]))
    return Catalog(tables=tables, source="unknown") if tables else None


def catalog_rows(catalog: Catalog | None) -> list[dict]:
    rows: list[dict] = []
    for table in (catalog.tables if catalog else []):
        if not table.fields:
            rows.append({"table_name": table.table_name, "field_name": "", "field_type": "unknown", "description": ""})
        for field in table.fields:
            rows.append(
                {
                    "table_name": table.table_name,
                    "field_name": field.field_name,
                    "field_type": field.field_type,
                    "description": field.description or "",
                }
            )
    return rows


def catalog_from_rows(rows, previous: Catalog | None) -> Catalog:
    if hasattr(rows, "to_dict"):
        rows = rows.to_dict(orient="records")
    tables: dict[str, CatalogTable] = {}
    seen_fields: set[tuple[str, str]] = set()
    for row in rows:
        table_name = str(row.get("table_name") or "").strip()
        field_name = str(row.get("field_name") or "").strip()
        if not table_name:
            continue
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", table_name):
            raise ValueError(f"테이블 이름 형식이 올바르지 않습니다: {table_name}")
        table = tables.setdefault(table_name, CatalogTable(table_name=table_name))
        if not field_name:
            continue
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", field_name):
            raise ValueError(f"필드 이름 형식이 올바르지 않습니다: {field_name}")
        key = (table_name, field_name)
        if key in seen_fields:
            raise ValueError(f"같은 테이블에 중복된 필드가 있습니다: {table_name}.{field_name}")
        seen_fields.add(key)
        table.fields.append(
            CatalogField(
                field_name=field_name,
                field_type=str(row.get("field_type") or "unknown").strip() or "unknown",
                description=str(row.get("description") or "").strip() or None,
            )
        )
    return Catalog(
        tables=list(tables.values()),
        catalog_version=previous.catalog_version if previous else None,
        updated_at=datetime.now(timezone.utc).isoformat(),
        source="manual",
        function_type_rules=previous.function_type_rules if previous else [],
    )

with st.sidebar:
    st.subheader("상태")
    st.write(f"LLM provider: `{settings.llm_provider}`")
    st.write(f"LLM model: `{settings.ollama_model if settings.llm_provider == 'ollama' else settings.openai_model}`")
    st.caption("모델 변경은 `.env`의 `OLLAMA_MODEL` 또는 `OPENAI_MODEL`을 바꾼 뒤 서버를 재시작하면 적용됩니다.")
    with st.expander("Ollama 상태 진단"):
        st.caption(f"URL: {settings.ollama_base_url} | 모델: {settings.ollama_model}")
        if st.button("Ollama 연결 점검"):
            st.session_state["ollama_status"] = check_ollama(settings.ollama_base_url, settings.ollama_model)
        if ollama_status := st.session_state.get("ollama_status"):
            if ollama_status["status"] == "reachable":
                st.success("Ollama 서버에 연결했습니다.")
            else:
                st.warning("Ollama 서버에 연결하지 못했습니다. 규칙 기반 생성은 계속 사용할 수 있습니다.")
            st.json(ollama_status)
        if last_error := st.session_state.get("response", {}).get("debug", {}).get("llm_error_type"):
            st.caption(f"최근 LLM fallback 사유: {last_error}")
    feedback_summary = FeedbackStore(settings.db_path).summary()
    unresolved_outcomes = feedback_summary.get("unresolved_outcomes", {})
    if feedback_summary["total"] or unresolved_outcomes:
        st.caption(f"저장된 피드백: {feedback_summary['total']}건 | 문제 유형: {feedback_summary['issue_types']}")
        if unresolved_outcomes:
            labels = {"needs_clarification": "확인 질문 필요", "unsupported": "지원 불가"}
            st.caption("자동 수집된 미해결 요청: " + ", ".join(f"{labels.get(status, status)} {count}건" for status, count in unresolved_outcomes.items()))
        candidates = FeedbackStore(settings.db_path).improvement_candidates()
        if candidates:
            with st.expander("피드백 기반 개선 후보"):
                for candidate in candidates:
                    st.write(f"- {candidate['title']} ({candidate['count']}건)")
                    st.caption(candidate["suggestion"])
        st.download_button(
            "개선 리포트 다운로드",
            data=json.dumps(FeedbackStore(settings.db_path).improvement_report(), ensure_ascii=False, indent=2),
            file_name="query-improvement-report.json",
            mime="application/json",
        )
    st.write(f"문서 인덱스: {'완료' if status['indexed'] else '미생성'}")
    st.write(f"문서 변경됨: {'예' if status['stale'] else '아니오'}")
    st.write(f"청크 수: {status['chunk_count']}")
    if settings.doc_path.exists() and status["indexed"] and not status["stale"] and status["chunk_count"]:
        st.success("생성 준비 상태: 준비됨")
    else:
        st.warning("생성 준비 상태: 기준 문서 또는 인덱스를 확인하세요.")
    product = st.selectbox("로그프레소 라이선스 제품군", ["ENT", "STD", "SNR", "FRS"], index=0)
    generation_mode = st.selectbox(
        "생성 모드",
        ["자동", "빠른 규칙 기반", "Ollama 보조"],
        index=1,
        help="빠른 규칙 기반은 로컬 모델 호출 없이 안전한 템플릿을 우선합니다.",
    )
    version = st.text_input("버전")
    known_tables = st.text_area("테이블 힌트 (선택)", placeholder="예: firewall_logs")
    known_fields = st.text_area("필드 힌트 (선택)", placeholder="예: src_ip\naction\n_time")
    known_loggers = st.text_area("logger 힌트 (선택)", placeholder="예: local\\firewall_logger")
    known_streams = st.text_area("stream 힌트 (선택)", placeholder="예: firewall_stream")
    selected_store_product = ""
    selected_store_schema = ""
    mapped_store_table = None
    with st.expander("운영 관리 · Logpresso Store 스키마", expanded=False):
        store_status = store_knowledge.status()
        col1, col2, col3 = st.columns(3)
        col1.metric("제품", store_status.get("products", 0))
        col2.metric("스키마", store_status.get("schemas", 0))
        col3.metric("상세 필드", store_status.get("fields", 0))
        st.caption(
            f"버전 {store_status.get('version') or '미지정'} · Raw 형식 {store_status.get('raw_formats', 0)}개 · "
            f"필드 미공개 스키마 {store_status.get('schemas_without_fields', 0)}개"
        )
        store_search = st.text_input("제품·스키마 검색", placeholder="예: 포티게이트, 웹필터, SQL 감사")
        search_results = store_knowledge.search(store_search, 30) if store_search.strip() else []
        if search_results:
            st.dataframe(search_results, use_container_width=True, hide_index=True)
        products = store_knowledge.payload.get("products", [])
        filtered_products = list(dict.fromkeys(item["product"] for item in search_results)) if search_results else [
            str(item.get("name")) for item in products
        ]
        selected_store_product = st.selectbox("Store 제품", [""] + filtered_products)
        selected_product_data = next(
            (item for item in products if item.get("name") == selected_store_product), None
        )
        schema_options = [str(item.get("name")) for item in (selected_product_data or {}).get("schemas", [])]
        selected_store_schema = st.selectbox("Store 스키마", [""] + schema_options)
        mapped_store_table = store_mapping.resolve(selected_store_product, selected_store_schema or None)
        mapping_table = st.text_input(
            "실제 Logpresso 테이블",
            value=mapped_store_table or "",
            placeholder="예: waf_events",
        )
        product_default = st.checkbox("제품 전체 기본 테이블로 저장", value=not bool(selected_store_schema))
        if st.button("테이블 매핑 저장", disabled=not selected_store_product or not has_role("editor", "admin")):
            try:
                store_mapping.save(
                    selected_store_product,
                    mapping_table,
                    None if product_default else selected_store_schema or None,
                )
            except ValueError as error:
                st.error(str(error))
            else:
                st.success("테이블 매핑을 저장했습니다.")
                st.rerun()
        mappings = store_mapping.list()
        if mappings:
            st.dataframe(mappings, use_container_width=True, hide_index=True)
        st.download_button(
            "테이블 매핑 CSV 다운로드",
            store_mapping.export_csv(),
            file_name="store-table-mappings.csv",
            mime="text/csv",
        )
        mapping_file = st.file_uploader("테이블 매핑 CSV 일괄 등록", type=["csv"], key="store_mapping_csv")
        if mapping_file is not None and st.button(
            "매핑 CSV 적용", disabled=not has_role("editor", "admin")
        ):
            try:
                imported_mappings = store_mapping.import_csv(mapping_file.getvalue())
            except ValueError as error:
                st.error(str(error))
            else:
                st.success(f"테이블 매핑 {len(imported_mappings)}개를 반영했습니다.")
                st.rerun()

        if selected_store_product:
            readiness = store_knowledge.preflight(
                selected_store_product, selected_store_schema or None, mapped_store_table
            )
            if readiness["ready"]:
                st.success("선택한 스키마는 쿼리 생성 준비가 완료되었습니다.")
            else:
                issue_labels = {
                    "fields_unavailable": "상세 필드 미공개",
                    "table_mapping_missing": "실제 테이블 매핑 필요",
                    "unknown_schema": "알 수 없는 스키마",
                }
                st.warning(" · ".join(issue_labels.get(item, item) for item in readiness["issues"]))

        missing_coverage = store_knowledge.coverage(missing_only=True)
        with st.expander(f"필드 미공개 우선 보강 목록 {len(missing_coverage)}개"):
            st.dataframe(missing_coverage, use_container_width=True, hide_index=True)

        store_file = st.file_uploader("Store 카탈로그 Excel 업데이트", type=["xlsx"], key="store_schema_xlsx")
        if store_file is not None:
            updater = StoreSchemaUpdate(settings.store_schema_path)
            try:
                candidate = updater.parse_xlsx(store_file.getvalue(), store_file.name)
                comparison = updater.compare(
                    updater.current(StoreSchemaKnowledge.bundled().payload), candidate
                )
            except StoreSchemaUpdateError as error:
                st.error(str(error))
            else:
                st.json(comparison)
                confirmed = st.checkbox("변경 내역을 확인했습니다.", key="store_schema_apply_confirmed")
                if st.button(
                    "Store 카탈로그 적용",
                    disabled=not confirmed or not has_role("admin"),
                ):
                    updater.save(candidate)
                    st.success("Store 카탈로그를 적용하고 이전 파일을 백업했습니다.")
                    st.rerun()

        raw_formats = (selected_product_data or {}).get("raw_formats", [])
        raw_line = st.text_area(
            "Raw Syslog 샘플",
            key="store_raw_sample",
            help="화면에서만 분석하며 자동 저장하지 않습니다. 제품을 선택하지 않아도 형식 후보를 찾습니다.",
        )
        if st.button("Raw 제품·형식 자동 판별", disabled=not raw_line):
            detected = store_knowledge.detect_raw(raw_line, selected_store_product or None)
            if detected:
                st.dataframe(detected, use_container_width=True, hide_index=True)
            else:
                st.warning("비교할 수 있는 공개 Raw 양식이 없습니다.")
        if raw_formats:
            raw_type = st.selectbox("Raw 로그 유형", [str(item.get("log_type")) for item in raw_formats])
            if st.button("Raw 형식 검증") and raw_line:
                raw_result = store_knowledge.validate_raw(selected_store_product, raw_type, raw_line)
                if raw_result.get("valid"):
                    st.success(f"필드 수 {raw_result['actual_fields']}개가 공개 형식과 일치합니다.")
                else:
                    st.warning(
                        f"예상 {raw_result.get('expected_fields', 0)}개 / 실제 {raw_result.get('actual_fields', 0)}개"
                    )
                st.json(raw_result)
    with st.expander("업무 별칭 관리"):
        alias_store = AliasStore(settings.db_path)
        alias_file = st.file_uploader("별칭 CSV 가져오기", type=["csv"], key="alias_csv_import")
        st.caption("CSV 열: phrase,target,kind,scope (kind와 scope는 선택)")
        alias_preview = []
        if alias_file is not None:
            try:
                alias_preview = alias_store.preview_csv_bytes(alias_file.getvalue())
            except AliasImportError as error:
                st.error(f"별칭 CSV 오류: {error}")
            else:
                st.dataframe(alias_preview, use_container_width=True, hide_index=True)
        import_confirmed = st.checkbox("미리보기와 변경 대상이 맞는지 확인했습니다.", key="alias_csv_import_confirmed")
        if alias_file is not None and st.button("별칭 CSV 저장", disabled=not alias_preview or not import_confirmed or not has_role("editor", "admin")):
            try:
                count = alias_store.import_csv_bytes(alias_file.getvalue())
            except AliasImportError as error:
                st.error(f"별칭 CSV 오류: {error}")
            else:
                st.success(f"{count}개 별칭을 저장했습니다.")
                st.rerun()
        alias_phrase = st.text_input("업무 표현", key="alias_phrase", placeholder="예: 내부 방화벽")
        alias_target = st.text_input("테이블 또는 필드", key="alias_target", placeholder="예: corp_firewall_logs")
        alias_kind = st.selectbox("별칭 종류", ["table", "field"], key="alias_kind")
        alias_scope = st.selectbox("적용 범위", ["공통", "ENT", "STD", "SNR", "FRS"], key="alias_scope")
        if st.button("별칭 저장", disabled=not has_role("editor", "admin")):
            try:
                alias_store.save(alias_phrase, alias_target, alias_kind, "" if alias_scope == "공통" else alias_scope)
            except ValueError as error:
                st.error(str(error))
            else:
                st.success("별칭을 저장했습니다.")
                st.rerun()
        aliases = alias_store.list(product)
        conflicts = alias_store.diagnostics()
        if conflicts:
            st.warning("같은 업무 표현이 여러 대상으로 등록되어 있습니다.")
            st.dataframe(conflicts, use_container_width=True, hide_index=True)
        if aliases:
            st.dataframe(aliases, use_container_width=True, hide_index=True)
            st.download_button(
                "별칭 CSV 다운로드",
                data=alias_store.export_csv(product),
                file_name="logpresso-aliases.csv",
                mime="text/csv",
            )
            alias_to_delete = st.selectbox("삭제할 별칭", [""] + [f"{item['kind']}: {item['phrase']}" for item in aliases])
            if st.button("선택 별칭 삭제", disabled=not has_role("editor", "admin")) and alias_to_delete:
                kind, phrase = alias_to_delete.split(": ", 1)
                alias_store.delete(phrase, kind)
                st.rerun()
    with st.expander("이번 세션에서 기억한 힌트"):
        learned_tables = st.session_state.get("learned_tables", [])
        learned_fields = st.session_state.get("learned_fields", [])
        if learned_tables or learned_fields:
            st.write("테이블: " + ", ".join(learned_tables or ["없음"]))
            st.write("필드: " + ", ".join(learned_fields or ["없음"]))
            hint_kind = st.selectbox("\uc120\ud0dd\ud560 \uae30\uc5b5 \ud78c\ud2b8 \uc885\ub958", ["table", "field"], key="session_hint_kind")
            hint_options = learned_tables if hint_kind == "table" else learned_fields
            hint_to_remove = st.selectbox("\uc120\ud0dd\ud560 \uae30\uc5b5 \ud78c\ud2b8", [""] + hint_options, key="session_hint_to_remove")
            if st.button("\uc120\ud0dd \ud78c\ud2b8 \uc0ad\uc81c") and hint_to_remove:
                state_key = "learned_tables" if hint_kind == "table" else "learned_fields"
                st.session_state[state_key] = remove_hint(st.session_state.get(state_key, []), hint_to_remove)
                st.rerun()
            clear_tables, clear_fields, clear_all = st.columns(3)
            if clear_tables.button("테이블 초기화"):
                st.session_state.pop("learned_tables", None)
                st.rerun()
            if clear_fields.button("필드 초기화"):
                st.session_state.pop("learned_fields", None)
                st.rerun()
            if clear_all.button("모두 초기화"):
                st.session_state.pop("learned_tables", None)
                st.session_state.pop("learned_fields", None)
                st.rerun()
        else:
            st.caption("수정 쿼리 재검증을 통과한 후 힌트를 기억하면 여기에 표시됩니다.")
    st.caption("비워 두어도 요청에 명시한 테이블과 필드를 생성에 사용합니다. 실제 존재 여부는 카탈로그가 있을 때 검증합니다.")
    request_schema = st.text_area("이번 요청 스키마 (선택)", placeholder="firewall_logs: src_ip, action, _time\napp_logs: message, host")
    try:
        request_schema_catalog = parse_request_catalog(request_schema)
    except ValueError as error:
        request_schema_catalog = None
        st.error(str(error))
    uploaded_catalog = st.file_uploader("카탈로그 파일", type=["json", "csv"])
    st.caption("CSV 필수 열: table_name, field_name, field_type, description | 선택 열: node, namespace, table_description, nullable")
    st.download_button(
        "CSV 카탈로그 템플릿 다운로드",
        data="table_name,node,namespace,table_description,field_name,field_type,nullable,description\nfirewall_logs,node-a,security,Firewall events,src_ip,ip,false,source address\nfirewall_logs,node-a,security,Firewall events,action,string,true,allow or deny\n",
        file_name="logpresso-catalog-template.csv",
        mime="text/csv",
    )
    uploaded_request_catalog = load_uploaded_catalog(uploaded_catalog)
    persisted_catalog = catalog_service.load() if uploaded_request_catalog is None else None
    active_catalog = uploaded_request_catalog or persisted_catalog
    if active_catalog:
        trust = CatalogService.trust_summary(active_catalog)
        source_column, version_column, updated_column = st.columns(3)
        source_column.metric("카탈로그 출처", trust["label"])
        version_column.metric("버전", active_catalog.catalog_version or "미지정")
        updated_column.metric("갱신 시점", active_catalog.updated_at or "미기록")
        st.caption(str(trust["detail"]))
        with st.expander("카탈로그 미리보기"):
            st.json(active_catalog.model_dump())
    else:
        st.info("카탈로그 없이 바로 시작할 수 있습니다. 요청에 실제 테이블·필드명을 직접 쓰면 그 이름을 우선 사용하고, 생성 전 해석 편집 또는 수정 쿼리 재검증으로 이번 세션의 힌트를 보완할 수 있습니다.")
    with st.expander("카탈로그 편집"):
        edited_rows = st.data_editor(
            catalog_rows(active_catalog),
            column_config={
                "table_name": st.column_config.TextColumn("테이블", required=True),
                "field_name": st.column_config.TextColumn("필드"),
                "field_type": st.column_config.TextColumn("타입"),
                "description": st.column_config.TextColumn("설명"),
            },
            num_rows="dynamic",
            use_container_width=True,
            key="catalog_editor",
        )
        if st.button("카탈로그 저장", disabled=not has_role("admin")):
            try:
                saved_catalog = catalog_service.save(catalog_from_rows(edited_rows, active_catalog))
            except ValueError as error:
                st.error(str(error))
            else:
                st.success(f"{len(saved_catalog.tables)}개 테이블 카탈로그를 저장했습니다.")
                st.rerun()
        backups = catalog_service.backups()
        if backups:
            backup_name = st.selectbox("비교할 카탈로그 백업", [item["name"] for item in backups])
            if st.button("현재 카탈로그와 비교"):
                comparison = catalog_service.compare_backup(backup_name)
                st.session_state["catalog_comparison"] = comparison
            if comparison := st.session_state.get("catalog_comparison"):
                st.json(comparison)
            restore_confirmed = st.checkbox(
                "현재 카탈로그를 선택한 백업으로 교체합니다. 현재 버전은 새 백업으로 보관됩니다.",
                key="catalog_restore_confirmed",
            )
            if st.button("선택한 백업 복원", disabled=not restore_confirmed or not has_role("admin")):
                try:
                    restored = catalog_service.restore(backup_name)
                except (FileNotFoundError, ValueError) as error:
                    st.error(f"카탈로그 복원에 실패했습니다: {error}")
                else:
                    st.session_state.pop("catalog_comparison", None)
                    st.success(f"{len(restored.tables)}개 테이블 카탈로그를 복원했습니다.")
                    st.rerun()
        st.download_button(
            "카탈로그 JSON 다운로드",
            data=(active_catalog or Catalog(source="unknown")).model_dump_json(indent=2),
            file_name="logpresso-catalog.json",
            mime="application/json",
        )
    if st.button("문서 다시 인덱싱", disabled=not has_role("admin")):
        result = index.rebuild(settings.doc_path)
        st.success(f"{result['chunk_count']}개 청크를 인덱싱했습니다.")

    with st.expander("실행 연동 준비"):
        st.success("DRY RUN 준비 완료")
        st.write("실제 Logpresso 실행은 비활성화되어 있습니다.")
        st.caption("생성 쿼리는 검증 후 복사해서 Logpresso에서 수동 실행합니다.")
    with st.expander("관리 변경 이력"):
        events = AuditStore(settings.db_path).recent(30)
        if events:
            st.dataframe(events, use_container_width=True, hide_index=True)
        else:
            st.caption("표시할 관리 변경 이력이 없습니다.")
    with st.expander("운영 집계"):
        metrics_store = MetricsStore(settings.metrics_db_path, settings.metrics_retention_days)
        metrics = metrics_store.summary()
        if metrics:
            overview = operational_overview(metrics)
            st.caption(
                f"최근 {settings.metrics_retention_days}일 집계입니다. 요청·쿼리·IP 원문은 저장하지 않습니다."
            )
            generation_col, fallback_col, ollama_col, slow_col = st.columns(4)
            generation_col.metric("생성 요청", overview["generation_total"])
            fallback_col.metric("LLM fallback", overview["fallback_count"])
            ollama_col.metric("Ollama 응답", overview["ollama_requests"])
            slow_col.metric("Timeout 구간", overview["slow_ollama_count"])
            for warning in overview["warnings"]:
                st.warning(warning)
            st.dataframe(
                [
                    {"항목": metric_label(key), "카운터": key, "횟수": value}
                    for key, value in metrics.items()
                ],
                use_container_width=True,
                hide_index=True,
            )
            daily_metrics = metrics_store.daily_summary()
            if daily_metrics:
                st.caption("최근 일별 집계")
                st.dataframe(
                    [
                        {"날짜(UTC)": item["day"], "항목": metric_label(str(item["metric"])), "횟수": item["count"]}
                        for item in daily_metrics
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
        else:
            st.caption("표시할 집계가 없습니다. 요청·쿼리 원문은 저장하지 않습니다.")
    if settings.enable_dev_evaluation:
        with st.expander("개발용 Gold Set 평가"):
            st.caption("fixture 기반 평가이며 외부 Logpresso 시스템에 연결하지 않습니다.")
            suggestions = FeedbackStore(settings.db_path).gold_set_suggestions()
            if suggestions:
                st.caption("원문 없이 집계한 피드백 기반 시나리오 제안")
                st.dataframe(suggestions, use_container_width=True, hide_index=True)
            if st.button("Gold Set 실행"):
                st.session_state["gold_set_result"] = run_gold_set(settings.db_path, settings.docs_dir.parent / "tests" / "fixtures" / "gold_set.json")
            if result := st.session_state.get("gold_set_result"):
                st.metric("통과", f"{result['passed']} / {result['total']}")
                failures = [item for item in result["results"] if not item["passed"]]
                if failures:
                    st.dataframe(failures, use_container_width=True, hide_index=True)
                else:
                    st.success("모든 Gold Set 시나리오를 통과했습니다.")
            if settings.llm_provider == "ollama":
                comparison_case_limit = st.number_input(
                    "문맥 비교 케이스 수",
                    min_value=1,
                    max_value=19,
                    value=1,
                    step=1,
                )
                if st.button("Ollama 문맥 제한 비교"):
                    st.session_state["ollama_context_comparison"] = compare_llm_context_limits(
                        settings.db_path,
                        settings.docs_dir.parent / "tests" / "fixtures" / "gold_set.json",
                        QueryGenerator(Retriever(index)).llm,
                        max_cases=int(comparison_case_limit),
                    )
                if result := st.session_state.get("ollama_context_comparison"):
                    st.dataframe(
                        [
                            {"문맥": name, **summary}
                            for name, summary in result.items()
                        ],
                        use_container_width=True,
                        hide_index=True,
                    )

st.title("로그프레소 자연어 쿼리 생성기")

work_mode = st.radio("작업 유형", ["쿼리 생성", "대시보드 생성"], horizontal=True)
if work_mode == "대시보드 생성":
    st.subheader("자연어 대시보드 설계")
    st.caption("공통 운영 대시보드 또는 제조사·제품·로그 형식별 보안 대시보드를 설계합니다.")
    dashboard_designer = DashboardDesigner()
    dashboard_examples = dashboard_designer.example_requests()
    example_by_label = {
        f"{item['title']} · 패널 {item['panel_count']}개": item
        for item in dashboard_examples
    }
    with st.expander(f"제공받은 운영 대시보드 예시 · {len(dashboard_examples) - 1}종", expanded=True):
        example_label = st.selectbox(
            "대시보드 예시",
            list(example_by_label),
            help="통합 운영 현황은 아래 8개 예시를 하나의 대시보드로 구성합니다.",
        )
        selected_example = example_by_label[example_label]
        st.caption(selected_example["description"])
        if st.button("선택한 예시로 바로 설계", type="primary", width="stretch"):
            st.session_state["dashboard_definition"] = dashboard_designer.design(DashboardDesignRequest(
                request=selected_example["request"], context=RequestContext(product=product),
            )).model_dump()
            st.session_state.pop("dashboard_record_id", None)
            st.rerun()
    dashboard_store = DashboardStore(settings.dashboard_db_path)
    saved_dashboards = dashboard_store.list()
    with st.expander(f"저장된 대시보드 · {len(saved_dashboards)}개"):
        if saved_dashboards:
            saved_by_label = {
                f"{item.title} · r{item.revision} · 패널 {item.panel_count}개": item
                for item in saved_dashboards
            }
            saved_label = st.selectbox("저장된 설계", list(saved_by_label), key="saved_dashboard_choice")
            saved_item = saved_by_label[saved_label]
            saved_col1, saved_col2 = st.columns(2)
            if saved_col1.button("불러오기", width="stretch"):
                st.session_state["dashboard_definition"] = dashboard_store.get(saved_item.id).dashboard.model_dump()
                st.session_state["dashboard_record_id"] = saved_item.id
                st.rerun()
            if saved_col2.button("복제하여 불러오기", width="stretch"):
                clone = dashboard_store.clone(saved_item.id)
                st.session_state["dashboard_definition"] = clone.dashboard.model_dump()
                st.session_state["dashboard_record_id"] = clone.id
                st.rerun()
            revisions = dashboard_store.revisions(saved_item.id)
            st.dataframe(revisions, width="stretch", hide_index=True)
        else:
            st.caption("아직 저장된 대시보드가 없습니다.")
    dashboard_request = st.text_area(
        "대시보드 요청",
        placeholder="예: 라이선스와 로그 수집 상태를 한 화면에서 확인하는 운영 대시보드 만들어줘",
        height=100,
    )
    dashboard_products = store_knowledge.payload.get("products", [])
    dashboard_manufacturers = list(dict.fromkeys(
        str(item.get("manufacturer")) for item in dashboard_products if item.get("manufacturer")
    ))
    scope_col1, scope_col2, scope_col3 = st.columns(3)
    with scope_col1:
        dashboard_manufacturer = st.selectbox("대시보드 제조사", [""] + dashboard_manufacturers)
    scoped_products = [
        str(item.get("name")) for item in dashboard_products
        if not dashboard_manufacturer or item.get("manufacturer") == dashboard_manufacturer
    ]
    with scope_col2:
        dashboard_product = st.selectbox("대시보드 제품", [""] + scoped_products)
    dashboard_product_data = next(
        (item for item in dashboard_products if item.get("name") == dashboard_product), None
    )
    dashboard_schemas = [str(item.get("name")) for item in (dashboard_product_data or {}).get("schemas", [])]
    with scope_col3:
        dashboard_schema = st.selectbox("대시보드 로그 형식", [""] + dashboard_schemas, disabled=not dashboard_product)
    setting_col1, setting_col2, setting_col3 = st.columns(3)
    with setting_col1:
        dashboard_table = st.text_input(
            "대시보드 조회 테이블",
            value="secui_events" if dashboard_product else "",
            disabled=not dashboard_product,
        )
    with setting_col2:
        dashboard_time_range = st.selectbox("기본 시간 범위", ["1h", "6h", "24h", "7d", "30d"], index=2)
    with setting_col3:
        dashboard_refresh = st.number_input("새로고침 주기 초", min_value=30, max_value=86400, value=300, step=30)
    if st.button("대시보드 설계", type="primary", disabled=not dashboard_request.strip()):
        st.session_state["dashboard_definition"] = dashboard_designer.design(DashboardDesignRequest(
            request=dashboard_request,
            manufacturer=dashboard_manufacturer or None,
            store_product=dashboard_product or None,
            store_schema=dashboard_schema or None,
            table_name=dashboard_table or None,
            default_time_range=dashboard_time_range,
            refresh_interval_seconds=int(dashboard_refresh),
            context=RequestContext(product=product),
        )).model_dump()

    if dashboard_payload := st.session_state.get("dashboard_definition"):
        dashboard = DashboardDefinition.model_validate(dashboard_payload)
        st.divider()
        dashboard.title = st.text_input("대시보드 제목", value=dashboard.title)
        dashboard.description = st.text_area("대시보드 설명", value=dashboard.description, height=70)
        st.subheader(f"패널 미리보기 · {len(dashboard.panels)}개")
        edited_panels = []
        for index, panel in enumerate(dashboard.panels):
            with st.expander(f"{index + 1}. {panel.title}", expanded=index < 2):
                title_col, visual_col, unit_col = st.columns([2, 1, 1])
                with title_col:
                    panel.title = st.text_input("패널 제목", value=panel.title, key=f"dashboard_panel_title_{panel.id}")
                with visual_col:
                    visual_options = ["metric", "status", "line", "bar", "table"]
                    panel.visualization = st.selectbox(
                        "시각화", visual_options, index=visual_options.index(panel.visualization), key=f"dashboard_visual_{panel.id}"
                    )
                with unit_col:
                    panel.unit = st.text_input("단위", value=panel.unit or "", key=f"dashboard_unit_{panel.id}") or None
                panel.query = st.text_area("패널 쿼리", value=panel.query, height=180, key=f"dashboard_query_{panel.id}")
                layout_cols = st.columns(4)
                panel.layout.x = int(layout_cols[0].number_input("X", 0, 11, panel.layout.x, key=f"dashboard_x_{panel.id}"))
                panel.layout.y = int(layout_cols[1].number_input("Y", 0, 100, panel.layout.y, key=f"dashboard_y_{panel.id}"))
                panel.layout.width = int(layout_cols[2].number_input("너비", 1, 12, panel.layout.width, key=f"dashboard_w_{panel.id}"))
                panel.layout.height = int(layout_cols[3].number_input("높이", 1, 12, panel.layout.height, key=f"dashboard_h_{panel.id}"))
                if panel.thresholds:
                    threshold_text = st.text_area(
                        "임계치 JSON",
                        value=json.dumps([item.model_dump() for item in panel.thresholds], ensure_ascii=False, indent=2),
                        height=130,
                        key=f"dashboard_thresholds_{panel.id}",
                        help="operator, value, severity, label을 수정할 수 있습니다.",
                    )
                    try:
                        panel.thresholds = [DashboardThreshold.model_validate(item) for item in json.loads(threshold_text)]
                    except (ValueError, TypeError):
                        st.warning("임계치 JSON 형식을 확인하세요. 마지막 정상 값을 사용합니다.")
                edited_panels.append(panel)
        dashboard.panels = edited_panels
        dashboard, dashboard_validation = DashboardDesigner().validate(dashboard, RequestContext(product=product))
        if dashboard_validation.valid:
            st.success(f"패널 쿼리 {dashboard_validation.valid_panels}/{dashboard_validation.panel_count}개 검증 통과")
        else:
            st.error(f"검증 실패 패널 {dashboard_validation.invalid_panels}개")
        st.dataframe(dashboard_validation.panels, width="stretch", hide_index=True)
        analysis = analyze_dashboard(dashboard)
        with st.expander(f"성능·비용 점검 · {analysis.score}점", expanded=bool(analysis.warnings)):
            st.metric("예상 쿼리 부하", analysis.estimated_query_weight)
            for warning in analysis.warnings:
                st.warning(warning)
            for recommendation in analysis.recommendations:
                st.info(recommendation)
            st.dataframe(analysis.panel_details, width="stretch", hide_index=True)
        preview_columns = st.columns(2)
        for index, panel in enumerate(dashboard.panels):
            with preview_columns[index % 2].container(border=True):
                st.markdown(f"**{panel.title}**")
                st.caption(f"{panel.visualization} · {panel.unit or '단위 없음'} · {panel.layout.width}×{panel.layout.height}")
                st.code(panel.query, language="text")
        export_payload = dashboard.model_copy(deep=True)
        for panel in export_payload.panels:
            panel.validation = None
        export_col1, export_col2 = st.columns(2)
        export_col1.download_button(
            "대시보드 JSON 다운로드",
            export_payload.model_dump_json(indent=2),
            file_name="logpresso-dashboard.json",
            mime="application/json",
            width="stretch",
        )
        export_col2.download_button(
            "대시보드 YAML 다운로드",
            dashboard_to_yaml(export_payload),
            file_name="logpresso-dashboard.yaml",
            mime="application/yaml",
            width="stretch",
        )
        action_col1, action_col2 = st.columns(2)
        if action_col1.button("설계 저장", width="stretch"):
            record = dashboard_store.save(
                export_payload,
                st.session_state.get("dashboard_record_id"),
                "웹 편집기에서 저장",
            )
            st.session_state["dashboard_record_id"] = record.id
            st.success(f"저장 완료 · 리비전 {record.revision}")
        if action_col2.button("Logpresso 배포계획 미리보기", width="stretch"):
            st.session_state["dashboard_deployment_plan"] = deployment_plan(
                export_payload,
                LogpressoTarget(base_url="https://10.11.12.14", verify_tls=True),
            ).model_dump()
        if plan := st.session_state.get("dashboard_deployment_plan"):
            with st.expander("배포계획 · 실제 서버 변경 없음", expanded=True):
                st.write(f"대상: {plan['target']['base_url']}")
                st.write(f"위젯 {plan['widget_count']}개 · 변수 {plan['variable_count']}개")
                for step in plan["steps"]:
                    st.write(f"- {step}")
                for warning in plan["warnings"]:
                    st.warning(warning)
                st.json(plan["payload"], expanded=False)
        st.session_state["dashboard_definition"] = dashboard.model_dump()
    st.stop()

store_products = store_knowledge.payload.get("products", [])
manufacturers = list(dict.fromkeys(
    str(item.get("manufacturer")) for item in store_products if item.get("manufacturer")
))
selection_col1, selection_col2 = st.columns(2)
with selection_col1:
    selected_manufacturer = st.selectbox("제조사", [""] + manufacturers)
product_options = [
    str(item.get("name")) for item in store_products
    if not selected_manufacturer or item.get("manufacturer") == selected_manufacturer
]
with selection_col2:
    selected_store_product = st.selectbox("Syslog 제품", [""] + product_options)
selected_product_data = next(
    (item for item in store_products if item.get("name") == selected_store_product), None
)
schema_options = [str(item.get("name")) for item in (selected_product_data or {}).get("schemas", [])]
selected_store_schema = st.selectbox(
    "로그 형식",
    [""] + schema_options,
    disabled=not selected_store_product,
    help="제품을 먼저 선택하면 해당 제품에서 수집 가능한 Syslog 형식만 표시됩니다.",
)
saved_store_table = store_mapping.resolve(selected_store_product, selected_store_schema or None)
query_store_table = st.text_input(
    "조회 테이블",
    value=saved_store_table or ("secui_events" if selected_store_product else ""),
    disabled=not selected_store_product,
    help="테스트 기본값은 secui_events입니다. 실제 환경의 테이블명이 다르면 변경하세요.",
    key=f"query_store_table::{selected_store_product}::{selected_store_schema}",
)
mapped_store_table = query_store_table.strip() or None
selected_schema_data = next(
    (item for item in (selected_product_data or {}).get("schemas", []) if item.get("name") == selected_store_schema),
    None,
)
if selected_store_product:
    field_count = len((selected_schema_data or {}).get("fields", []))
    context_parts = [f"선택 제품: {selected_store_product}"]
    if selected_store_schema:
        context_parts.extend([f"로그 형식: {selected_store_schema}", f"공개 필드: {field_count}개"])
    if mapped_store_table:
        context_parts.append(f"대상 테이블: {mapped_store_table}")
    st.caption(" · ".join(context_parts))
    if mapped_store_table and not saved_store_table:
        st.info("`secui_events`는 테스트용 기본 테이블입니다. 실제 로그 테이블이 다르면 위 값을 변경하세요.")
    if selected_store_schema and field_count:
        field_rows = [
            {
                "필드명": field.get("name", ""),
                "표시명": field.get("display_name", ""),
                "유형": field.get("type") or field.get("source_type", ""),
                "설명": field.get("description", ""),
                "유사어": ", ".join(str(alias) for alias in field.get("aliases", [])),
            }
            for field in selected_schema_data.get("fields", [])
        ]
        with st.expander(f"선택된 로그 형식 필드 {field_count}개", expanded=True):
            st.dataframe(
                field_rows,
                width="stretch",
                hide_index=True,
                height=min(520, 38 + field_count * 35),
            )
            st.caption("필드명과 표시명·유사어를 자연어 요청에 사용할 수 있습니다.")
    elif selected_store_schema:
        st.warning("이 로그 형식은 공개 필드가 없어 제품·형식 힌트 중심으로 생성됩니다.")
else:
    st.caption("제품을 모르는 경우 선택하지 않고 요청문에 제품명·로그 종류·조건을 직접 적어도 됩니다.")

request_placeholder = "예: 최근 24시간 출발지 IP별 차단 건수를 많은 순으로 20개 보여줘"
if selected_store_schema:
    request_placeholder = f"예: 최근 24시간 {selected_store_schema}에서 출발지 IP별 건수를 보여줘"
request_text = st.text_area(
    "쿼리 요청",
    value=st.session_state.get("request_text", ""),
    height=130,
    placeholder=request_placeholder,
)
with st.expander("생성 전 해석 편집", expanded=False):
    st.caption("자연어 해석이 다를 때 이 값만 보완해 다시 생성할 수 있습니다.")
    interpretation_tables = st.text_input("테이블", placeholder="예: firewall_logs, insa")
    interpretation_fields = st.text_input("필드", placeholder="예: src_ip, dst_ip, action")
    interpretation_join_keys = st.text_input("조인 키", placeholder="예: firewall_logs.src_ip, insa.ip")


def request_fingerprint(text: str, context: RequestContext) -> str:
    payload = {
        "request": text,
        "context": context.model_dump(),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def current_context() -> RequestContext:
    catalog_tables = active_catalog.tables if active_catalog else []
    request_tables = request_schema_catalog.tables if request_schema_catalog else []
    return RequestContext(
        product=product,
        version=version or None,
        store_product=selected_store_product or None,
        store_schema=selected_store_schema or None,
        known_tables=list(dict.fromkeys(
            [line.strip() for line in known_tables.splitlines() if line.strip()]
            + [value.strip() for value in interpretation_tables.split(",") if value.strip()]
            + ([mapped_store_table] if mapped_store_table else [])
            + st.session_state.get("learned_tables", [])
            + [table.table_name for table in catalog_tables + request_tables]
        )),
        known_fields=list(dict.fromkeys(
            [line.strip() for line in known_fields.splitlines() if line.strip()]
            + [value.strip() for value in interpretation_fields.split(",") if value.strip()]
            + [str(field.get("name")) for field in (selected_schema_data or {}).get("fields", []) if field.get("name")]
            + st.session_state.get("learned_fields", [])
            + [field.field_name for table in catalog_tables + request_tables for field in table.fields]
        )),
        known_loggers=list(dict.fromkeys(
            [line.strip() for line in known_loggers.splitlines() if line.strip()]
        )),
        known_streams=list(dict.fromkeys(
            [line.strip() for line in known_streams.splitlines() if line.strip()]
        )),
        catalog=active_catalog,
        request_catalog=request_schema_catalog,
    )


def analyze_query_data(query: str, context: RequestContext) -> dict:
    syntax = QueryValidator(Retriever(index)).validate(query)
    schema = catalog_service.validate_query(query, context)
    syntax.errors.extend(schema.errors)
    syntax.warnings.extend(schema.warnings)
    syntax.compatibility_notes.extend(schema.compatibility_notes)
    syntax.valid = not syntax.errors
    quality = QueryQualityAnalyzer().analyze(query, syntax)
    preview = ExecutionPreviewService().build(query if syntax.valid else None, syntax, quality)
    return {
        "validation": syntax.model_dump(),
        "schema_validation": schema.model_dump(),
        "quality": quality.model_dump(),
        "execution_preview": preview.model_dump(),
    }


def render_revalidation_summary(analysis: dict) -> None:
    validation = analysis.get("validation", {})
    quality = analysis.get("quality", {})
    preview = analysis.get("execution_preview", {})
    errors = validation.get("errors", [])
    warnings = validation.get("warnings", [])
    risk_level = quality.get("risk_level", "unknown")

    if validation.get("valid"):
        st.success("수정 쿼리는 현재 검증 규칙을 통과했습니다.")
    else:
        st.error(f"수정 쿼리에서 {len(errors)}개의 오류를 찾았습니다.")

    status_column, risk_column, preview_column = st.columns(3)
    status_column.metric("문법/스키마", "통과" if validation.get("valid") else "오류")
    risk_column.metric("위험도", risk_level.upper())
    preview_column.metric("실행 준비", preview.get("status", "not_requested"))

    if errors:
        st.caption("수정이 필요한 항목")
        for issue in errors:
            st.error(issue.get("message", "검증 오류") + (f" 제안: {issue['suggestion']}" if issue.get("suggestion") else ""))
    if warnings:
        st.caption("확인 권장 항목")
        for issue in warnings:
            st.warning(issue.get("message", "검증 경고") + (f" 제안: {issue['suggestion']}" if issue.get("suggestion") else ""))

    diagnostics = quality.get("diagnostics", [])
    if diagnostics:
        with st.expander(f"품질 진단 {len(diagnostics)}건"):
            for issue in diagnostics:
                st.write(f"- {issue.get('message', '')}")
                if issue.get("suggestion"):
                    st.caption(f"제안: {issue['suggestion']}")
    if preview.get("confirmation_message"):
        st.info(preview["confirmation_message"])
    with st.expander("상세 JSON"):
        st.json(analysis)


def render_validation_result(title: str, result: dict) -> None:
    """Make generation-time validation scannable while preserving raw evidence."""
    errors = result.get("errors", [])
    warnings = result.get("warnings", [])
    is_valid = result.get("valid", False)
    st.subheader(title)
    (st.success if is_valid else st.error)("문법 검증을 통과했습니다." if is_valid else f"오류 {len(errors)}건")
    commands = result.get("commands", [])
    if commands:
        st.markdown("사용 명령: " + ", ".join(f"`{command}`" for command in commands))
    error_column, warning_column, command_column = st.columns(3)
    error_column.metric("오류", len(errors))
    warning_column.metric("경고", len(warnings))
    command_column.metric("명령", len(result.get("commands", [])))
    for issue in errors:
        st.error(issue.get("message", "검증 오류") + (f" 제안: {issue['suggestion']}" if issue.get("suggestion") else ""))
    for issue in warnings:
        st.warning(issue.get("message", "검증 경고") + (f" 제안: {issue['suggestion']}" if issue.get("suggestion") else ""))
    with st.expander(f"{title} 상세 JSON"):
        st.json(result)


def query_structure_dot(intent: dict) -> str:
    """Render the parsed plan only; this never executes a query."""
    tables = intent.get("tables") or []
    join = intent.get("join") or {}
    filters = intent.get("filters") or []
    aggregations = intent.get("aggregations") or []
    lines = ["digraph query {", "rankdir=LR;", 'node [shape=box, style="rounded,filled", fillcolor="#f5f7fa"];']
    for table in tables:
        lines.append(f'"table:{table}" [label="table\\n{table}"];')
    if join:
        left = join.get("left_table", "left")
        right = join.get("right_table", "right")
        label = f"{join.get('join_type', 'inner')} join\\n{join.get('left_key', '')} = {join.get('right_key', '')}"
        lines.append(f'"table:{left}" -> "table:{right}" [label="{label}"];')
    previous = f"table:{tables[0]}" if tables else None
    for index, item in enumerate(filters):
        node = f"filter:{index}"
        lines.append(f'"{node}" [label="filter\\n{item.get("field", "")} {item.get("operator", "")} {item.get("value", "")}", fillcolor="#fff6d9"];')
        if previous:
            lines.append(f'"{previous}" -> "{node}";')
        previous = node
    for index, item in enumerate(aggregations):
        node = f"aggregate:{index}"
        lines.append(f'"{node}" [label="aggregate\\n{item.get("function", "")}({item.get("field") or ""})", fillcolor="#e8f5ef"];')
        if previous:
            lines.append(f'"{previous}" -> "{node}";')
        previous = node
    lines.append("}")
    return "\n".join(lines)


def clear_clarification_state() -> None:
    st.session_state.pop("clarification_answer", None)


def clear_result_state() -> None:
    clear_clarification_state()
    st.session_state.pop("response", None)
    st.session_state.pop("response_fingerprint", None)
    st.session_state.pop("editable_query", None)
    st.session_state.pop("editable_query_source", None)
    st.session_state.pop("edited_query_analysis", None)
    st.session_state.pop("edited_query_analysis_fingerprint", None)


def generate(text: str, *, clear_answer: bool = True) -> None:
    if clear_answer:
        clear_clarification_state()
    context = current_context()
    additions = []
    if interpretation_tables:
        additions.append("테이블은 " + interpretation_tables)
    if interpretation_fields:
        additions.append("필드는 " + interpretation_fields)
    if interpretation_join_keys:
        additions.append("조인 키는 " + interpretation_join_keys)
    enriched_text = text + ("\n추가 조건: " + " / ".join(additions) if additions else "")
    payload = GenerateQueryRequest(request=enriched_text, context=context)
    llm = MockProvider() if generation_mode == "빠른 규칙 기반" else None
    generator = QueryGenerator(Retriever(index), llm=llm)
    original_timeout = settings.ollama_timeout_seconds
    if generation_mode == "Ollama 보조":
        settings.ollama_timeout_seconds = min(original_timeout, 30)
    try:
        response = generator.generate(payload)
    finally:
        settings.ollama_timeout_seconds = original_timeout
    FeedbackStore(settings.db_path).record_generation_outcome(enriched_text, response.status)
    st.session_state["request_text"] = text
    st.session_state["response"] = response.model_dump()
    st.session_state["response_fingerprint"] = request_fingerprint(text, context)
    st.session_state["editable_query"] = response.query or ""
    st.session_state["query_versions"] = [response.query] if response.query else []
    st.session_state["editable_query_source"] = st.session_state["response_fingerprint"]
    st.session_state.pop("edited_query_analysis", None)
    st.session_state.pop("edited_query_analysis_fingerprint", None)
    if response.status != "needs_clarification":
        clear_clarification_state()


current_fingerprint = request_fingerprint(request_text, current_context())
if request_text.strip():
    preview_intent = IntentParser().parse(GenerateQueryRequest(request=request_text, context=current_context()))
    if preview_intent.table_candidates:
        st.caption("AI 해석 후보 테이블: " + ", ".join(preview_intent.table_candidates) + " (카탈로그로 확인 권장)")
if (
    "response_fingerprint" in st.session_state
    and st.session_state["response_fingerprint"] != current_fingerprint
):
    clear_result_state()


generate_button, generate_progress = st.columns([1, 4], vertical_alignment="center")
with generate_button:
    requested_generation = st.button("쿼리 생성", type="primary")
if requested_generation:
    with generate_progress:
        with st.spinner("쿼리 생성 중...", show_time=True):
            generate(request_text)
    st.rerun()

response = st.session_state.get("response")
if response:
    needs_clarification = response.get("status") == "needs_clarification"

    if needs_clarification:
        st.warning("추가 정보가 필요합니다.")
        answer = st.text_area(
            "확인 질문 답변",
            key="clarification_answer",
            placeholder="예: 테이블은 app_logs, 에러 필드는 message, 기간은 최근 24시간",
        )
        if st.button("답변을 반영해 다시 생성"):
            combined = request_text + "\n추가 조건: " + answer
            generate(combined, clear_answer=True)
            st.rerun()

    if st.session_state.get("editable_query_source") != st.session_state.get("response_fingerprint"):
        st.session_state["editable_query"] = response.get("query") or ""
        st.session_state["editable_query_source"] = st.session_state.get("response_fingerprint")
    if suggestion_code := st.session_state.pop("pending_query_suggestion", None):
        suggested_query = apply_safe_suggestion(st.session_state.get("editable_query", ""), suggestion_code)
        if suggested_query:
            st.session_state["editable_query"] = suggested_query
            st.session_state["suggestion_applied_notice"] = suggestion_code
    if version_to_restore := st.session_state.pop("pending_query_version_restore", None):
        versions = st.session_state.get("query_versions", [])
        if isinstance(version_to_restore, int) and 0 <= version_to_restore < len(versions):
            st.session_state["editable_query"] = versions[version_to_restore]
    tabs = st.tabs(["생성 쿼리", "설명", "검증", "문서 근거", "구조", "구조화 요청", "디버그"])
    with tabs[0]:
        if needs_clarification:
            for question in response.get("questions", []):
                st.write(f"- {question}")
        elif response.get("query"):
            st.code(response["query"], language="sql")
            st.caption("코드 블록의 복사 아이콘을 사용하거나 아래에서 파일로 저장할 수 있습니다.")
            st.download_button(
                "쿼리 파일 다운로드",
                data=response["query"],
                file_name="logpresso-query.txt",
                mime="text/plain",
            )
            if notice := st.session_state.pop("suggestion_applied_notice", None):
                st.info(f"'{notice}' 제안을 편집 쿼리에 반영했습니다. 재검증 후 검토하세요.")
            with st.expander("규칙 기반과 Ollama 결과 비교"):
                st.caption("비교는 쿼리 초안과 검증 정보만 보여 주며, 실제 Logpresso 실행은 하지 않습니다.")
                if settings.llm_provider != "ollama":
                    st.info("Ollama 비교는 LLM_PROVIDER=ollama일 때 사용할 수 있습니다.")
                elif st.button("두 모드 비교 생성"):
                    comparison_payload = GenerateQueryRequest(request=request_text, context=current_context())
                    with st.spinner("두 개의 쿼리 초안을 검토 중..."):
                        rule_response = QueryGenerator(Retriever(index), llm=MockProvider()).generate(comparison_payload)
                        original_timeout = settings.ollama_timeout_seconds
                        settings.ollama_timeout_seconds = min(original_timeout, 30)
                        try:
                            ollama_response = QueryGenerator(Retriever(index)).generate(comparison_payload)
                        finally:
                            settings.ollama_timeout_seconds = original_timeout
                    comparison = compare_generation_results(rule_response, ollama_response)
                    st.session_state["generation_comparison"] = comparison
                    st.session_state["generation_comparison_history"] = append_comparison_history(
                        st.session_state.get("generation_comparison_history", []), comparison
                    )
                if comparison := st.session_state.get("generation_comparison"):
                    st.json(comparison)
                if history := st.session_state.get("generation_comparison_history"):
                    st.caption("이번 브라우저 세션의 비교 이력")
                    st.dataframe(comparison_history_rows(history), use_container_width=True, hide_index=True)
            edited_query = st.text_area("생성 쿼리 편집", height=180, key="editable_query")
            edited_fingerprint = request_fingerprint(edited_query, current_context())
            if (
                "edited_query_analysis_fingerprint" in st.session_state
                and st.session_state["edited_query_analysis_fingerprint"] != edited_fingerprint
            ):
                st.session_state.pop("edited_query_analysis", None)
                st.session_state.pop("edited_query_analysis_fingerprint", None)
            if st.button("수정 쿼리 재검증"):
                st.session_state["query_versions"] = append_version(st.session_state.get("query_versions", []), edited_query)
                st.session_state["edited_query_analysis"] = analyze_query_data(edited_query, current_context())
                st.session_state["edited_query_analysis_fingerprint"] = edited_fingerprint
            if edited_analysis := st.session_state.get("edited_query_analysis"):
                render_revalidation_summary(edited_analysis)
                if edited_analysis.get("validation", {}).get("valid") and st.button("이 수정 기준을 이번 세션에 기억"):
                    tables = CatalogService._tables(edited_query)
                    fields = sorted(CatalogService._field_refs(edited_query))
                    st.session_state["learned_tables"] = merge_hints(st.session_state.get("learned_tables", []), tables)
                    st.session_state["learned_fields"] = merge_hints(st.session_state.get("learned_fields", []), fields)
                    st.success("다음 요청부터 이번 세션의 테이블·필드 힌트로 사용합니다.")
            versions = st.session_state.get("query_versions", [])
            if len(versions) > 1:
                with st.expander("편집 이력 비교"):
                    version_index = st.selectbox("되돌릴 버전", list(range(len(versions) - 1)), format_func=lambda index: f"버전 {index + 1}")
                    st.code(query_diff(versions[version_index], edited_query) or "변경 없음", language="diff")
                    if st.button("선택 버전으로 되돌리기"):
                        st.session_state["pending_query_version_restore"] = version_index
                        st.rerun()
        else:
            st.error("쿼리를 생성하지 못했습니다.")
    with tabs[1]:
        explanations = response.get("explanation", [])
        if explanations:
            st.dataframe(explanations, use_container_width=True, hide_index=True)
            st.caption("문서 근거 탭에서 같은 명령어의 문법 근거와 옵션을 확인할 수 있습니다.")
        else:
            st.info("설명할 생성 쿼리가 없습니다.")
    with tabs[2]:
        render_validation_result("문법 검증 결과", response.get("validation") or {})
        schema = response.get("schema_validation") or {}
        quality = response.get("quality") or {}
        preview = response.get("execution_preview") or {}
        if schema:
            render_validation_result("스키마 검증 결과", schema)
            if lineage := schema.get("field_lineage"):
                with st.expander("필드 계보"):
                    st.dataframe(lineage, use_container_width=True, hide_index=True)
        else:
            st.info("카탈로그가 제공되지 않아 문법 중심으로만 검증했습니다. 실제 테이블/필드 카탈로그를 추가하면 검증 범위가 넓어집니다.")
        st.subheader("쿼리 품질 진단")
        if quality:
            scores = st.columns(4)
            for column, label, key in zip(scores, ["안전성", "성능", "완성도", "신뢰도"], ["safety_score", "performance_score", "completeness_score", "confidence_score"]):
                column.metric(label, quality.get(key, "-"))
                reasons = quality.get("score_reasons", {}).get(key, [])
                if reasons:
                    column.caption("감점: " + ", ".join(reasons))
            risk = quality.get("risk_level", "unknown")
            (st.error if risk in {"high", "critical"} else st.warning if risk == "medium" else st.success)(f"위험도: {risk}")
            for issue_index, issue in enumerate(quality.get("diagnostics", [])):
                message = issue.get("message", "")
                suggestion = issue.get("suggestion")
                text = f"{message} {suggestion or ''}".strip()
                if issue.get("severity") == "error":
                    st.error(text)
                elif issue.get("severity") == "warning":
                    st.warning(text)
                else:
                    st.info(text)
                if suggestion and st.button(
                    "제안 반영",
                    key=f"apply_suggestion_{issue.get('code')}_{issue_index}",
                ):
                    st.session_state["pending_query_suggestion"] = issue.get("code")
                    st.rerun()
        st.subheader("실행 준비 상태")
        if preview:
            st.write(f"상태: `{preview.get('status')}` | 위험도: `{preview.get('risk_level')}`")
            if preview.get("confirmation_message"):
                st.info(preview["confirmation_message"])
            for reason in preview.get("blocked_reasons", []):
                st.error(reason)
            st.caption("이 도구는 쿼리를 자동 실행하지 않습니다. 복사한 쿼리를 Logpresso에서 직접 검토 후 수동 실행하세요.")
        if edited_analysis := st.session_state.get("edited_query_analysis"):
            st.subheader("수정 쿼리 재검증")
            render_revalidation_summary(edited_analysis)
    with tabs[3]:
        references = response.get("references", [])
        if references:
            for reference_index, reference in enumerate(references):
                title = f"{reference.get('entry_name', '문서')} · {reference.get('section', '근거')}"
                with st.expander(title):
                    st.caption(reference.get("reason", "생성 쿼리에 사용된 문서 근거입니다."))
                    st.write(reference.get("excerpt", ""))
                    if reference.get("options"):
                        st.write("옵션: " + ", ".join(reference["options"]))
                    if reference.get("functions"):
                        st.write("함수: " + ", ".join(reference["functions"]))
        else:
            st.info("표시할 문서 근거가 없습니다.")
    with tabs[4]:
        st.graphviz_chart(query_structure_dot(response.get("intent") or {}), use_container_width=True)
        st.caption("이 화면은 생성 계획을 시각화한 것이며, Logpresso 실행을 수행하지 않습니다.")
    with tabs[5]:
        debug = response.get("debug", {})
        if response.get("assumptions") or debug.get("llm_intent_fallback"):
            st.subheader("AI 해석 결과")
            if debug.get("llm_intent_fallback"):
                st.info("AI가 구조화한 요청을 기존 검증기를 통과한 뒤 쿼리로 조립했습니다.")
            for assumption in response.get("assumptions", []):
                st.warning(f"추정: {assumption}")
        st.json(response.get("intent", {}))
    with tabs[6]:
        st.code(json.dumps(response.get("debug", {}), ensure_ascii=False, indent=2))

    st.divider()
    st.subheader("생성 결과 피드백")
    feedback_rating = st.selectbox("평가", ["positive", "neutral", "negative"], format_func={"positive": "좋음", "neutral": "보통", "negative": "개선 필요"}.get)
    feedback_issue = st.selectbox("문제 유형", ["", "wrong_table", "wrong_field", "wrong_time_range", "invalid_syntax", "unsafe_query", "irrelevant_query", "other"], format_func=lambda value: "선택 안 함" if not value else value)
    feedback_comment = st.text_area("의견", max_chars=1000)
    if st.button("피드백 저장"):
        saved = FeedbackStore(settings.db_path).save(
            FeedbackRequest(
                request_text=request_text,
                generated_query=response.get("query"),
                result_status=response.get("status", "unknown"),
                rating=feedback_rating,
                issue_type=feedback_issue or None,
                feedback_comment=feedback_comment or None,
            )
        )
        st.success(f"피드백 #{saved['id']}가 저장되었습니다.")
        st.caption("원문 요청과 쿼리는 저장하지 않았습니다.")

with st.expander("기존 쿼리 분석"):
    analysis_query = st.text_area("분석할 Logpresso 쿼리", height=140)
    manual_fingerprint = request_fingerprint(analysis_query, current_context())
    if (
        "manual_analysis_fingerprint" in st.session_state
        and st.session_state["manual_analysis_fingerprint"] != manual_fingerprint
    ):
        st.session_state.pop("manual_analysis", None)
        st.session_state.pop("manual_analysis_fingerprint", None)
    if st.button("쿼리 분석"):
        st.session_state["manual_analysis"] = analyze_query_data(analysis_query, current_context())
        st.session_state["manual_analysis_fingerprint"] = manual_fingerprint
    if manual_analysis := st.session_state.get("manual_analysis"):
        st.json(manual_analysis)
        st.caption("이 분석은 실제 Logpresso 실행을 수행하지 않습니다.")
