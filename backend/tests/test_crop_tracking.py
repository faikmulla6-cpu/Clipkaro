from app.services.crop_tracking import ffmpeg_focus_expression, smooth_crop_keyframes


def test_crop_motion_is_bounded_and_padded():
    rows = smooth_crop_keyframes([{"time": 1, "focus_x": 10}, {"time": 2, "focus_x": 90}], 4)
    assert rows[0]["time"] == 0 and rows[-1]["time"] == 4
    assert rows[2]["focus_x"] <= 28


def test_dynamic_expression_uses_time_interpolation():
    expression = ffmpeg_focus_expression([{"time": 0, "focus_x": 30}, {"time": 3, "focus_x": 70}], 3)
    assert "lt(t" in expression and "(t-0.000)" in expression
