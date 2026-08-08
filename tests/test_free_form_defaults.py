from app.models.request import GenerateQueryRequest
from app.services.intent_parser import IntentParser


def test_infers_allow_filter_for_firewall_request():
    intent = IntentParser().parse(GenerateQueryRequest(request="\ubc29\ud654\ubcbd \ub85c\uadf8\uc5d0\uc11c \ud5c8\uc6a9\ub41c \ud1b5\uc2e0\ub9cc \ubcf4\uc5ec\uc918"))
    assert any(item.field == "action" and item.value == "allow" for item in intent.filters)


def test_infers_destination_ip_counting_without_catalog():
    intent = IntentParser().parse(GenerateQueryRequest(request="\ub3c4\ucc29\uc9c0 IP\ubcc4 \ucc28\ub2e8 \ud69f\uc218\ub97c \ubcf4\uc5ec\uc918"))
    assert intent.tables == ["firewall_logs"]
    assert intent.group_by == ["dst_ip"]
    assert intent.aggregations[0].function == "count"
