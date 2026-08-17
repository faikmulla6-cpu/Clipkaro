from app.services.hinglish_fusion import anonymized_fusion_messages,assert_reference_blind

def test_nvidia_payload_contains_only_anonymized_hypotheses():
    messages,mapping=anonymized_fusion_messages('mucs-hinglish-01',[{'provider':'hidden-a','transcript':'आज meeting cancel हो गई'},{'provider':'hidden-b','transcript':'आज मीटिंग cancel हो गई'}])
    joined='\n'.join(m['content'] for m in messages)
    assert 'hidden-a' not in joined and 'hidden-b' not in joined
    assert 'reference transcript' not in joined.lower() and 'wer' not in joined.lower() and 'cer' not in joined.lower()
    assert mapping and assert_reference_blind(messages) is None
