"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |

Gợi ý
- Mép trái = x - w/2, mép phải = x + w/2 (xem câu hỏi "dòng YOLO nào lỗi?" trong slide).
- Một dòng hỏng (BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO) thì `continue`, đừng kiểm tiếp hình học của dòng đó.
- Dòng thiếu cột làm script của slide dừng giữa chừng: đây là lý do phải `try/except`.
- `iou_xywh(a, b)` có sẵn trong common.py.
- Ngưỡng nằm trong `cfg["label_format"]` — đừng viết cứng số vào code.
"""
from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401


def _overflow(cx, cy, w, h) -> float:
    """Mức tràn lớn nhất của box ra khỏi khung [0,1] (0 nếu nằm gọn)."""
    left, top = cx - w / 2, cy - h / 2
    right, bottom = cx + w / 2, cy + h / 2
    return max(0.0, -left, -top, right - 1.0, bottom - 1.0)


def run(ds, cfg):
    lf = cfg["label_format"]
    tol = lf["overflow_tol"]
    min_px = lf["min_box_px"]
    max_frac = lf["max_box_frac"]
    dup_iou = lf["dup_box_iou"]
    n_classes = len(ds.classes)

    issues = []
    for p in ds.image_files():
        stem = p.stem
        lines = ds.read_label_lines(stem)
        if lines is None:
            continue                                  # thiếu file nhãn: check khác báo
        size = ds.image_size(stem)
        seen = []                                     # các box hợp lệ đã gặp: (id, cx, cy, w, h)
        for line_no, text in lines:
            try:
                cls, cx, cy, w, h = parse_yolo_line(text)
            except ValueError:
                issues.append(Issue("label_format", ERROR, "BAD_FORMAT", stem,
                                    f"dòng không đúng 5 cột số: {text!r}", line_no))
                continue

            if not (0 <= cls < n_classes):
                issues.append(Issue("label_format", ERROR, "BAD_CLASS_ID", stem,
                                    f"ID lớp {cls} ngoài 0..{n_classes - 1}", line_no,
                                    {"id": cls}))
                continue

            if w <= 0 or h <= 0:
                issues.append(Issue("label_format", ERROR, "BOX_ZERO", stem,
                                    f"box rộng/cao <= 0 (w={w}, h={h})", line_no))
                continue

            over = _overflow(cx, cy, w, h)
            if over > tol:
                issues.append(Issue("label_format", ERROR, "BOX_OUT_OF_IMAGE", stem,
                                    f"box tràn ảnh {over:.4f} > {tol}", line_no,
                                    {"overflow": round(over, 6)}))

            dup = next((s for s in seen if s[0] == cls and iou_xywh((cx, cy, w, h), s[1:]) > dup_iou), None)
            if dup is not None:
                issues.append(Issue("label_format", ERROR, "DUP_BOX", stem,
                                    f"box lặp lớp {cls} (IoU > {dup_iou})", line_no))
            else:
                seen.append((cls, cx, cy, w, h))

            if size is not None:
                short_px = min(w * size[0], h * size[1])
                if short_px < min_px:
                    issues.append(Issue("label_format", WARN, "BOX_TINY", stem,
                                        f"cạnh ngắn {short_px:.1f}px < {min_px}px", line_no,
                                        {"short_px": round(short_px, 2)}))

            if w * h > max_frac:
                issues.append(Issue("label_format", WARN, "BOX_HUGE", stem,
                                    f"box chiếm {w * h:.2f} diện tích > {max_frac}", line_no,
                                    {"frac": round(w * h, 4)}))
    return issues
