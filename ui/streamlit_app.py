import json
import hashlib
import re
from datetime import datetime, timezone

import streamlit as st

from app.core.config import settings
from app.models.request import Catalog, CatalogField, CatalogTable, FeedbackRequest, GenerateQueryRequest, RequestContext
from app.services.catalog_service import CatalogService
from app.services.feedback_store import FeedbackStore
from app.services.alias_store import AliasStore
from app.services.execution_preview import ExecutionPreviewService
from app.services.indexer import DocumentIndex
from app.services.quality_analyzer import QueryQualityAnalyzer
from app.services.query_generator import QueryGenerator
from app.services.intent_parser import IntentParser
from app.services.query_validator import QueryValidator
from app.services.retriever import Retriever


st.set_page_config(page_title="로그프레소 자연어 쿼리 생성기", layout="wide")

index = DocumentIndex(settings.db_path)
status = index.status(settings.doc_path)
catalog_service = CatalogService(settings.catalog_path)


def load_uploaded_catalog(uploaded_file) -> Catalog | None:
    if uploaded_file is None:
        return None
    try:
        return Catalog.model_validate_json(uploaded_file.getvalue())
    except ValueError:
        st.sidebar.error("카탈로그 JSON 형식이 올바르지 않습니다.")
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
    feedback_summary = FeedbackStore(settings.db_path).summary()
    if feedback_summary["total"]:
        st.caption(f"저장된 피드백: {feedback_summary['total']}건 | 문제 유형: {feedback_summary['issue_types']}")
        candidates = FeedbackStore(settings.db_path).improvement_candidates()
        if candidates:
            with st.expander("피드백 기반 개선 후보"):
                for candidate in candidates:
                    st.write(f"- {candidate['title']} ({candidate['count']}건)")
                    st.caption(candidate["suggestion"])
    st.write(f"문서 인덱스: {'완료' if status['indexed'] else '미생성'}")
    st.write(f"문서 변경됨: {'예' if status['stale'] else '아니오'}")
    st.write(f"청크 수: {status['chunk_count']}")
    product = st.selectbox("제품군", ["ENT", "STD", "SNR", "FRS"], index=0)
    version = st.text_input("버전")
    known_tables = st.text_area("테이블 힌트 (선택)", placeholder="예: firewall_logs")
    known_fields = st.text_area("필드 힌트 (선택)", placeholder="예: src_ip\naction\n_time")
    known_loggers = st.text_area("logger 힌트 (선택)", placeholder="예: local\\firewall_logger")
    known_streams = st.text_area("stream 힌트 (선택)", placeholder="예: firewall_stream")
    with st.expander("업무 별칭 관리"):
        alias_store = AliasStore(settings.db_path)
        alias_phrase = st.text_input("업무 표현", key="alias_phrase", placeholder="예: 내부 방화벽")
        alias_target = st.text_input("테이블 또는 필드", key="alias_target", placeholder="예: corp_firewall_logs")
        alias_kind = st.selectbox("별칭 종류", ["table", "field"], key="alias_kind")
        if st.button("별칭 저장"):
            try:
                alias_store.save(alias_phrase, alias_target, alias_kind)
            except ValueError as error:
                st.error(str(error))
            else:
                st.success("별칭을 저장했습니다.")
                st.rerun()
        aliases = alias_store.list()
        if aliases:
            st.dataframe(aliases, use_container_width=True, hide_index=True)
            alias_to_delete = st.selectbox("삭제할 별칭", [""] + [f"{item['kind']}: {item['phrase']}" for item in aliases])
            if st.button("선택 별칭 삭제") and alias_to_delete:
                kind, phrase = alias_to_delete.split(": ", 1)
                alias_store.delete(phrase, kind)
                st.rerun()
    st.caption("비워 두어도 요청에 명시한 테이블과 필드를 생성에 사용합니다. 실제 존재 여부는 카탈로그가 있을 때 검증합니다.")
    request_schema = st.text_area("이번 요청 스키마 (선택)", placeholder="firewall_logs: src_ip, action, _time\napp_logs: message, host")
    try:
        request_schema_catalog = parse_request_catalog(request_schema)
    except ValueError as error:
        request_schema_catalog = None
        st.error(str(error))
    uploaded_catalog = st.file_uploader("카탈로그 JSON", type=["json"])
    uploaded_request_catalog = load_uploaded_catalog(uploaded_catalog)
    persisted_catalog = catalog_service.load() if uploaded_request_catalog is None else None
    active_catalog = uploaded_request_catalog or persisted_catalog
    if active_catalog:
        st.caption(f"카탈로그: {len(active_catalog.tables)}개 테이블 ({active_catalog.source})")
        with st.expander("카탈로그 미리보기"):
            st.json(active_catalog.model_dump())
    else:
        st.caption("카탈로그 없음: 알려진 테이블/필드와 문서 기반 검증을 사용합니다.")
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
        if st.button("카탈로그 저장"):
            try:
                saved_catalog = catalog_service.save(catalog_from_rows(edited_rows, active_catalog))
            except ValueError as error:
                st.error(str(error))
            else:
                st.success(f"{len(saved_catalog.tables)}개 테이블 카탈로그를 저장했습니다.")
                st.rerun()
        st.download_button(
            "카탈로그 JSON 다운로드",
            data=(active_catalog or Catalog(source="unknown")).model_dump_json(indent=2),
            file_name="logpresso-catalog.json",
            mime="application/json",
        )
    if st.button("문서 다시 인덱싱"):
        result = index.rebuild(settings.doc_path)
        st.success(f"{result['chunk_count']}개 청크를 인덱싱했습니다.")

    with st.expander("실행 연동 준비"):
        st.success("DRY RUN 준비 완료")
        st.write("실제 Logpresso 실행은 비활성화되어 있습니다.")
        st.caption("생성 쿼리는 검증 후 복사해서 Logpresso에서 수동 실행합니다.")

st.title("로그프레소 자연어 쿼리 생성기")

examples = [
    "최근 24시간 동안 firewall_logs에서 출발지 IP별 차단 건수를 집계해서 많은 순으로 20개 보여줘",
    "araqne_query_logs에서 root가 실행한 쿼리를 찾아줘",
    "araqne_query_logs에서 root 사용자의 실행 건수를 10분 단위로 보여줘",
    "firewall_logs의 src_ip를 할당ip로 rename해줘",
    "firewall_logs에서 src_ip, action만 보여줘",
    "에러 로그 보여줘",
]
selected = st.selectbox("예제 요청", [""] + examples)
quick_requests = [
    "방화벽에서 외부로 나간 통신 중 많은 IP부터 보고 싶어",
    "어제 로그인 실패한 사용자들을 계정별로 정리해줘",
    "인사 정보랑 방화벽 로그를 IP 기준으로 합쳐서 누가 차단됐는지 보고 싶어",
]
quick_choice = st.selectbox("빠른 테스트", [""] + quick_requests)
default_request = quick_choice or selected or st.session_state.get("request_text", "")
request_text = st.text_area("사용자 요청", value=default_request, height=130)
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
        known_tables=list(dict.fromkeys(
            [line.strip() for line in known_tables.splitlines() if line.strip()]
            + [value.strip() for value in interpretation_tables.split(",") if value.strip()]
            + [table.table_name for table in catalog_tables + request_tables]
        )),
        known_fields=list(dict.fromkeys(
            [line.strip() for line in known_fields.splitlines() if line.strip()]
            + [value.strip() for value in interpretation_fields.split(",") if value.strip()]
            + [field.field_name for table in catalog_tables + request_tables for field in table.fields]
        )),
        known_loggers=[line.strip() for line in known_loggers.splitlines() if line.strip()],
        known_streams=[line.strip() for line in known_streams.splitlines() if line.strip()],
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
    generator = QueryGenerator(Retriever(index))
    response = generator.generate(payload)
    st.session_state["request_text"] = text
    st.session_state["response"] = response.model_dump()
    st.session_state["response_fingerprint"] = request_fingerprint(text, context)
    st.session_state["editable_query"] = response.query or ""
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
    tabs = st.tabs(["생성 쿼리", "설명", "검증", "문서 근거", "구조", "구조화 요청", "디버그"])
    with tabs[0]:
        if needs_clarification:
            for question in response.get("questions", []):
                st.write(f"- {question}")
        elif response.get("query"):
            st.code(response["query"], language="sql")
            edited_query = st.text_area("생성 쿼리 편집", height=180, key="editable_query")
            edited_fingerprint = request_fingerprint(edited_query, current_context())
            if (
                "edited_query_analysis_fingerprint" in st.session_state
                and st.session_state["edited_query_analysis_fingerprint"] != edited_fingerprint
            ):
                st.session_state.pop("edited_query_analysis", None)
                st.session_state.pop("edited_query_analysis_fingerprint", None)
            if st.button("수정 쿼리 재검증"):
                st.session_state["edited_query_analysis"] = analyze_query_data(edited_query, current_context())
                st.session_state["edited_query_analysis_fingerprint"] = edited_fingerprint
            if edited_analysis := st.session_state.get("edited_query_analysis"):
                render_revalidation_summary(edited_analysis)
        else:
            st.error("쿼리를 생성하지 못했습니다.")
    with tabs[1]:
        st.json(response.get("explanation", []))
    with tabs[2]:
        st.json(response.get("validation", {}))
        schema = response.get("schema_validation") or {}
        quality = response.get("quality") or {}
        preview = response.get("execution_preview") or {}
        st.subheader("스키마 검증 결과")
        if schema:
            st.json(schema)
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
            for issue in quality.get("diagnostics", []):
                message = issue.get("message", "")
                suggestion = issue.get("suggestion")
                text = f"{message} {suggestion or ''}".strip()
                if issue.get("severity") == "error":
                    st.error(text)
                elif issue.get("severity") == "warning":
                    st.warning(text)
                else:
                    st.info(text)
                if suggestion and st.button("제안 반영", key=f"apply_suggestion_{issue.get('code')}"):
                    generate(request_text + "\n개선 조건: " + suggestion)
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
        st.json(response.get("references", []))
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

    st.download_button(
        "진단 리포트 다운로드",
        data=json.dumps(response, ensure_ascii=False, indent=2),
        file_name="logpresso-query-diagnostic.json",
        mime="application/json",
    )
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
