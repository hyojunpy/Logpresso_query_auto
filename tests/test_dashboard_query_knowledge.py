from app.services.dashboard_query_knowledge import DashboardQueryKnowledge


def test_matches_dashboard_titles_and_aliases_case_insensitively():
    knowledge = DashboardQueryKnowledge.bundled()
    assert knowledge.match("라이선스 만료일 보여줘")["title"] == "라이선스 만료일"
    assert knowledge.match("LICENSE EXPIRY 확인")["title"] == "라이선스 만료일"
    assert knowledge.match("어제 수집기별 수집량 알려줘")["title"] == "전일 수집기별 수집량"
