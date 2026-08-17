from app.services.roman_hinglish_display_v1 import display_text
def test_display_spelling():assert display_text('kitane kisee ceej calegaa aaegee matalab bacce rahaa')=='kitne kisi cheez chalega aayegi matlab bacche raha'
def test_protection():assert display_text('engineering meeting client timing YouTube IIT SRM')=='engineering meeting client timing YouTube IIT SRM'
def test_safety():assert display_text("123, car client! don't")=='123, car client! don\'t'
