import json
import hashlib
from pathlib import Path

import streamlit as st

from app.core.config import settings
from app.models.request import GenerateQueryRequest, RequestContext
from app.services.indexer import DocumentIndex
from app.services.query_generator import QueryGenerator
from app.services.retriever import Retriever


st.set_page_config(page_title="로그프레소 자연어 쿼리 생성기", layout="wide")

index = DocumentIndex(settings.db_path)
if Path(settings.doc_path).exists():
    index.ensure_current(settings.doc_path)
status = index.status(settings.doc_path)

with st.sidebar:
    st.subheader("상태")
    st.write(f"LLM provider: `{settings.llm_provider}`")
    st.write(f"문서 인덱스: {'완료' if status['indexed'] else '미생성'}")
    st.write(f"문서 변경됨: {'예' if status['stale'] else '아니오'}")
    st.write(f"청크 수: {status['chunk_count']}")
    product = st.selectbox("제품군", ["ENT", "STD", "SNR", "FRS"], index=0)
    version = st.text_input("버전")
    known_tables = st.text_area("알려진 테이블", "firewall_logs\naraqne_query_logs")
    known_fields = st.text_area("알려진 필드", "src_ip\naction\n_time\nlogin_name\nmessage\nlevel")
    if st.button("문서 다시 인덱싱"):
        result = index.rebuild(settings.doc_path)
        st.success(f"{result['chunk_count']}개 청크를 인덱싱했습니다.")

st.title("로그프레소 자연어 쿼리 생성기")

examples = [
    "최근 24시간 동안 firewall_logs에서 출발지 IP별 차단 건수를 집계해서 많은 순으로 20개 보여줘",
    "araqne_query_logs에서 root가 실행한 쿼리를 찾아줘",
    "araqne_query_logs에서 root 사용자의 실행 건수를 10분 단위로 보여줘",
    "firewall_logs의 src_ip를 할당ip로 rename해줘",
    "firewall_logs에서 src_ip, action만 보여줘",
    "sample1, sample2 스트림을 10초간 level=error 조건으로 보여줘",
    "/opt/logpresso/events.json 파일을 조회해줘",
    "/opt/logpresso/testdata.zip 안의 *.txt 파일을 조회해줘",
    "firewall_logs 테이블의 message 필드 JSON 중첩을 펼쳐 파싱해줘",
    "에러 로그 보여줘",
]
selected = st.selectbox("예제 요청", [""] + examples)
default_request = selected or st.session_state.get("request_text", "")
request_text = st.text_area("사용자 요청", value=default_request, height=130)


def request_fingerprint(text: str, context: RequestContext) -> str:
    payload = {
        "request": text,
        "context": context.model_dump(),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def current_context() -> RequestContext:
    return RequestContext(
        product=product,
        version=version or None,
        known_tables=[line.strip() for line in known_tables.splitlines() if line.strip()],
        known_fields=[line.strip() for line in known_fields.splitlines() if line.strip()],
    )


def clear_clarification_state() -> None:
    st.session_state.pop("clarification_answer", None)


def clear_result_state() -> None:
    clear_clarification_state()
    st.session_state.pop("response", None)
    st.session_state.pop("response_fingerprint", None)


def generate(text: str, *, clear_answer: bool = True) -> None:
    if clear_answer:
        clear_clarification_state()
    context = current_context()
    payload = GenerateQueryRequest(request=text, context=context)
    generator = QueryGenerator(Retriever(index))
    response = generator.generate(payload)
    st.session_state["request_text"] = text
    st.session_state["response"] = response.model_dump()
    st.session_state["response_fingerprint"] = request_fingerprint(text, context)
    if response.status != "needs_clarification":
        clear_clarification_state()


current_fingerprint = request_fingerprint(request_text, current_context())
if (
    "response_fingerprint" in st.session_state
    and st.session_state["response_fingerprint"] != current_fingerprint
):
    clear_result_state()


if st.button("쿼리 생성", type="primary"):
    generate(request_text)
    st.rerun()

response_slot = st.empty()
response = st.session_state.get("response")
if response:
    with response_slot.container():
        needs_clarification = response.get("status") == "needs_clarification"
        clarification_slot = st.empty()

        if needs_clarification:
            with clarification_slot.container():
                st.warning("추가 정보가 필요합니다.")
                answer = st.text_area(
                    "확인 질문 답변",
                    key="clarification_answer",
                    placeholder="예: 테이블은 app_logs, 에러 필드는 message, 기간은 최근 24시간",
                )
                if st.button("답변을 반영해 다시 생성", disabled=not answer.strip()):
                    combined = request_text + "\n추가 조건: " + answer.strip()
                    generate(combined, clear_answer=True)
                    st.rerun()
        else:
            clarification_slot.empty()

        tabs = st.tabs(["생성 쿼리", "설명", "검증", "문서 근거", "구조화 요청", "디버그"])
        with tabs[0]:
            if needs_clarification:
                for question in response.get("questions", []):
                    st.write(f"- {question}")
            elif response.get("query"):
                query = response["query"]
                st.code(query, language="sql")
                st.caption("코드 영역 오른쪽 위의 복사 아이콘으로 쿼리를 복사할 수 있습니다.")
                st.download_button(
                    "쿼리 파일 다운로드",
                    data=query,
                    file_name="logpresso_query.txt",
                    mime="text/plain",
                )
            else:
                st.error("쿼리를 생성하지 못했습니다.")
        with tabs[1]:
            st.json(response.get("explanation", []))
        with tabs[2]:
            st.json(response.get("validation", {}))
        with tabs[3]:
            st.json(response.get("references", []))
        with tabs[4]:
            st.json(response.get("intent", {}))
        with tabs[5]:
            st.code(json.dumps(response.get("debug", {}), ensure_ascii=False, indent=2))
