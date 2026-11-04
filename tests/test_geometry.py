from lockstep.core import iou, controls


def box(x, y, w, h):
    return {"x": x, "y": y, "width": w, "height": h}


def test_iou_identical_and_disjoint():
    assert iou(box(0, 0, 10, 10), box(0, 0, 10, 10)) == 1.0
    assert iou(box(0, 0, 10, 10), box(50, 50, 10, 10)) == 0.0


def test_iou_partial_overlap():
    assert 0.3 < iou(box(0, 0, 10, 10), box(5, 0, 10, 10)) < 0.4


def test_controls_parses_aria_snapshot():
    snap = '- link "Reports"\n- button "Export to CSV"\n- heading "Reports"'
    assert controls(snap) == {("link", "Reports"), ("button", "Export to CSV")}
