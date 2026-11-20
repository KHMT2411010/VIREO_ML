# Cách dùng ngưỡng F1 trong VIREO

- Cả Isolation Forest và ECOD được fit trên Train, không truyền nhãn vào fit.
- Trên Validation có nhãn, chương trình thử các giá trị ngưỡng của **điểm bất thường** và tính Precision/Recall/F1 cho từng ngưỡng.
- `train.py` lưu `threshold` (ngưỡng điểm cho F1 lớn nhất) và `val_f1` (F1 tương ứng) cho mỗi mô hình vào `backend/models/metrics.json`.
- Khi dự đoán CSV mới, API tính điểm bằng mô hình đã học rồi so sánh `score >= threshold`. **Không so sánh score với val_f1** vì thang đo khác nhau.
- `/api/metrics` trả metadata gồm ngưỡng, val_f1 và F1 trên Test. `/api/predict` và `/api/predict-csv` trả `threshold_selection.method = max_f1_validation` và `threshold_selection.validation_f1`.
- Không tính lại F1 từ CSV mới không có nhãn; không dùng nhãn của chính CSV cần đánh giá để chọn lại ngưỡng.
- Kết quả có thể cảnh báo nhầm nhiều (ROC-AUC trước đây ~0.5). Đây là công cụ nghiên cứu, không kết luận chắc chắn gian lận.
