# Báo cáo kiểm thử

Trạng thái: đang tích hợp phần thư bí mật; kết quả cuối sẽ được cập nhật sau khi chạy trên backend và giao diện hoàn chỉnh.

## Môi trường

- Windows, Python 3.9.10, Playwright 1.49.1, Chrome headless 155.0.8059.85.
- Trình duyệt kiểm tra ở 280, 320, 390, 768 và 1440 px; kiểm tra bổ sung các điểm gãy khi có thay đổi bố cục.
- Mật khẩu kiểm thử được tạo ngẫu nhiên cho kho dữ liệu tạm ngoài dự án. Không ghi mật khẩu, cookie, CSRF token hoặc URL ảnh chứa token vào báo cáo.

## Đo font trước thay đổi

Chrome CDP `CSS.getPlatformFontsForNode` ghi nhận tên hồ sơ `Lê Anh Tuấn` dùng một font Georgia, 12 glyph, ở 23,4 px với line-height 30,42 px. Chuỗi ở dạng Unicode NFC, không tràn hoặc cắt dòng. Chưa tái hiện việc trộn font dự phòng trên máy kiểm thử này. Nội dung hồ sơ dùng Segoe UI và Segoe UI Semibold tương ứng với độ đậm được khai báo.

Việc bổ sung font tiếng Việt cục bộ sẽ được kiểm tra riêng để xác nhận tải thành công và hiển thị nhất quán; kết quả này không được xem là bằng chứng rằng font ban đầu thiếu glyph.

## Các nhóm kiểm tra sau tích hợp

| Nhóm | Tiêu chí |
| --- | --- |
| Loading và hồ sơ | Loader biến mất khi DOM sẵn sàng, lỗi tài nguyên không chặn thao tác; animation hồ sơ chỉ bắt đầu sau khi loader đã gỡ; font cục bộ tải đúng; giảm chuyển động và tắt JavaScript vẫn dùng được nội dung cơ bản. |
| Mở khu vực bí mật | Đúng 7 lần bấm trong 2 giây; ít hơn ngưỡng hoặc hết thời gian không mở; mouse và touch không bị đếm đôi; không tạo hộp thoại trùng. |
| Đăng nhập | Không gửi request lấy thư trước khi xác thực; CSRF và Origin được kiểm tra; lần sai thứ sáu khóa theo cấu hình; reload hoặc ngữ cảnh trình duyệt mới không vượt khóa; session hết hạn buộc xác thực lại. |
| CRUD và lưu trữ | Tạo, đọc, sửa, xóa thư có UUID, thời gian server, lọc theo người nhận; thứ tự ảnh bền vững; tải lại và trình duyệt độc lập cùng thấy dữ liệu; ghi đồng thời không mất bản ghi; JSON lỗi không bị ghi đè bằng kho rỗng. |
| Ảnh và đường dẫn riêng tư | Kiểm tra giới hạn số ảnh, dung lượng, định dạng và giải mã; đường dẫn riêng tư và API từ chối khách chưa xác thực; lỗi upload không tạo bản ghi một phần. |
| Bố cục và bàn phím | Không tràn ngang với nội dung dài; modal giữ focus, hỗ trợ Escape và trả focus; nền khóa cuộn và khôi phục vị trí; giao diện mobile vẫn thao tác được. |

## Giới hạn

Các kiểm tra hiện có chưa thay thế đánh giá bảo mật triển khai thực tế, cấu hình reverse proxy hoặc HTTPS. Chỉ ghi nhận những hành vi được chạy và quan sát trên bản tích hợp cuối.
