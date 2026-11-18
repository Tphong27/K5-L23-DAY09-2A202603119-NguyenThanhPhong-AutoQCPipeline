# Báo cáo Day 09 — Nguyễn Thanh Phong, 2A202603119

## 1. Kết luận trước

Pipeline trả về **HOLD**, không phải Release cũng không phải Rework. Từ 224 ảnh raw, bước intake loại 21 ảnh (hỏng, nhỏ, trùng, rò rỉ test), còn 203 ảnh đi tiếp. Sau khi autofix và cho người duyệt mô phỏng (ngân sách 80 ảnh), vẫn còn 44 ảnh (21.67%) mang cảnh báo chưa được ai xác nhận — vượt ngưỡng 10% nên gate giữ ở Hold.

Lý do chính khiến mình không dám Release: phần lớn cảnh báo còn lại là lỗi ngữ nghĩa (box lỏng, nghi thiếu nhãn, nghi sai lớp) — máy chỉ *nghi ngờ* được chứ không khẳng định. Với 80 ảnh duyệt mà hàng đợi tới 130 ảnh, vẫn còn 50 ảnh chưa ai xem. Release lúc này là đánh cược vào những chỗ mình chưa kiểm.

## 2. Lỗi và phân việc

Số liệu mình lấy từ `02_error_list_v1.csv` (trước khi sửa). Tổng cộng 57 lỗi bắt buộc (ERROR) và 171 cảnh báo (WARN). Trong đó 21 lỗi ERROR bị loại ngay ở bước intake, 36 lỗi vào thẳng vòng QC.

| Mã lỗi | Số dòng | Ai xử lý | Vì sao |
|---|---:|---|---|
| CORRUPT_IMAGE | 2 | máy (intake) | ảnh không mở được, loại luôn |
| BAD_SIZE | 3 | máy (intake) | cạnh ngắn < 250px, dưới chuẩn dự án |
| DUP_IMAGE_EXACT | 8 | máy (intake) | trùng từng byte (md5) |
| DUP_IMAGE_NEAR | 3 | máy (intake) | ảnh thu nhỏ/đổi sáng, md5 không bắt được |
| LEAK_TEST | 5 | máy (intake) | trùng ảnh trong test/gold_val, để lại là rò rỉ metric |
| BAD_CLASS_ID | 6 | máy (autofix) | ID 93, 4, -1, 7 — ngoài 0..3, xoá dòng |
| BAD_FORMAT | 3 | máy (autofix) | dòng thiếu cột hoặc có NaN, xoá dòng |
| BOX_ZERO | 4 | máy (autofix) | w hoặc h bằng 0, xoá dòng |
| DUP_BOX | 7 | máy (autofix) | hai box cùng lớp chồng gần hết (IoU>0.9), xoá dòng sau |
| BOX_OUT_OF_IMAGE | 8 | máy (autofix) | box tràn ảnh, cắt về [0,1] |
| BAD_CLASS_NAME | 2 | máy (autofix) | 'Person', 'Bus' viết hoa sai, sửa data.yaml |
| MISSING_LABEL_FILE | 6 | người | ảnh không có file nhãn; máy không bịa được, chuyển người gán |
| BOX_TINY | 6 | người | cạnh ngắn < 12px — có thể là vật thật nhỏ, người quyết |
| BOX_HUGE | 3 | người | box chiếm > 95% ảnh, nghi box phình |
| EMPTY_LABEL | 12 | người | file nhãn rỗng: ảnh nền thật hay thiếu nhãn? |
| CLASS_RARE | 4 | người | lớp quá ít box, coi chừng mất cân bằng |
| POSSIBLE_MISSING | 68 | người | model thấy vật mà nhãn không có box |
| POSSIBLE_LOOSE_BOX | 31 | người | đúng vật nhưng box lỏng, IoU thấp |
| POSSIBLE_FALSE_POS | 29 | người | box nhãn không khớp vật nào model thấy |
| POSSIBLE_WRONG_CLASS | 18 | người | cùng chỗ nhưng khác lớp (xe tải ↔ bus…) |

Autofix chạy tổng cộng 35 thay đổi (`03_fixes.csv`): xoá 20 dòng, cắt 8 box, sửa 1 lần data.yaml, và 6 dòng needs_label cho ảnh thiếu nhãn.

Về `05_review_queue.csv`: hàng đợi xếp theo trọng số trong config, nên ảnh thiếu nhãn (NEEDS_LABEL, 10 điểm) và nghi sai lớp (WRONG_CLASS, 3 điểm) lên đầu, rồi tới MISSING/FALSE_POS (2 điểm), cuối là LOOSE_BOX (1.5) và tiny/huge. Ngân sách 80 ảnh nên người xem được các ca ngữ nghĩa nặng nhất trước; 50 ảnh còn lại đa số là box lỏng/tiny chưa ai xác nhận. Mình thấy cách xếp này hợp lý vì sửa sai lớp đắt hơn nhiều so với bỏ sót một box nhỏ.

## 3. Calibration (2 ngưỡng)

| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do |
|---|---|---|---|---|
| `duplicates.phash_dist` | 2 | **8** | DUP_IMAGE_NEAR: 1.00/0.50 → 1.00/0.67 | Bắt thêm được cặp trùng gần, không loại oan ảnh khác |
| `second_opinion.conf` | 0.25 | **0.5** | MISSING: 0.50/1.00 → 0.57/1.00 | Tăng precision mà recall vẫn giữ nguyên 1.00 |

Mình không chỉ nhìn F1 cao nhất trên bộ calib mà đo thêm trên lô raw thật, vì calib chỉ có 39 ảnh. Với `phash_dist`, calib đẩy lên 16 thì F1 đẹp hơn, nhưng khi soi trên raw mình thấy dist=16 bắt thêm 3 cặp có Hamming tận 16 (img_0011~img_0008, img_0084~img_0074, img_0177~img_0113) — rất dễ gộp nhầm hai ảnh thật ra khác nhau. Còn dist=20 thì loại tới 134/224 ảnh, gần như xoá sạch lô. Nên mình dừng ở 8.

Với `second_opinion.conf`, mình chọn 0.5 vì đây là điểm calib cho F1 của MISSING cao nhất (0.73), đồng thời số ảnh bị cảnh báo trên raw giảm từ 137 (ở 0.25) xuống 119 — hàng đợi bớt ảo mà vẫn không mất ca MISSING nào (recall = 1.00).

**Chỗ calibration có thể đánh lừa:** bộ calib chỉ 39 ảnh nên phân bố của nó không đại diện cho 224 ảnh raw. Mình đã tự kiểm bằng hai cách. Thứ nhất, nhìn các cặp ảnh bị cho là trùng: có cặp Hamming=0 (thực sự giống), nhưng nếu chọn dist cao thì lẫn cả cặp Hamming=16 — mắt người nhìn mới biết có nên gộp hay không. Thứ hai, đếm số ảnh bị loại ở bước 1 theo từng mức dist: 8 thì loại 16 ảnh (hợp lý), 20 thì loại 134 ảnh (rõ ràng sai). Đây chính là kiểu "ngưỡng khớp calib nhưng hại dữ liệu thật".

## 4. Cửa chặn và điều pipeline KHÔNG bắt được

**(a) Gate chặn có thật.** Mình chạy `python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb` để mô phỏng "không có người duyệt". Kết quả đúng như mong đợi: còn 6 lỗi `MISSING_LABEL_FILE` (ảnh chưa có nhãn, máy không tự bịa), gate trả về **Rework**, mã thoát **20**, và bước 5 ghi rõ "KHÔNG xuất". Kiểm lại thì thư mục `work/exp_nb/clean_v1` không hề được tạo — cửa chặn thực sự chặn, không phải chỉ in chữ rồi vẫn xuất.

**(b) Hai thứ pipeline không bắt được, mình thấy rõ trong lô này:**

- **Box lỏng nhẹ.** Nhiều ca IoU rơi vào khoảng 0.45–0.49 (ví dụ img_0018 = 0.45, img_0021 = 0.49). Vì ngưỡng `iou_missing` là 0.3 nên máy vẫn coi là "có khớp", chỉ gắn cảnh báo LOOSE_BOX chứ không khẳng định sai. Thực tế box có thể đã phình hoặc lệch đủ để hại khi train, nhưng chỉ mắt người mới phân định được.

- **Nhầm lớp mà model lớn cũng nhầm.** Ví dụ img_0024 bị cờ WRONG_CLASS (model đoán lớp 2, nhãn là lớp 1). Nhưng nếu chính yolo26l cũng nhìn ra lớp 2 thì second_opinion không có "ý kiến khác" để đối chiếu — hai bên cùng sai thì im lặng. Những ca xe tải/bus/car giống nhau về hình dáng là điểm mù cố hữu của cách kiểm này.

Ngoài ra còn một điểm mù thứ ba mình muốn ghi: **ảnh trùng bị biến đổi mạnh** (cắt cúp, lật, đổi khung) làm phash nhảy xa, vượt cả Hamming 16, nên pipeline coi là ảnh khác. Bộ lọc trùng hiện tại chỉ bắt được trùng gần như nguyên bản.

## 5. Train: raw vs clean

Chưa chạy. Mình quyết định không train trên Colab lần này vì hai lý do. Thứ nhất, kết luận đang là Hold, bản `clean_v1` mới là nháp chứ chưa phải bản phát hành, đem train so sánh lúc này dễ bị hiểu sai là "đã sạch". Thứ hai, tập test chỉ 100 ảnh nên chênh lệch mAP giữa raw và clean khó vượt được độ nhiễu giữa các seed — làm vội rồi báo "clean tốt hơn" sẽ thiếu trung thực.

Nếu làm sau, mình sẽ giữ nguyên val/test, 2 seed mỗi biến thể, cùng siêu tham số, rồi so chênh lệch mAP50 với độ lệch chuẩn giữa seed. Giả thuyết cần kiểm: ảnh trùng/rò rỉ test còn sót trong raw có thể làm điểm raw *bị thổi lên*, còn nhãn máy chưa sửa trong clean có thể làm điểm clean *bị kéo xuống* — cả hai đều khiến kết luận "clean hơn raw" đáng ngờ.

## 6. Quyết định và ghi chú AI

**(a) Quyết định:** giữ **HOLD**. Để lên được Release thì cần một trong hai: người duyệt thêm phần 50 ảnh còn lại (nâng ngân sách hoặc duyệt nhiều vòng), hoặc siết `second_opinion.conf` cao hơn để giảm số cảnh báo xuống dưới 10% — nhưng cách sau đánh đổi bằng việc bỏ sót lỗi, nên mình không muốn tự ý làm để "đạt" Release.

**(b) Dùng AI:** có dùng để hỗ trợ viết code, nhưng mình đọc lại và kiểm từng phần.
- *Prompt chính:* mình dán nguyên docstring của module (ví dụ `label_format`) kèm một test mẫu, yêu cầu viết hàm trả về list Issue, chỉ đọc file không sửa, lấy ngưỡng từ `cfg`.
- *Cách kiểm:* đọc lướt xem có chỗ nào xoá/ghi đè file ngoài ý muốn hay nuốt lỗi bằng `except: pass`; chạy `pytest` cho từng module; chạy thêm trên tập calib và lô raw qua `make run`; soát lại xem có hardcode ngưỡng nào không (phải lấy từ config).
- *Một lần AI sai:* bản `autofix` đầu tiên xử lý `BOX_OUT_OF_IMAGE` bằng cách vừa đưa vào danh sách xoá dòng vừa đưa vào danh sách cắt box, nên test `test_clip_box` đỏ. Mình sửa lại cho đúng ý đồ: box tràn thì cắt, chỉ khi cắt xong không còn diện tích mới xoá dòng.

*(Không làm phần thưởng CVAT.)*
