"""CHECK 6 — Ý kiến thứ hai: so nhãn với một model LỚN HƠN (yolo26l).   ★★★ (khó nhất, đáng điểm nhất)

Test:  pytest tests/test_second_opinion.py -q

Máy kiểm quy tắc, người kiểm ý nghĩa (slide). Các lỗi như thiếu nhãn / gán nhầm lớp hợp lệ / box lỏng
KHÔNG bắt được bằng quy tắc cú pháp. Ta nhờ một model mạnh hơn "nhìn lại" và CHỈ CẢNH BÁO (model cũng có thể sai):
những ảnh bị cờ sẽ vào hàng đợi cho NGƯỜI duyệt.

`preds[stem]` = list `[id_lớp, conf, cx, cy, w, h]` của model (lấy qua `get_preds(ds, cfg, "checker")` nếu preds=None).
`L = ds.valid_boxes(stem)` = list `(id_lớp, cx, cy, w, h)` của nhãn (đã bỏ dòng hỏng).
Ngưỡng ở `cfg["second_opinion"]`: conf, min_area_px, fp_conf, iou_missing, iou_match, iou_loose.

Thuật toán gợi ý, với từng ảnh (bỏ qua ảnh không có trong preds hoặc không có file nhãn):
  P = dự đoán có conf >= conf  VÀ diện tích px (w*W * h*H) >= min_area_px
  Với mỗi dự đoán r trong P: lấy các nhãn có IoU(r, nhãn) >= iou_missing  (cands)
   - không có cands                            -> POSSIBLE_MISSING     (model thấy vật mà nhãn không có box)
   - có cands cùng lớp, tốt nhất IoU < iou_loose -> POSSIBLE_LOOSE_BOX  (đúng vật, box lỏng/lệch)
   - không có cands cùng lớp, nhưng cands tốt nhất IoU >= iou_match (khác lớp) -> POSSIBLE_WRONG_CLASS
  Với mỗi dòng nhãn hợp lệ: nếu IoU với MỌI dự đoán (conf >= fp_conf, không lọc diện tích) đều < iou_missing
                                             -> POSSIBLE_FALSE_POS  (box nhãn không khớp vật nào model thấy; Issue.line = số dòng)

Chi tiết các ca biên (test kiểm đúng các ca này)
- `cands` gồm nhãn MỌI lớp có IoU >= iou_missing; "tốt nhất cùng lớp" = cands cùng lớp có IoU lớn nhất; "tốt nhất khác lớp" tương tự với cands khác lớp.
- Thứ tự quyết định cho mỗi dự đoán: (1) cands rỗng -> MISSING. (2) có cands cùng lớp: IoU tốt nhất < iou_loose -> LOOSE_BOX, ngược lại KHÔNG cờ
  (nhãn đúng lớp đã phủ vật này, kể cả khi còn nhãn khác lớp chồng lên). (3) không có cands cùng lớp: nếu IoU tốt nhất khác lớp >= iou_match -> WRONG_CLASS;
  nếu chỉ có khác lớp với IoU trong [iou_missing, iou_match) -> không cờ gì (mơ hồ: để cho FALSE_POS / lần duyệt khác).
- Một dự đoán sinh tối đa MỘT issue (MISSING / LOOSE_BOX / WRONG_CLASS); một ảnh có thể có nhiều issue.
- Thứ tự issue: theo `ds.image_files()` rồi theo thứ tự dự đoán trong `preds[stem]`, cuối cùng là các FALSE_POS theo số dòng; `Issue.image` = stem, `Issue.line` chỉ đặt cho FALSE_POS.

Lưu ý số dòng: dùng `ds.read_label_lines(stem)` (giữ số dòng gốc, kể cả dòng hỏng/trống) để lấy `Issue.line`; `valid_boxes` KHÔNG giữ số dòng.

Tất cả severity WARN; `Issue.extra` nên có {"conf": ...} hoặc {"iou": ...} (hàng đợi duyệt dùng conf để xếp ưu tiên).

Gợi ý
- `iou_xywh` có sẵn. Dòng nhãn hỏng không được làm script chết (dùng `ds.valid_boxes` và `parse_yolo_line` trong try).
- Kết quả phụ thuộc mạnh vào ngưỡng: calibrate chúng ở Bước 3 thay vì đoán.
"""
from ..common import WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401
from ..model_cache import get_preds  # noqa: F401


def run(ds, cfg, preds=None):
    so = cfg["second_opinion"]
    conf = so["conf"]
    min_area = so["min_area_px"]
    fp_conf = so["fp_conf"]
    iou_missing = so["iou_missing"]
    iou_match = so["iou_match"]
    iou_loose = so["iou_loose"]
    n_classes = len(ds.classes)

    if preds is None:
        preds = get_preds(ds, cfg, "checker")

    issues = []
    for p in ds.image_files():
        stem = p.stem
        if stem not in preds:
            continue                                   # model không có ý kiến về ảnh này
        lines = ds.read_label_lines(stem)
        if lines is None:
            continue                                   # không có file nhãn: check khác lo
        valid = ds.valid_boxes(stem)                   # các nhãn parse được, ID hợp lệ
        size = ds.image_size(stem)

        # P: dự đoán đủ tin cậy VÀ đủ lớn (guideline: vật quá nhỏ không gán)
        P = []
        for r in preds[stem]:
            rcls, rconf, cx, cy, w, h = r
            if rconf < conf:
                continue
            if size is not None and (w * size[0]) * (h * size[1]) < min_area:
                continue
            P.append((rcls, rconf, cx, cy, w, h))

        # 1) Mỗi dự đoán trong P sinh tối đa một issue
        for rcls, rconf, cx, cy, w, h in P:
            rbox = (cx, cy, w, h)
            cands = []                                 # (nhãn_cls, iou) các nhãn khớp vật này
            for lbl in valid:
                if iou_xywh(rbox, lbl[1:]) >= iou_missing:
                    cands.append((lbl[0], iou_xywh(rbox, lbl[1:])))
            if not cands:
                issues.append(Issue("second_opinion", WARN, "POSSIBLE_MISSING", stem,
                                    f"model thấy vật (conf {rconf:.2f}) nhưng nhãn không có box",
                                    None, {"conf": round(rconf, 4)}))
                continue
            same = [iou for lc, iou in cands if lc == rcls]
            if same:
                if max(same) < iou_loose:
                    issues.append(Issue("second_opinion", WARN, "POSSIBLE_LOOSE_BOX", stem,
                                        f"đúng vật nhưng box lỏng (IoU {max(same):.2f})",
                                        None, {"iou": round(max(same), 4), "conf": round(rconf, 4)}))
                # else: nhãn cùng lớp đã phủ vật -> không cờ
            else:
                other = [iou for lc, iou in cands if lc != rcls]
                if other and max(other) >= iou_match:
                    issues.append(Issue("second_opinion", WARN, "POSSIBLE_WRONG_CLASS", stem,
                                        f"cùng vị trí nhưng khác lớp (model {rcls}, IoU {max(other):.2f})",
                                        None, {"iou": round(max(other), 4), "conf": round(rconf, 4)}))
                # else: mơ hồ (IoU trong [iou_missing, iou_match)) -> không cờ

        # 2) Box nhãn không khớp vật nào model thấy -> POSSIBLE_FALSE_POS (theo số dòng)
        all_pred_boxes = [(r[2], r[3], r[4], r[5]) for r in preds[stem] if r[1] >= fp_conf]
        if all_pred_boxes:
            for line_no, text in lines:
                try:
                    b = parse_yolo_line(text)
                except ValueError:
                    continue
                if not (0 <= b[0] < n_classes):
                    continue
                lblbox = b[1:]
                best = max(iou_xywh(lblbox, pb) for pb in all_pred_boxes)
                if best < iou_missing:
                    issues.append(Issue("second_opinion", WARN, "POSSIBLE_FALSE_POS", stem,
                                        f"box nhãn không khớp dự đoán nào (IoU {best:.2f})",
                                        line_no, {"iou": round(best, 4)}))
    return issues
