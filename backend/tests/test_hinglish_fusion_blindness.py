from app.services.hinglish_fusion import anonymized_fusion_messages, assert_reference_blind, FUSION_PROMPT_SHA256

def test_fusion_payload_is_deterministic_anonymous_and_reference_blind():
    hypotheses=[{"provider":"provider-one","transcript":"आज meeting cancel हो गई"},{"provider":"provider-two","transcript":"आज मीटिंग cancel हो गई"}]
    messages,mapping=anonymized_fusion_messages("mucs-hinglish-01",hypotheses)
    rendered="\n".join(item['content'] for item in messages)
    assert FUSION_PROMPT_SHA256 and "provider-one" not in rendered and "provider-two" not in rendered
    assert set(mapping.values())=={"provider-one","provider-two"}
    assert_reference_blind(messages)
