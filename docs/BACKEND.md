# Cấu hình và vận hành Love Days

Ảnh/video gốc, upload chia phần, bản đồ, Geoapify và thanh nhạc mới: xem [MEDIA_MAPS_AUDIO.md](MEDIA_MAPS_AUDIO.md).

Nhật ký, Cài đặt quản trị và cơ chế khóa 300/30 giây được mô tả trong [hướng dẫn nâng cấp](UPGRADE_SETTINGS_JOURNAL.md). Thư cũ tiếp tục dùng JSON; các bảng mới dùng auth.sqlite3 trong cùng kho riêng.

## Kiến trúc

Website gốc là frontend tĩnh. Trình duyệt không thể tự ghi an toàn một JSON chung cho hai thiết bị hoặc giữ bí mật một mật khẩu được nhúng trong JavaScript. Bản này giữ nguyên frontend và bổ sung Flask, Waitress, Werkzeug, Pillow và filelock. Không dùng localStorage làm kho thư.

Thư lưu trong một letters.json UTF-8. Ảnh/video nằm ở kho riêng và JSON chỉ lưu metadata. SQLite lưu xác thực, cài đặt, nhật ký/lịch sử, tiến trình upload và cache địa điểm; nội dung thư tiếp tục nằm trong JSON.

## Chạy trên máy này

Mật khẩu ban đầu theo yêu cầu đã được nhập qua CLI và lưu dưới dạng băm scrypt có salt. Không có mật khẩu rõ hoặc hash mặc định trong frontend, JSON công khai, repository hay ví dụ cấu hình.

~~~powershell
python -m pip install -r requirements.txt
python server.py serve --host 127.0.0.1 --port 8001
~~~

Mở http://127.0.0.1:8001. Nhấn 10 lần vào .heart-column, nút tim bên trong hoặc nền/vùng nội dung không tương tác, cách nhau tối đa 1.200 ms mỗi lần. Các điều khiển khác không tham gia bộ đếm. Nội dung thư chỉ được yêu cầu sau khi máy chủ xác nhận phiên.

## Cài trên máy mới

Dùng Python 3.10 trở lên khi triển khai mới. Bản đã được kiểm tra với Python 3.9 trên môi trường hiện có; requirements có nhánh Pillow phù hợp cho phiên bản này.

~~~powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe server.py init-password
.\.venv\Scripts\python.exe server.py serve --host 127.0.0.1 --port 8001
~~~

Linux/macOS thay đường dẫn Python của môi trường ảo bằng .venv/bin/python. CLI hỏi mật khẩu và xác nhận bằng getpass; dữ liệu nhập không hiện ra màn hình. Chọn mật khẩu từ 8 đến 256 ký tự.

Đổi mật khẩu cũng bằng lệnh init-password. Lệnh thay băm và thu hồi tất cả phiên đã đăng nhập; không thay đổi thư, ảnh hoặc bỏ qua thời gian chờ do nhập sai. Nếu có biến LOVEDAYS_PASSWORD_HASH, bỏ biến đó trước khi đổi mật khẩu lưu trên đĩa.

## Nơi lưu riêng và quyền truy cập

Mặc định:

~~~text
<thư mục người dùng>/.lovedays-private/<mã riêng của đường dẫn dự án>/
  letters.json
  letters.lock
  images/
    <tên UUID an toàn>.jpg | .png | .webp
  auth.sqlite3
  auth.sqlite3-wal, auth.sqlite3-shm (khi SQLite đang chạy)
  secret.key
  setup.lock
~~~

Xem vị trí thực tế:

~~~powershell
python -c "from server import create_app; print(create_app().config['DATA_DIR'])"
~~~

Có thể đặt một đường dẫn ổn định bằng biến môi trường trước khi khởi tạo mật khẩu và chạy server:

~~~powershell
$env:LOVEDAYS_DATA_DIR = "D:\LoveDaysPrivate"
python server.py init-password
python server.py serve --host 127.0.0.1 --port 8001
~~~

Linux/macOS:

~~~sh
export LOVEDAYS_DATA_DIR=/var/lib/lovedays-private
python server.py init-password
python server.py serve --host 127.0.0.1 --port 8001
~~~

Kho này phải ở ngoài thư mục dự án và ngoài mọi document root khác. Server từ chối cấu hình kho nằm trong dự án. Khi chuyển dự án hoặc triển khai lên máy khác, chuyển cả kho riêng và cấu hình đường dẫn mới; không chỉ chép frontend. Không đưa kho vào Git.

Tài khoản chạy backend cần quyền đọc/ghi/tạo/đổi tên/xóa trong kho để ghi thay thế JSON và quản lý ảnh. Trên Linux đặt chủ sở hữu là tài khoản dịch vụ, thư mục 0700, file riêng 0600. Trên Windows dùng ACL để chỉ tài khoản dịch vụ và quản trị viên cần thiết được truy cập; không cấp quyền cho tài khoản phục vụ file tĩnh công khai.

Sao lưu toàn bộ kho cùng nhau, bao gồm JSON, ảnh, khóa và SQLite. Nên dừng backend khi sao lưu file SQLite trực tiếp, hoặc dùng cơ chế backup SQLite nhất quán.

## Những vị trí có thể thay đổi

| Thiết lập | Vị trí | Mặc định |
| --- | --- | --- |
| Mật khẩu | CLI server.py init-password | Giá trị đã khởi tạo riêng, không có mặc định trong mã |
| Số lần nhấn | SECRET_CONFIG.clicks trong main/js/letters.js | 10 |
| Khoảng cách tối đa giữa hai lần nhấn | SECRET_CONFIG.maxGapMs trong main/js/letters.js | 1200 ms |
| Giữ tay quá lâu không tính | SECRET_CONFIG.maxPressMs trong main/js/letters.js | 500 ms |
| Dịch chuyển tay tối đa | SECRET_CONFIG.maxMovementPx trong main/js/letters.js | 12 pixel |
| Lần sai tự đóng/khóa | MAX_LOGIN_FAILURES trong create_app của server.py | 6, nghĩa là cho phép sai 5 lần |
| Cửa sổ giới hạn nhập sai | LOGIN_WINDOW_SECONDS trong server.py | 900 giây |
| Thời hạn phiên | SESSION_TTL_SECONDS trong server.py | 1800 giây, có giới hạn tuyệt đối |
| Số lượng/dung lượng tệp đính kèm | Không áp giới hạn nghiệp vụ | Phụ thuộc hosting và dung lượng còn lại |
| Kích thước một phần upload | CHUNK_BYTES trong media_uploads.py | 1 MiB, không phải dung lượng cả tệp |
| Upload đồng thời | CONCURRENT_UPLOADS trong main/js/media.js | 2 tệp, không hạn chế tổng số tệp |
| Mô tả người trong popup | Đối tượng profiles trong main/js/profiles.js | Tuấn và Thư theo thông tin đã cung cấp |
| Danh sách ID người gửi/nhận | PEOPLE trong server.py | tuan, thu |
| Dự phòng frontend khi chưa tải cấu hình | SECRET_CONFIG, DEFAULT_PEOPLE trong main/js/letters.js | Đồng bộ giá trị hiện tại |
| Thời gian thoát loading dự phòng | FALLBACK_TIMEOUT_MS trong main/js/loading.js | 5000 ms |

Frontend lấy giới hạn văn bản và danh sách người từ API/session. Các giá trị giới hạn số ảnh/dung lượng cũ hiện là null để tương thích API; không còn chặn theo các giá trị cũ. Khởi động lại server sau khi sửa cấu hình Python.

Tên có thể trùng hoặc đổi, nhưng senderId/recipientId phải ổn định. Không đổi ID đã được dùng nếu chưa di chuyển dữ liệu liên quan. ID thư và ID ảnh do backend tạo UUID; frontend không dùng vị trí mảng làm ID.

## JSON và lưu đồng thời

Xem [letters.example.json](letters.example.json) để biết đầy đủ cấu trúc schemaVersion và letters. Nội dung ví dụ chỉ minh họa, ảnh ví dụ không phải file thực tế; server không tự nạp dữ liệu mẫu.

Backend tự đặt UUID, createdAt và updatedAt ở UTC ISO 8601. Giao diện luôn hiển thị theo Asia/Ho_Chi_Minh, kể cả khi thiết bị đặt múi giờ khác. Nội dung được render bằng textContent và giữ xuống dòng.

Toàn bộ thao tác đọc–sửa–ghi JSON có khóa trong tiến trình và khóa file giữa các tiến trình. File tạm được ghi, flush, fsync rồi thay thế nguyên tử. Lưu mới đồng thời không làm mất thư. Chỉnh sửa gửi expectedUpdatedAt; nếu thư đã được sửa ở thiết bị khác, API trả 409 và giữ bản nháp để tránh ghi đè âm thầm. JSON hỏng trả 503 và giữ nguyên file, không tự biến thành danh sách rỗng.

Ảnh JPEG/PNG/WebP và video MP4/WebM mới được xác minh định dạng thực tế, giữ nguyên byte gốc, tên lưu sinh riêng. Tệp hoàn tất qua hàng đợi được giữ khi lưu lỗi để thử lại; xóa thư hoặc gỡ tệp sẽ xóa tham chiếu và file tương ứng. Media nhật ký cũ vẫn được giữ riêng cho lịch sử. Bản nháp lỗi và File chưa lưu nằm trong RAM của tab; tải lại hoặc đóng tab có thể mất bản nháp. Xem hướng dẫn media cho retry, Range và CLI dọn upload chưa dùng.

## API và quyền

| Endpoint | Yêu cầu |
| --- | --- |
| GET /api/session | Khởi tạo CSRF, kiểm tra phiên và cấu hình; không trả thư |
| POST /api/auth | Mật khẩu + X-CSRF-Token, kiểm tra Origin |
| POST /api/logout | Phiên hiện tại + CSRF, thu hồi đăng nhập |
| GET /api/letters | Phiên hợp lệ; danh sách mới nhất trước |
| GET /api/letters/&lt;id&gt; | Phiên hợp lệ; đúng UUID thư |
| POST /api/letters | Phiên + CSRF; JSON hoặc multipart |
| PUT /api/letters/&lt;id&gt; | Phiên + CSRF; sửa thư, có thể kiểm tra expectedUpdatedAt |
| DELETE /api/letters/&lt;id&gt; | Phiên + CSRF; frontend xác nhận trước khi gọi |
| GET /api/images/&lt;imageId&gt; | Phiên hợp lệ; tìm metadata trong JSON, không nhận đường dẫn file |

Multipart có trường payload là JSON và nhiều trường images cho file mới. payload có senderId, senderName, recipientId, type, title, content, keepImageIds và expectedUpdatedAt khi sửa. Backend chọn recipientName từ ID đã biết, không tin tên nhận tùy ý từ request.

Không có tài khoản cá nhân trong dự án. Mật khẩu chung mở quyền đọc, tạo, sửa và xóa chung; chọn tên chỉ gắn metadata cho thư. Bộ lọc người nhận không phải xác thực và không giả lập phân quyền tác giả. Muốn quyền riêng theo từng người cần bổ sung tài khoản cùng kiểm tra quyền ở backend.

Cookie phiên là HttpOnly, SameSite=Strict; nội dung API và ảnh riêng dùng no-store. Các thao tác ghi yêu cầu CSRF và Origin cùng trang. Số lần nhập sai lưu bền theo trình duyệt và IP, không được đặt lại chỉ bằng đóng popup, tải lại trang hoặc xóa cookie. Khóa tính trong cửa sổ 15 phút từ lần sai đầu tiên; đăng nhập đúng không được dùng để vượt một khóa đang có hiệu lực. Hết phiên phải nhập lại mật khẩu.

Các file JSON, SQLite, khóa, mã backend, test và tài liệu không nằm trong danh sách file tĩnh được phục vụ. Không dùng máy chủ file tĩnh thay cho backend để triển khai tính năng thư.

## Đưa lên mạng cho hai thiết bị

Hai thiết bị phải truy cập cùng một địa chỉ backend. Trên mạng LAN tin cậy có thể chạy với --host 0.0.0.0 và dùng địa chỉ IP của máy chủ; chỉ mở firewall cho mạng cần thiết. Không dùng localhost trên thiết bị thứ hai vì địa chỉ đó trỏ về chính thiết bị ấy.

Khi đưa lên Internet, chạy Waitress sau reverse proxy HTTPS, proxy cả website và /api về cùng backend. Đặt:

~~~powershell
$env:LOVEDAYS_PUBLIC_ORIGIN = "https://ten-mien-cua-ban.example"
$env:LOVEDAYS_COOKIE_SECURE = "true"
python server.py serve --host 127.0.0.1 --port 8001
~~~

Không bật Secure cookie cho bản thử HTTP localhost, vì trình duyệt có thể không gửi cookie ở cấu hình HTTP khác. Mật khẩu chỉ nên truyền qua HTTPS khi dùng ngoài máy cục bộ.

Backend mặc định không tin X-Forwarded-For do client gửi. Với reverse proxy, giới hạn IP có thể được dùng chung cho những người đi qua proxy; nếu mở rộng nhiều người dùng, cấu hình proxy tin cậy có kiểm soát trước khi tách IP thực. Không bật CORS cho nguồn tùy ý.

GitHub Pages hoặc hosting chỉ phục vụ HTML không chạy được backend này. Cần máy chủ/dịch vụ có Python và dung lượng ghi bền cho kho riêng. Thiết lập dịch vụ khởi động lại sau reboot và sao lưu kho; không dùng filesystem tạm của một container không có volume. Cấu hình GitHub/Pages/Render/Vercel phù hợp với repository hiện tại có tại [DEPLOYMENT.md](DEPLOYMENT.md). Render tự cung cấp RENDER_EXTERNAL_URL để backend kiểm tra origin; LOVEDAYS_PUBLIC_ORIGIN được ưu tiên nếu có tên miền riêng.

Phương án miễn phí giữ nguyên backend: [PythonAnywhere Beginner](DEPLOY_FREE.md). Dùng pythonanywhere_wsgi.py và đặt LOVEDAYS_SQLITE_JOURNAL_MODE=DELETE khi chạy CLI trên PythonAnywhere; adapter đặt chế độ này mặc định cho Web app. Môi trường khác vẫn mặc định WAL. Giữ CLI và WSGI cùng đường dẫn dự án/kho dữ liệu.

## Kiểm tra

~~~powershell
python -m unittest discover -s tests -p test_backend.py -v
~~~

Các bài kiểm tra backend dùng dữ liệu và mật khẩu ngẫu nhiên riêng ngoài repository, không thay mật khẩu hoặc thư thực.

Trình duyệt cần Playwright và Chrome/Chromium. Cách chạy và kết quả thực tế nằm tại [TEST_REPORT.md](TEST_REPORT.md). Kiểm tra giả lập di động không thay thế kiểm tra trên điện thoại thật.

## Kiểm tra font và loading

Baseline trước khi sửa: chuỗi Lê Anh Tuấn là UTF-8/NFC, CSS Georgia với line-height tương ứng, không thấy overflow hoặc cắt dấu và CDP báo dùng glyph Georgia trên máy kiểm tra. Vì vậy không kết luận sai rằng dữ liệu bị lỗi encoding hoặc thiếu glyph ở tất cả máy.

Bản mới thay riêng #profile-name bằng Lora variable lưu cục bộ, có tập ký tự tiếng Việt; dùng weight 500 thật, line-height 1.55, padding cho dấu, cho xuống dòng và dự phòng Segoe UI/Arial. Không đổi font toàn trang. Font có giấy phép OFL đi kèm.

Loading không có phần trăm giả và không chờ ảnh Facebook/nhạc từ xa. Nó kết thúc khi DOM và các script defer đã sẵn sàng, fade ra rồi mới cho profile xuất hiện. Có đường thoát dự phòng 5 giây; overlay được gỡ hẳn khỏi DOM và không còn chặn click. Không JavaScript thì overlay mặc định ẩn; nội dung cơ bản và trình phát nhạc vẫn dùng được.

## Tài liệu chính thức đã đối chiếu

- [Flask: bảo vệ CSRF, cookie và giới hạn tài nguyên](https://flask.palletsprojects.com/en/stable/web-security/).
- [Werkzeug: generate_password_hash và check_password_hash](https://werkzeug.palletsprojects.com/en/stable/utils/#werkzeug.security.generate_password_hash).
- [OWASP: Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).
- [Pillow: xử lý an toàn file ảnh](https://pillow.readthedocs.io/en/stable/handbook/security.html).
- [Google Fonts: metadata Lora, gồm vietnamese](https://raw.githubusercontent.com/google/fonts/main/ofl/lora/METADATA.pb).
