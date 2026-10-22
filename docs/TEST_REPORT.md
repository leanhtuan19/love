# Báo cáo kiểm thử

## Bổ sung triển khai PythonAnywhere miễn phí

Sau khi thêm adapter WSGI và cấu hình SQLite journal, đã chạy `python -m unittest discover -s tests -p test_pythonanywhere.py -v`: 3/3 đạt; chạy lại `test_backend.py`: 23/23 đạt. Kiểm tra mới dùng app thật và kho tạm ngoài dự án: HTTPS/Secure cookie, CSRF/origin, đăng nhập, CRUD, đọc từ thiết bị khác, dữ liệu sau tạo lại app, kho mặc định dùng chung với CLI, SQLite DELETE, origin EU và từ chối journal mode không hỗ trợ. Không dùng mật khẩu/dữ liệu thật. Chưa deploy hoặc chạy thử network filesystem/HTTPS/upload trên tài khoản PythonAnywhere; browser suites không chạy lại vì frontend không đổi trong phần bổ sung này.

Đợt tích hợp trước đã chạy 41 bài kiểm tra tự động: 23 backend, 7 tích hợp trình duyệt, 8 thao tác pointer/mobile, 3 build artifact; tất cả đạt. Sau khi sửa lỗi nhấn nút tim không mở thư, đã chạy lại toàn bộ nhóm pointer/mobile được cập nhật: 9/9 đạt. Các nhóm còn lại không chạy lại trong bản sửa này. Chưa triển khai lên tài khoản GitHub Pages, Render hoặc Vercel.

## Môi trường

- Windows, Python 3.9.10, Playwright 1.49.1, Chrome headless 155.0.8059.85.
- Trình duyệt kiểm tra ở 280, 320, 390, 768 và 1440 px; kiểm tra bổ sung các điểm gãy khi có thay đổi bố cục.
- Mật khẩu kiểm thử được tạo ngẫu nhiên cho kho dữ liệu tạm ngoài dự án. Không ghi mật khẩu, cookie, CSRF token hoặc URL ảnh chứa token vào báo cáo.

## Đo font trước thay đổi

Chrome CDP `CSS.getPlatformFontsForNode` ghi nhận tên hồ sơ `Lê Anh Tuấn` dùng một font Georgia, 12 glyph, ở 23,4 px với line-height 30,42 px. Chuỗi ở dạng Unicode NFC, không tràn hoặc cắt dòng. Chưa tái hiện việc trộn font dự phòng trên máy kiểm thử này. Nội dung hồ sơ dùng Segoe UI và Segoe UI Semibold tương ứng với độ đậm được khai báo.

Font Lora cục bộ đã tải thành công qua backend thật; CDP ghi nhận custom font Lora và kiểm tra tên tiếng Việt dài tại 280px không tràn/cắt dấu. CSS đã sửa URL tương đối theo cấu trúc main/css hiện tại. Kết quả này không được xem là bằng chứng rằng font ban đầu thiếu glyph.

## Các nhóm kiểm tra sau tích hợp

| Nhóm | Tiêu chí |
| --- | --- |
| Loading và hồ sơ | Loader biến mất khi DOM sẵn sàng, lỗi tài nguyên không chặn thao tác; animation hồ sơ chỉ bắt đầu sau khi loader đã gỡ; font cục bộ tải đúng; giảm chuyển động và tắt JavaScript vẫn dùng được nội dung cơ bản. |
| Mở khu vực bí mật | 9 lần chưa mở; lần thứ 10 mở một popup. Khoảng cách giữa hai lần tối đa 1.200 ms; cả chuỗi có thể dài hơn. Chuột/touch thực, nhiều vị trí, đóng rồi đếm lại đều đạt. Vùng .heart-column, nút #heart và SVG bên trong cùng tham gia bộ đếm. Không đếm click giả, các nút khác/form, kéo, giữ, cuộn, pointercancel hoặc nhiều ngón. |
| Đăng nhập | Không gửi request lấy thư trước khi xác thực; CSRF và Origin được kiểm tra; lần sai thứ sáu khóa theo cấu hình; reload hoặc ngữ cảnh trình duyệt mới không vượt khóa; session hết hạn buộc xác thực lại. |
| CRUD và lưu trữ | Tạo, đọc, sửa, xóa thư có UUID, thời gian server, lọc theo người nhận; thứ tự ảnh bền vững; tải lại và trình duyệt độc lập cùng thấy dữ liệu; ghi đồng thời không mất bản ghi; JSON lỗi không bị ghi đè bằng kho rỗng. |
| Ảnh và đường dẫn riêng tư | Kiểm tra giới hạn số ảnh, dung lượng, định dạng và giải mã; đường dẫn riêng tư và API từ chối khách chưa xác thực; lỗi upload không tạo bản ghi một phần. |
| Bố cục và bàn phím | Không tràn ngang với nội dung dài; modal giữ focus, hỗ trợ Escape và trả focus; nền khóa cuộn và khôi phục vị trí; giao diện mobile vẫn thao tác được. |

## Giới hạn

Các kiểm tra hiện có chưa thay thế đánh giá bảo mật triển khai thực tế, cấu hình reverse proxy hoặc HTTPS. Chỉ ghi nhận những hành vi được chạy và quan sát trên bản tích hợp cuối.

## Các lệnh đã chạy và kết quả

| Lệnh | Số bài đạt |
| --- | --- |
| python -m unittest discover -s tests -p test_backend.py -v | 23/23 |
| python -m unittest discover -s tests -p test_browser.py -v | 7/7 |
| python -m unittest discover -s tests -p test_gestures.py -v | 9/9 sau bản sửa nút tim |
| python -m unittest discover -s tests -p test_static_build.py -v | 3/3 |
| python scripts/build_static.py | Build thành công, các URL HTML/CSS đều tìm thấy trong artifact |
| git diff --check | Không có lỗi whitespace |

Backend kiểm tra API/ảnh/đường dẫn riêng khi chưa xác thực, CSRF và origin, sai lần 6 và persistence sau reload/cookie mới, hết phiên, CRUD theo UUID, upload PNG/JPEG/WebP và giới hạn ảnh, loại metadata/mã đuôi, lỗi commit thu hồi ảnh, JSON hỏng không bị ghi đè, 18 yêu cầu lưu đồng thời qua hai app instance, xung đột sửa cũ trả 409. Kiểm tra mới bao phủ main/js, main/css, main/img, main/music, MIME font và origin Render/custom domain.

Trình duyệt tích hợp đã thực hiện tạo/sửa/xóa thư, upload/giữ thứ tự ảnh/lightbox, sắp xếp/lọc theo ID, tải lại và đọc từ browser context độc lập, giữ nháp khi hết phiên, khóa sai mật khẩu, focus/Escape/khóa cuộn, loading dự phòng và không JavaScript. Kho kiểm thử tạm, không sửa dữ liệu thật.

Gesture suite dùng sự kiện chuột và CDP touch thực, không dùng e.click() giả lập để vượt bộ đếm. Thử pinch nhiều ngón kéo rộng trên Chromium mô phỏng ghi nhận visualViewport.scale vẫn bằng 1; dọc trang vẫn cuộn được, pinch/cuộn không tăng đếm. Các kiểm tra cũng xác nhận nút tim, nhạc và hồ sơ vẫn thực hiện chức năng cũ.

Bản sửa nút tim kiểm tra riêng 9 click chuột vào #heart chưa mở, click thứ 10 mở đúng một popup và lời nhắn vẫn đổi. Trên Chromium mobile mô phỏng với animation bật, chạm xen kẽ vào SVG đang đập và phần trống .heart-column dùng chung bộ đếm, không đếm trùng touch/click; chạm trong popup không tạo popup mới và đóng xong cần đủ 10 lần mới mở lại.

Thử website dưới prefix /love/: toàn bộ CSS/JS/ảnh/font tải được, popup gọi /love/api/session, /love/api/auth và đăng nhập qua app backend được mount dưới prefix. Đây là kiểm tra đường dẫn/prefix bằng proxy trong test, không phải tuyên bố GitHub Pages thực thi Python.

Build artifact chỉ chứa index.html, main/, fonts/ và marker build; không có server.py, requirements, test, tài liệu, JSON thư, SQLite, khóa hay .env. Tùy chọn Vercel tạo đúng external rewrite nhưng không triển khai proxy thực tế. URL backend có credentials/query/path bị từ chối. Ảnh avatar trong artifact khớp byte với bản sao cục bộ; HTML không chứa access_token.

Một số lần test có ResourceWarning từ Werkzeug development handler khi Chrome hủy preload tệp MP3 cũ. Đây không phải lỗi JavaScript; các assertion đều đạt. Bản phục vụ đầy đủ dùng Waitress, không dùng development server của test.

## Những việc chưa kiểm tra trên môi trường thật

- Thiết bị iPhone/Safari và Android/Chrome vật lý, browser WebKit thật, zoom trợ năng của hệ điều hành. Chromium mô phỏng không thay thế các kiểm tra này và không đảm bảo chặn zoom 100%.
- Chạy GitHub Actions trên remote, Render Blueprint schema validator, dịch vụ có tính phí, migration kho dữ liệu production, HTTPS/domain/DNS/firewall.
- Vercel CLI/proxy production, Set-Cookie qua proxy thực, giới hạn upload của proxy và preview domain. Không dùng Vercel Functions /tmp làm kho bền.
- Token avatar cũ có thể còn trong lịch sử Git. Đã gỡ khỏi HTML hiện tại và giữ đúng ảnh bằng snapshot; chưa thu hồi token tại Facebook và không viết lại lịch sử repository.
