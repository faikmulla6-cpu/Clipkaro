from app.services.asr_policy_v2 import error_rate_v2, normalize_v2
import pytest

@pytest.mark.parametrize(('reference','hypothesis','expected'),[
 ('same words','same words',0),('a b','a x b',.5),('a b c','a c',1/3),('a b','a x',.5),
 ('यह है','यह है।',0),('हे आहे','हे आहे।',0),('क़िला','क़िला',0),
 ('<noise> {school} [music] नमस्ते','नमस्ते',0),('<noise spoken words','noise spoken words',0),
 ('मैं use करता हूँ AI','मैं use करता हूँ ai',0),('HELLO','hello',0),('hello, world!','hello world',0),('क\u200d्ष','क्ष',0),
])
def test_policy_v2_expected_word_rates(reference,hypothesis,expected): assert error_rate_v2(reference,hypothesis,unit='word') == pytest.approx(expected)

def test_policy_v2_does_not_transliterate_hinglish(): assert error_rate_v2('click','क्लिक',unit='word') == 1
