"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict  # noqa: F401

import yaml  # noqa: F401

from ..common import ERROR, parse_yolo_line  # noqa: F401


def fix(ds, issues, cfg):
    """Sửa tự động lỗi ERROR. Trả list[dict] ghi lại thay đổi."""
    fixes = []
    
    # Phân loại issue theo image
    to_remove_images = set()
    drop_lines = defaultdict(set)  # image → set(line_no) để xoá
    clip_lines = defaultdict(dict)  # image → {line_no: None} để thử clip
    needs_label_images = set()
    bad_class_name = False

    for issue in issues:
        if issue.severity != ERROR:
            continue
        
        if issue.code == "MISSING_LABEL_FILE":
            needs_label_images.add(issue.image)
        elif issue.code in ("DUP_IMAGE_EXACT", "DUP_IMAGE_NEAR", "LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"):
            to_remove_images.add(issue.image)
        elif issue.code == "BAD_CLASS_NAME":
            bad_class_name = True
        elif issue.code in ("BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"):
            drop_lines[issue.image].add(issue.line)
        elif issue.code == "BOX_OUT_OF_IMAGE":
            # Thử clip trước; nếu toàn nằm ngoài → drop
            clip_lines[issue.image][issue.line] = None

    # 1. Xoá ảnh
    for stem in to_remove_images:
        img_path = ds.image_path(stem)
        if img_path and img_path.exists():
            img_path.unlink()
        lbl_path = ds.label_path(stem)
        if lbl_path.exists():
            lbl_path.unlink()
        fixes.append({"image": stem, "line": None, "action": "remove_image", "before": "", "after": ""})

    # 2. Sửa tên lớp
    if bad_class_name:
        yaml_path = ds.yaml_path
        if yaml_path.exists():
            data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
            data["names"] = cfg["classes"]
            yaml_path.write_text(
                yaml.dump(data, default_flow_style=False, allow_unicode=True),
                encoding="utf-8"
            )
        fixes.append({"image": "data.yaml", "line": None, "action": "rename_classes", "before": "", "after": ""})

    # 3. Sửa dòng nhãn (drop + clip)
    for stem in sorted(set(drop_lines.keys()) | set(clip_lines.keys())):
        lines_data = ds.read_label_lines(stem)
        if lines_data is None:
            continue

        # Danh sách dòng cần xoá (ưu tiên: drop trước clip)
        to_drop = drop_lines.get(stem, set())
        to_clip = clip_lines.get(stem, {})
        
        # Đọc tất cả dòng (kể cả dòng trống)
        all_lines = ds.label_path(stem).read_text(encoding="utf-8", errors="replace").splitlines()
        new_lines = []
        
        for line_idx, text in enumerate(all_lines, 1):
            # Nếu cần drop thì drop (không ghi fix clip)
            if line_idx in to_drop:
                fixes.append({
                    "image": stem,
                    "line": line_idx,
                    "action": "drop_line",
                    "before": text,
                    "after": ""
                })
                continue
            
            # Nếu cần clip
            if line_idx in to_clip:
                try:
                    cls, cx, cy, w, h = parse_yolo_line(text)
                    # Cắt box về [0,1]
                    left = max(0.0, cx - w / 2)
                    right = min(1.0, cx + w / 2)
                    top = max(0.0, cy - h / 2)
                    bottom = min(1.0, cy + h / 2)
                    
                    new_w = right - left
                    new_h = bottom - top
                    
                    # Nếu box toàn nằm ngoài ảnh → drop
                    if new_w <= 0 or new_h <= 0:
                        fixes.append({
                            "image": stem,
                            "line": line_idx,
                            "action": "drop_line",
                            "before": text,
                            "after": ""
                        })
                        continue
                    
                    # Còn diện tích → clip
                    new_cx = left + new_w / 2
                    new_cy = top + new_h / 2
                    new_line = f"{cls} {new_cx:.6g} {new_cy:.6g} {new_w:.6g} {new_h:.6g}"
                    
                    fixes.append({
                        "image": stem,
                        "line": line_idx,
                        "action": "clip_box",
                        "before": text,
                        "after": new_line
                    })
                    new_lines.append(new_line)
                except (ValueError, Exception):
                    # Dòng hỏng: giữ nguyên (không sửa)
                    new_lines.append(text)
            else:
                # Dòng bình thường: giữ nguyên
                new_lines.append(text)
        
        # Ghi lại file
        content = "\n".join(new_lines)
        if new_lines:
            content += "\n"
        ds.label_path(stem).write_text(content, encoding="utf-8")

    # 4. Ghi needs_label
    for stem in needs_label_images:
        fixes.append({
            "image": stem,
            "line": None,
            "action": "needs_label",
            "before": "(không có file)",
            "after": "chuyển người gán"
        })

    return fixes
