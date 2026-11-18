# Báo cáo Day 09 — Nguyễn Thanh Phong, 2A202603119

## 1. Kết luận trước

Pipeline kết luận **Hold**. Ban đầu có 224 ảnh; bước nhận dữ liệu loại 21 ảnh và giữ 203 ảnh. Sau khi máy sửa lỗi và người duyệt mô phỏng xem 80 ảnh, còn **44/203 ảnh (21,67%)** có cảnh báo chưa được xác nhận. Tỉ lệ này cao hơn ngưỡng Hold 10%. Vòng kiểm cuối không còn lỗi bắt buộc, nên kết quả không phải Rework. Bộ `clean_v1` đã xuất chỉ là **bản nháp**, chưa phải dữ liệu được phát hành.

## 2. Lỗi và phân việc

Tôi đếm theo `02_error_list_v1.csv`, trước khi sửa: **57 dòng lỗi bắt buộc và 171 dòng cảnh báo**. Trong 57 lỗi có 21 lỗi ở bước nhận dữ liệu (224 ảnh ban đầu); 36 lỗi còn lại thuộc vòng kiểm trên 203 ảnh được giữ. Một ảnh có thể có nhiều dòng lỗi, nên không thể lấy 171 chia cho 203 để ra tỉ lệ ảnh cảnh báo.

| Mã lỗi               | Số dòng | Cách xử lý                            |
| -------------------- | ------: | ------------------------------------- |
| CORRUPT_IMAGE        |       2 | Máy loại ảnh hỏng                     |
| BAD_SIZE             |       3 | Máy loại ảnh có cạnh ngắn dưới 250 px |
| DUP_IMAGE_EXACT      |       8 | Máy loại ảnh trùng byte               |
| DUP_IMAGE_NEAR       |       3 | Máy loại ảnh gần trùng theo pHash     |
| LEAK_TEST            |       5 | Máy loại ảnh trùng với tập test/val   |
| BAD_CLASS_ID         |       6 | Máy xoá dòng có ID ngoài 0–3          |
| BAD_FORMAT           |       3 | Máy xoá dòng không đúng định dạng     |
| BOX_ZERO             |       4 | Máy xoá box không có diện tích        |
| DUP_BOX              |       7 | Máy xoá dòng box lặp                  |
| BOX_OUT_OF_IMAGE     |       8 | Máy cắt box về trong ảnh              |
| BAD_CLASS_NAME       |       2 | Máy sửa tên lớp trong `data.yaml`     |
| MISSING_LABEL_FILE   |       6 | Người gán nhãn; máy không tự tạo nhãn |
| BOX_TINY             |       6 | Người xem vật nhỏ có cần gán không    |
| BOX_HUGE             |       3 | Người kiểm tra box quá lớn            |
| EMPTY_LABEL          |      12 | Người xác định ảnh nền hay thiếu nhãn |
| CLASS_RARE           |       4 | Người kiểm tra lớp ít box             |
| POSSIBLE_MISSING     |      68 | Người kiểm tra vật có bị bỏ sót không |
| POSSIBLE_LOOSE_BOX   |      31 | Người kiểm tra box có lỏng không      |
| POSSIBLE_FALSE_POS   |      29 | Người kiểm tra box có thừa không      |
| POSSIBLE_WRONG_CLASS |      18 | Người kiểm tra lớp có sai không       |

`03_fixes.csv` ghi **35 mục**: xoá 20 dòng, cắt 8 box, sửa tên lớp 1 lần và ghi 6 mục `needs_label`. `needs_label` chỉ chuyển việc cho người, không phải đã sửa xong. Hàng đợi `05_review_queue.csv` có 130 ảnh. Điểm ưu tiên được cộng từ các cảnh báo và các lần máy sửa trên cùng ảnh; ảnh thiếu file nhãn được điểm cao để người xem sớm. Người duyệt mô phỏng xử lý 80 ảnh, còn 50 ảnh trong hàng đợi chưa xem. Ở vòng cuối có 88 dòng cảnh báo trên 74 ảnh; sau khi trừ các ảnh đã duyệt, gate tính **44 ảnh chưa xác nhận**.

## 3. Calibration hai ngưỡng

| Ngưỡng                  | Ban đầu → chọn | Precision / recall trên calib             | Lý do                                                                                                                                                                        |
| ----------------------- | -------------- | ----------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `duplicates.phash_dist` | 2 → **8**      | `DUP_IMAGE_NEAR`: 1,00/0,50 → 1,00/0,67   | Trên raw, mức 8 phát hiện thêm `img_0223` gần trùng `img_0077` và `img_0101` trùng với ảnh test so với mức 4. Đây vẫn là quyết định cần kiểm bằng mắt khi dùng dữ liệu khác. |
| `second_opinion.conf`   | 0,25 → **0,5** | `POSSIBLE_MISSING`: 0,50/1,00 → 0,57/1,00 | Giảm cảnh báo sai của loại này trên calib mà chưa mất ca lỗi chèn nào.                                                                                                       |

`phash_dist=4` và `8` cho **cùng precision/recall trên calib**; riêng kết quả calib không đủ để chọn 8. Tôi dùng thêm kết quả trên raw như bảng trên, nhưng không thể suy từ pHash rằng hai ảnh chắc chắn là một. Ở mức 16, số ảnh raw bị báo trùng hoặc rò rỉ tăng từ 16 lên 26; ở mức 20 là 134. Mức cao có nguy cơ loại nhầm ảnh nên tôi không chọn. Bộ calib chỉ có 39 ảnh, vì vậy các tỉ lệ thay đổi mạnh khi bắt thêm hoặc bỏ sót một ca.

`conf=0,5` cũng có giới hạn: trên calib, `POSSIBLE_LOOSE_BOX` chỉ bắt được **1/5 ca chèn** (recall 0,20); `POSSIBLE_FALSE_POS` có **5 cờ đúng và 9 cờ sai** (precision khoảng 0,36). Vì thế tôi không xem cảnh báo của model là kết luận cuối cùng. Calib là dữ liệu có lỗi chèn, còn raw có thể có lỗi khác; kết quả calib không chứng minh pipeline bắt hết lỗi trên raw.

## 4. Cửa chặn và điểm mù

- Tôi đã thử chạy `python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb`. Khi không có người gán, 6 ảnh vẫn thiếu file nhãn; gate trả **Rework**, mã thoát **20** và không tạo `work/exp_nb/clean_v1`. Thử nghiệm dùng thư mục `work/` riêng nên không ghi đè báo cáo nộp bài.

- Tôi thấy ít nhất hai giới hạn.

* Thứ nhất, model chỉ gắn **cảnh báo**, không xác nhận đúng sai của box và lớp. Ví dụ `img_0018` và `img_0021` bị báo `POSSIBLE_LOOSE_BOX` với IoU lần lượt khoảng 0,45 và 0,49; cần người mở ảnh để quyết định sửa. Nếu model và nhãn cùng sai theo một cách, phép so sánh cũng có thể không báo gì; tôi chưa có bằng chứng để khẳng định trường hợp đó đã xảy ra ở ảnh nào trong lô này.
* Thứ hai, bộ lọc pHash có thể bỏ sót ảnh trùng bị biến đổi mạnh. Ngay trên calib, ở ngưỡng đã chọn nó chỉ bắt **4/6** ca gần trùng được chèn. Hai điểm này khiến tôi không thể gọi bộ dữ liệu là hoàn toàn sạch.

## 5. Train raw và clean

**Chưa chạy** phần train, nên tôi không có số mAP để kết luận clean tốt hơn raw. Nếu làm tiếp, tôi sẽ giữ cùng tập val/test, model, siêu tham số và ít nhất hai seed cho mỗi biến thể, rồi so mức chênh lệch với độ dao động giữa các seed. `Hold` vẫn cho phép thử nghiệm trên bản nháp, nhưng kết quả phải được ghi rõ là thử nghiệm trên bản chưa phát hành.

## 6. Quyết định và ghi chú AI

- Tôi giữ quyết định **Hold**. Muốn xem xét Release, cần người duyệt các cảnh báo còn lại và chạy QC lại theo quy trình được phép. Tôi sẽ không tăng `review.budget_images` hoặc đổi các ngưỡng cố định của đề để làm kết quả thành Release. Tôi cũng không nâng `second_opinion.conf` chỉ nhằm giảm số cờ, vì như vậy có thể bỏ sót lỗi.

- Tôi có dùng AI hỗ trợ viết bốn module. Prompt chính đưa docstring và test mẫu, yêu cầu dùng ngưỡng từ `cfg`, trả về danh sách `Issue` và không sửa dữ liệu gốc. Tôi đọc lại code, chạy test từng module, kiểm các báo cáo trên calib và raw. Có một lần gợi ý ban đầu cho `autofix` vừa xoá vừa cắt cùng dòng `BOX_OUT_OF_IMAGE`, làm `test_clip_box` không qua; tôi đã sửa để chỉ xoá khi cắt xong box không còn diện tích.

- Chưa làm phần thưởng CVAT.
