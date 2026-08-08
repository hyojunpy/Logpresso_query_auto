from app.models.request import GenerateQueryRequest
from app.services.query_generator import QueryGenerator
from app.services.retriever import Retriever
from tests.support import shared_index
import pytest


FREE_FORM_REQUESTS = [
    "\ubc29\ud654\ubcbd\uc5d0\uc11c \uc678\ubd80\ub85c \ub098\uac04 \ud1b5\uc2e0 \uc911 \ub9ce\uc740 IP\ubd80\ud130 \ubcf4\uace0 \uc2f6\uc5b4",
    "\uc5b4\uc81c \ub85c\uadf8\uc778 \uc2e4\ud328\ud55c \uc0ac\uc6a9\uc790\ub4e4\uc744 \uacc4\uc815\ubcc4\ub85c \uc815\ub9ac\ud574\uc918",
    "\uc778\uc0ac \uc815\ubcf4\ub791 \ubc29\ud654\ubcbd \ub85c\uadf8\ub97c IP \uae30\uc900\uc73c\ub85c \ud569\uccd0\uc11c \ub204\uac00 \ucc28\ub2e8\ub410\ub294\uc9c0 \ubcf4\uace0 \uc2f6\uc5b4",
    "\uc6f9 \uc11c\ubc84 \uc624\ub958\uac00 \uac11\uc790\uae30 \ub298\uc5b4\ub09c \uc2dc\uac04\uc744 \ucc3e\uc544\uc918",
    "443 \ud3ec\ud2b8\ub85c \ub9c9\ud78c \uc811\uc18d\ub9cc \ud655\uc778\ud574\uc918",
    "\ucd9c\ubc1c\uc9c0 \uc8fc\uc18c\ubcc4\ub85c \ucc28\ub2e8 \ud69f\uc218 \uc0c1\uc704 10\uac1c \ubcf4\uc5ec\uc918",
    "\ubc29\ud654\ubcbd \ub85c\uadf8\uc5d0 \uc9c1\uc6d0 IP\uac00 \ud3ec\ud568\ub41c \uac83\ub9cc \ub530\ub85c \ubcf4\uace0 \uc2f6\uc5b4",
    "\uc9c0\ub09c\uc8fc\uc5d0 \ub370\uc774\ud130 \uc804\uc1a1\ub7c9\uc774 \ud070 \ud638\uc2a4\ud2b8\ub97c \ucc3e\uc544\uc918",
    "\uc5d0\ub7ec \ub85c\uadf8\uc5d0\uc11c timeout \uad00\ub828 \uba54\uc2dc\uc9c0\ub9cc \ubaa8\uc544\uc918",
    "\uc11c\ubc84\ubcc4 \ub85c\uadf8\uc778 \uc2e4\ud328 \ucd94\uc774\ub97c \uc2dc\uac04\ub300\ubcc4\ub85c \ubcf4\uace0 \uc2f6\uc5b4",
    "\ubc29\ud654\ubcbd \ud14c\uc774\ube14\uc758 IP \uceec\ub7fc \uc774\ub984\uc744 \ud560\ub2f9 IP\ub85c \ubc14\uafb8\uace0 \uc778\uc0ac \ud14c\uc774\ube14\uacfc \uc5f0\uacb0\ud574\uc918",
    "\ucc28\ub2e8 \ub85c\uadf8\ub294 \ub9ce\uc740 \uc21c\uc73c\ub85c, \ucd5c\uadfc \ud558\ub8e8 \uae30\uc900\uc73c\ub85c \ubcf4\uace0 \uc2f6\uc5b4",
    "\ubc29\ud654\ubcbd \ub85c\uadf8\uc5d0\uc11c \ucc28\ub2e8 \ud69f\uc218\ub97c \ucd9c\ubc1c\uc9c0 IP\ubcc4\ub85c \uc9d1\uacc4\ud574\uc918",
    "\ucd5c\uadfc 24\uc2dc\uac04 \ubc29\ud654\ubcbd \ub85c\uadf8\uc758 \ucc28\ub2e8 \ud69f\uc218\ub97c \ub9ce\uc740 \uc21c\uc73c\ub85c \ubcf4\uc5ec\uc918",
    "443 \ud3ec\ud2b8\uc5d0\uc11c \ub9c9\ud78c \uc811\uc18d\uc744 \ubc29\ud654\ubcbd \ub85c\uadf8\uc5d0\uc11c \ucc3e\uc544\uc918",
    "22 \ud3ec\ud2b8 \ucc28\ub2e8 \ub85c\uadf8\ub97c \ud655\uc778\ud574\uc918",
    "\uc5b4\uc81c \ub85c\uadf8\uc778 \uc2e4\ud328\ud55c \uacc4\uc815\uc744 \uc815\ub9ac\ud574\uc918",
    "\ub85c\uadf8\uc778 \uc2e4\ud328 \uc0ac\uc6a9\uc790\ub97c \uacc4\uc815\ubcc4\ub85c \ubcf4\uc5ec\uc918",
    "\uc11c\ubc84\ubcc4 \ub85c\uadf8\uc778 \uc2e4\ud328\ub97c \ubcf4\uc5ec\uc918",
    "\uc6f9\uc11c\ubc84 \uc624\ub958\ub97c \uc2dc\uac04\ub300\ubcc4\ub85c \uc815\ub9ac\ud574\uc918",
    "\uc6f9 \uc11c\ubc84 \uc624\ub958 \ubc1c\uc0dd \uc2dc\uac04\uc744 \ucc3e\uc544\uc918",
    "\uc5d0\ub7ec \ub85c\uadf8\uc5d0\uc11c timeout \uba54\uc2dc\uc9c0\ub97c \ubaa8\uc544\uc918",
    "timeout \uad00\ub828 \uc5d0\ub7ec \ub85c\uadf8\ub9cc \ubcf4\uc5ec\uc918",
    "\uc9c0\ub09c\uc8fc \ub370\uc774\ud130 \uc804\uc1a1\ub7c9\uc774 \ud070 \ud638\uc2a4\ud2b8\ub97c \uc815\ub9ac\ud574\uc918",
    "\ub370\uc774\ud130 \uc804\uc1a1\ub7c9\uc774 \ud070 \ud638\uc2a4\ud2b8\ub97c \ubcf4\uc5ec\uc918",
    "\uc9c1\uc6d0 IP\uac00 \ud3ec\ud568\ub41c \ubc29\ud654\ubcbd \ub85c\uadf8\ub97c \ubcf4\uace0 \uc2f6\uc5b4",
    "\uc778\uc0ac \uc815\ubcf4\uc640 \ubc29\ud654\ubcbd \ub85c\uadf8\uc5d0\uc11c \uc9c1\uc6d0 IP\ub97c \ud655\uc778\ud574\uc918",
    "\ubc29\ud654\ubcbd \ud14c\uc774\ube14\uc758 IP \uceec\ub7fc \uc774\ub984\uc744 \ud560\ub2f9 IP\ub85c \ubc14\uafd4\uc918",
    "firewall_logs\uc758 src_ip\ub97c \ud560\ub2f9ip\ub85c rename\ud574\uc918",
    "\ubc29\ud654\ubcbd\uc5d0\uc11c \uc678\ubd80\ub85c \ub098\uac04 \ud1b5\uc2e0\uc744 \ucd9c\ubc1c\uc9c0 \uc8fc\uc18c\ubcc4\ub85c \ubcf4\uc5ec\uc918",
    "\ucd9c\ubc1c\uc9c0 \uc8fc\uc18c\ubcc4 \ucc28\ub2e8 \ud69f\uc218\ub97c \uc0c1\uc704\ub85c \uc815\ub9ac\ud574\uc918",
    "\ucd5c\uadfc 3\uc77c \ub3d9\uc548 \ubc29\ud654\ubcbd \ub85c\uadf8\uc5d0\uc11c \ucc28\ub2e8 \ud69f\uc218\ub97c \ucd9c\ubc1c\uc9c0 IP\ubcc4\ub85c \ubcf4\uc5ec\uc918",
    "\ubc29\ud654\ubcbd\uc758 \ucc28\ub2e8 \ud69f\uc218\ub97c \ucd9c\ubc1c\uc9c0 \uc8fc\uc18c\ubcc4\ub85c \uc815\ub9ac\ud574\uc918",
    "80 \ud3ec\ud2b8\uc5d0 \ub300\ud55c \ucc28\ub2e8 \ub85c\uadf8\ub97c \ubc29\ud654\ubcbd\uc5d0\uc11c \ucc3e\uc544\uc918",
    "3389 \ud3ec\ud2b8\ub85c \ub9c9\ud78c \ud1b5\uc2e0\uc744 \ud655\uc778\ud574\uc918",
    "\ub85c\uadf8\uc778 \uc2e4\ud328\ud55c \uacc4\uc815\uc744 \ubcf4\uc5ec\uc918",
    "\uc5b4\uc81c \ub85c\uadf8\uc778 \uc2e4\ud328 \uc0c1\ud0dc\ub97c \uacc4\uc815별\ub85c \ubcf4\uc5ec\uc918",
    "\uc6f9 \uc11c\ubc84 \uc624\ub958 \ub85c\uadf8\ub97c \uc815\ub9ac\ud574\uc918",
    "\uc6f9\uc11c\ubc84\uc5d0\uc11c \uc624\ub958가 생긴 시간대를 찾아줘",
    "timeout 오류 로그만 모아줘",
    "에러 로그에서 timeout이 포함된 메시지를 보여줘",
    "데이터 전송량이 큰 호스트를 많은 순으로 정리해줘",
    "지난주 호스트별 데이터 전송량을 보여줘",
    "직원 IP가 있는 방화벽 로그를 인사 정보와 함께 보여줘",
    "방화벽 로그와 인사 정보를 직원 IP 기준으로 합쳐줘",
    "firewall_logs의 src_ip 컬럼을 할당 IP로 바꿔줘",
    "firewall_logs에서 src_ip를 할당ip로 이름 변경해줘",
    "도착지 IP별 차단 횟수를 보여줘",
    "방화벽 로그의 허용된 통신만 보여줘",
    "최근 하루 방화벽에서 허용된 통신을 보여줘",
]


def test_free_form_operational_requests_generate_without_clarification(monkeypatch):
    monkeypatch.setattr("app.services.query_generator.settings.llm_provider", "mock")
    generator = QueryGenerator(Retriever(shared_index()))
    responses = [generator.generate(GenerateQueryRequest(request=request)) for request in FREE_FORM_REQUESTS]
    assert len(FREE_FORM_REQUESTS) >= 50
    assert all(response.status == "generated" for response in responses)
    assert all(response.query for response in responses)


@pytest.mark.parametrize(
    ("request_text", "expected_parts"),
    [
        ("\ucd5c\uadfc 24\uc2dc\uac04 firewall_logs\uc5d0\uc11c \ucd9c\ubc1c\uc9c0 IP\ubcc4 \ucc28\ub2e8 \uac74\uc218\ub97c \ub9ce\uc740 \uc21c\uc73c\ub85c 20\uac1c \ubcf4\uc5ec\uc918", ["table duration=24h firewall_logs", 'action == "deny"', "stats count by src_ip", "limit 20"]),
        ("443 \ud3ec\ud2b8\ub85c \ub9c9\ud78c \uc811\uc18d\ub9cc \ud655\uc778\ud574\uc918", ["table firewall", 'action == "deny"', "dst_port == 443"]),
        ("\uc5b4\uc81c \ub85c\uadf8\uc778 \uc2e4\ud328\ud55c \uc0ac\uc6a9\uc790\ub4e4\uc744 \uacc4\uc815\ubcc4\ub85c \uc815\ub9ac\ud574\uc918", ["table from=", "auth_logs", 'status == "failure"', "by account_id"]),
        ("\uc6f9 \uc11c\ubc84 \uc624\ub958\uac00 \uac11\uc790\uae30 \ub298\uc5b4\ub09c \uc2dc\uac04\uc744 \ucc3e\uc544\uc918", ["table web_logs", 'severity == "error"', "by _time"]),
        ("\uc778\uc0ac \uc815\ubcf4\ub791 \ubc29\ud654\ubcbd \ub85c\uadf8\ub97c IP \uae30\uc900\uc73c\ub85c \ud569\uccd0\uc11c \ub204\uac00 \ucc28\ub2e8\ub410\ub294\uc9c0 \ubcf4\uace0 \uc2f6\uc5b4", ["table firewall_logs", "join type=inner", "table insa"]),
        ("\uc5d0\ub7ec \ub85c\uadf8\uc5d0\uc11c timeout \uad00\ub828 \uba54\uc2dc\uc9c0\ub9cc \ubaa8\uc544\uc918", ["table app_logs", "message =="]),
        ("\uc9c0\ub09c\uc8fc\uc5d0 \ub370\uc774\ud130 \uc804\uc1a1\ub7c9\uc774 \ud070 \ud638\uc2a4\ud2b8\ub97c \ucc3e\uc544\uc918", ["table from=", "metrics_logs", "sum(bytes)", "by host"]),
    ],
)
def test_free_form_requests_keep_operational_intent(monkeypatch, request_text, expected_parts):
    monkeypatch.setattr("app.services.query_generator.settings.llm_provider", "mock")
    response = QueryGenerator(Retriever(shared_index())).generate(GenerateQueryRequest(request=request_text))
    assert response.status == "generated", response.questions
    assert response.query is not None
    for expected in expected_parts:
        assert expected in response.query


def test_explicit_table_identifier_wins_over_firewall_alias(monkeypatch):
    monkeypatch.setattr("app.services.query_generator.settings.llm_provider", "mock")
    request = "\ucd5c\uadfc 24\uc2dc\uac04 firewall_logs\uc5d0\uc11c \ucd9c\ubc1c\uc9c0 IP\ubcc4 \ucc28\ub2e8 \uac74\uc218\ub97c 20\uac1c \ubcf4\uc5ec\uc918"
    response = QueryGenerator(Retriever(shared_index())).generate(GenerateQueryRequest(request=request))
    assert response.status == "generated"
    assert response.intent.tables[0] == "firewall_logs"
    assert response.query and response.query.startswith("table duration=24h firewall_logs")
