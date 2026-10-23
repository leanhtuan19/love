# Báo cáo kiểm thử

## Nhật ký, quản trị và tự khóa — 23/10/2026

Đã chạy các nhóm kiểm thử dưới đây trong quá trình tích hợp: **81 bài đạt, 1 bài fork POSIX bị bỏ qua trên Windows**. Kho, khóa và credentials kiểm thử đều được tạo tạm ngoài repository; không sửa dữ liệu thật và không đăng nhập tài khoản production.

| File kiểm thử | Kết quả |
| --- | --- |
| test_backend.py | 23/23 |
| test_site_features.py | 14/14 |
| test_mailbox_expiry.py | 9/9 |
| test_mailbox_ui.py | 5/5 |
| test_features_browser.py | 3/3 |
| test_browser.py | 7/7 |
| test_gestures.py | 9/9 |
| test_fork_locks.py | 3 đạt, 1 bỏ qua vì không có os.fork |
| test_pythonanywhere.py | 3/3 |
| test_static_build.py | 3/3 |
| test_backup_private.py | 2/2 |

Chạy từng nhóm bằng `python -m unittest discover -s tests -p TEN_FILE.py -v`; có thể chạy toàn bộ bằng `python -m unittest discover -s tests -v`. Các nhóm được chạy riêng trong quá trình tích hợp, không tuyên bố đã chạy một lượt nguyên bộ sau mỗi thay đổi giao diện.

Kiểm tra mới bao phủ mốc idle 300/đóng 30 giây bằng đồng hồ giả ở backend, mở lại trước hạn, nhiều tab/cookie chung, tải lại, hoạt động nền không gia hạn, khóa ngay, thu hồi phiên và giữ nháp trong RAM. Chromium dùng chuột/touch thật và hai tab; sự kiện chuyển nền và vị trí/thời gian được mô phỏng có kiểm soát. Tương tác tổng hợp không tạo hoạt động hòm thư. API ảnh/thư từ chối phiên đã hết hạn.

Quản trị/nhật ký đã kiểm tra mã hóa username và không lộ thông tin trong API công khai, CSRF/origin, phiên độc lập, xác thực lại/thu hồi sau đổi tài khoản, setup lặp an toàn, rate limit sau restart, đổi mật khẩu chức năng, ghi lịch sử trước/sau trong transaction, xóa mềm, ảnh lịch sử riêng tư, rollback SQL/upload, tìm tiếng Việt không dấu và ngày thực theo múi giờ Việt Nam, phân trang, upload/giới hạn ảnh, tọa độ thủ công và 8 yêu cầu ghi đồng thời từ hai app. Sao lưu kiểm tra JSON/ảnh/khóa và snapshot SQLite có thể đọc lại, không ghi đè bản sao cũ hoặc ghi ZIP vào vùng public.

Luồng trình duyệt mới thực hiện đăng bài kèm ảnh sau mở quyền, định vị thành công/từ chối vẫn nhập thủ công, xem ảnh lớn, nhập sai/đúng mật khẩu sửa bài, mở lịch sử và xóa có xác nhận; đổi hồ sơ/nội dung có hiệu lực ngay và đổi tài khoản phải đăng nhập lại. Bootstrap có chuỗi đóng script được kiểm tra không thực thi XSS. Kiểm tra thêm phản hồi quản trị/lịch sử bị trì hoãn sau đóng/mở popup xác nhận không làm hiện lại dữ liệu cũ. Không ghi nhận lỗi JavaScript hoặc tràn ngang ở 320/390 px trong các luồng mới; các hồi quy bố cục cũ cũng đạt.

Chưa deploy/reload trên tài khoản PythonAnywhere, chưa xác nhận filesystem mạng, proxy HTTPS và quota hosting thật; chưa kiểm tra iPhone/Safari/Android vật lý hoặc WebKit. Các ResourceWarning từ MP3 bị Chromium hủy preload trong Werkzeug test server không phải lỗi JavaScript. Hướng dẫn nâng cấp đầy đủ: [UPGRADE_SETTINGS_JOURNAL.md](UPGRADE_SETTINGS_JOURNAL.md).

## Sửa khóa file bị kế thừa qua fork — 23/10/2026

Traceback trên PythonAnywhere xác định GET /api/letters bị lỗi 500 vì UnixFileLock của letters.lock được tạo trước khi worker fork. LetterStore hiện lấy cặp RLock/FileLock riêng theo PID, giữ nguyên đường dẫn file khóa, khóa đọc–sửa–ghi và timeout 15 giây. Không đổi dữ liệu hoặc cấu hình xác thực.

Đã chạy 23/23 test_backend.py và 3/3 test_pythonanywhere.py thành công sau bản sửa. Nhóm mới test_fork_locks.py đạt 3 kiểm tra mô phỏng PID, bỏ qua 1 kiểm tra os.fork thật vì môi trường hiện tại là Windows. Kiểm tra mới bao phủ tạo lại cả hai khóa, lồng context giữ tính reentrant, dùng lại phiên đăng nhập và đọc/tạo/sửa/xóa thư sau đổi PID, giữ nguyên dữ liệu khi đọc và trả 503 khi một thread khác giữ khóa file thật. Thay implementation cũ trong bộ nhớ tái hiện được RuntimeError và lỗi 500 như log người dùng; không ghi đè file nguồn khi kiểm chứng. git diff --check đạt. Chưa deploy/reload hoặc kiểm tra fork thật trên tài khoản PythonAnywhere; frontend không thay đổi trong bản sửa này.

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
