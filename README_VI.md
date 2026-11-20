# VIREO — ứng dụng hoàn chỉnh chạy cục bộ

Chạy `START_WINDOWS.bat`, mở **http://127.0.0.1:8013** sau khi backend sẵn sàng. Không mở HTML trực tiếp.

## Giao diện

Đăng nhập/đăng ký được thiết kế theo mẫu kính xanh: nhãn cổng truy cập nội bộ, biểu tượng trong ô nhập, hiện/ẩn mật khẩu, các thẻ giới thiệu và ảnh nền tòa nhà. Nút Trải nghiệm demo vẫn được giữ. Mã chuyển động được giữ nguyên từ gói VIREO_Chuyen_Dong_Day_Sang bạn cung cấp. Dashboard giữ chế độ sáng/tối; nút chuyển nằm giữa ? và NV, có lưu lựa chọn. Chỉ còn nút Đăng xuất ở menu trái.

## Tài khoản và phiên đăng nhập

- Đăng ký, đăng nhập, đăng xuất và demo gọi API FastAPI, không dùng tài khoản giả lưu riêng trong JavaScript.
- SQLite lưu tài khoản tại `backend/data/accounts.sqlite3`; mật khẩu băm PBKDF2-HMAC-SHA256 với salt riêng.
- Cookie HttpOnly/SameSite Strict giữ phiên tối đa 8 giờ; đăng xuất thu hồi phiên phía server.
- Các API dự đoán, nhập CSV, xem/xử lý/xuất giao dịch yêu cầu phiên hợp lệ. Health và thông số mô hình được đọc trước đăng nhập.
- Mỗi lần mở/tải lại trang vẫn hiện Đăng nhập/Đăng ký theo yêu cầu trước đó. Có thể đăng nhập tài khoản đã tạo hoặc bấm demo.
- Tài khoản của phiên bản frontend-only cũ cần đăng ký lại một lần; không tự chuyển mật khẩu từ trình duyệt.
- Đây là app demo học thuật dùng cục bộ, có một không gian giao dịch chung cho các tài khoản nhân viên/quản lý. Vai trò là vai trò mô phỏng, không phải cơ chế cấp quyền cho ngân hàng thực tế.

## Mô hình và dữ liệu

Giữ Frequency Encoding với 6 cột số và 7 cột danh mục, fit trên Train. IF và PyOD ECOD dùng ngưỡng tối ưu F1 trên Validation; không chọn lại ngưỡng từ CSV tải lên. Kèm model đã huấn luyện và metadata; `check_models.py` kiểm tra trước khi chạy. Bộ cài khóa scikit-learn 1.8.0 và PyOD 3.6.8 để tương thích model.

Nhập thủ công và CSV lưu chung trong SQLite; tải CSV mới không xóa giao dịch cũ. Trùng mã từ CSV giữ bản cũ, nhập thủ công trùng mã báo lỗi. Bộ lọc hỗ trợ vượt/trong ngưỡng IF và ECOD. ECOD chấm một lần trên toàn bộ file; một dòng chấm riêng có thể khác điểm khi nằm trong nhóm. Chất lượng phân biệt gian lận giữ nguyên notebook, giao diện mới không cải thiện độ chính xác mô hình.

## Kiểm tra đã thực hiện

- API: tạo tài khoản, email trùng, sai mật khẩu, đăng nhập, cookie HttpOnly, demo, hết phiên sau đăng xuất, chặn API chưa đăng nhập.
- ML: tải model Frequency 13, nhập thủ công, tải CSV 2.000 dòng, giữ đủ 2.001 giao dịch trong danh sách chung, các bộ lọc IF/ECOD.
- Trình duyệt: đăng nhập demo qua backend, mở form đăng ký, kiểm tra bố cục, chuyển sáng/tối, đăng xuất ở sidebar và quay về đăng nhập.
- JavaScript/Python kiểm tra cú pháp; ZIP kiểm tra toàn vẹn. Kiểm thử chạy trên môi trường Linux và Chrome; chưa chạy trực tiếp batch Windows trong môi trường này.

Đừng đưa file dữ liệu phiên/tài khoản của bạn lên repository công khai. Khi chuyển máy cần giữ cả SQLite tài khoản và dữ liệu giao dịch nếu muốn tiếp tục dùng dữ liệu đã nhập.

## Thiết bị giao dịch được khôi phục

Form có ô chọn Transaction_Device với đúng 20 mục, nằm sau Merchant_Category và trước Transaction_Location. Backend dùng đúng giá trị được chọn, không suy ra hay ghi đè từ Device_Type. Đây là hai đặc trưng riêng biệt trong mô hình. Giờ/ngày/tháng vẫn tách từ ô ngày giờ.
